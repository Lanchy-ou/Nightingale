from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import URL, create_engine, inspect, select, text
from sqlalchemy.orm import Session

from app.data_decay import (
    HOT_MAX_AGE_DAYS,
    POLICY_VERSION,
    WARM_MAX_AGE_DAYS,
    run_storage_policy,
)
from app.db import migrate_e3_schema
from app.models import Artifact, ArtifactStorageState, Event, Highlight, Task
from app.storage_security import assert_sqlcipher_file
from seed import fixture
from seed.seed import create_schema, seed


AS_OF = datetime(2026, 8, 26, 23, 59, 59)
BACKEND = Path(__file__).resolve().parent.parent


def _result(report, artifact_id: str):
    return next(row for row in report.artifacts if row.artifact_id == artifact_id)


def _apply(db_session):
    return run_storage_policy(
        db_session,
        as_of=AS_OF,
        apply=True,
        evaluated_at=datetime(2026, 8, 27, 8, 0),
    )


def test_injected_as_of_produces_stable_fixture_tiers_and_decay(db_session):
    report = _apply(db_session)

    assert report.policy_version == POLICY_VERSION
    assert report.as_of == AS_OF
    assert _result(report, fixture.ART_HIST_2025_NOTE).tier == "cold"
    assert _result(report, fixture.ART_HIST_2026_NOTE).tier == "warm"
    assert _result(report, fixture.ART_PRE_RAW).tier == "hot"

    old = db_session.get(Highlight, "hl_headache_once_weekly")
    older_context = db_session.get(Highlight, "hl_headache_frequency_feb")
    current = db_session.get(Highlight, "hl_headache_worsening")
    assert old.decay_adjustment == -2
    assert older_context.decay_adjustment == -1
    assert current.decay_adjustment == 0
    for highlight in (old, older_context, current):
        assert highlight.importance_score == (
            highlight.base_importance_score
            + highlight.adaptive_adjustment
            + highlight.decay_adjustment
        )


def test_hot_warm_cold_boundaries_and_future_timestamp_fail_safe(db_session):
    event = db_session.get(Event, fixture.EVT_HIST_2025)
    artifact = db_session.get(Artifact, fixture.ART_HIST_2025_NOTE)
    highlight = db_session.get(Highlight, "hl_headache_once_weekly")
    highlight.source_span = None
    highlight.artifact_id = None
    highlight.source_artifact_id = None

    cases = [
        (AS_OF - timedelta(days=HOT_MAX_AGE_DAYS), "hot", 0),
        (AS_OF - timedelta(days=HOT_MAX_AGE_DAYS, seconds=1), "warm", -1),
        (AS_OF - timedelta(days=WARM_MAX_AGE_DAYS), "warm", -1),
        (AS_OF - timedelta(days=WARM_MAX_AGE_DAYS, seconds=1), "cold", -2),
        (AS_OF + timedelta(seconds=1), "hot", 0),
    ]
    for started_at, expected_tier, expected_decay in cases:
        event.started_at = started_at
        db_session.commit()
        report = run_storage_policy(db_session, as_of=AS_OF, apply=False)
        row = _result(report, artifact.artifact_id)
        assert (row.tier, row.decay_adjustment) == (expected_tier, expected_decay)
        if expected_tier == "hot" and started_at > AS_OF:
            assert "future_event_time" in row.reason_codes


def test_all_hard_protections_override_age_and_force_zero_decay(db_session):
    protection_mutations = {
        "explicit_risk": lambda h: setattr(
            h, "feature_flags", {**h.feature_flags, "explicit_risk": True}
        ),
        "clinician_confirmed": lambda h: setattr(
            h, "feature_flags", {**h.feature_flags, "clinician_confirmed": True}
        ),
        "pinned": lambda h: setattr(h, "status", "pinned"),
        "needs_review": lambda h: setattr(h, "review_status", "needs_review"),
    }

    for expected_reason, mutate in protection_mutations.items():
        highlight = db_session.get(Highlight, "hl_headache_once_weekly")
        original_flags = deepcopy(highlight.feature_flags)
        original_status = highlight.status
        original_review = highlight.review_status
        mutate(highlight)
        db_session.commit()

        report = _apply(db_session)
        row = _result(report, fixture.ART_HIST_2025_NOTE)
        assert row.tier == "hot"
        assert expected_reason in row.reason_codes
        db_session.refresh(highlight)
        assert highlight.decay_adjustment == 0

        highlight.feature_flags = original_flags
        highlight.status = original_status
        highlight.review_status = original_review
        db_session.commit()


def test_only_real_unresolved_task_protects_old_artifact(db_session):
    old_highlight = db_session.get(Highlight, "hl_headache_once_weekly")
    old_highlight.feature_flags = {**old_highlight.feature_flags, "unresolved_task": True}
    db_session.commit()
    report = _apply(db_session)
    assert _result(report, fixture.ART_HIST_2025_NOTE).tier == "cold"

    task = db_session.get(Task, fixture.TASK_SYMPTOM_DIARY)
    task.event_id = fixture.EVT_HIST_2025
    task.source_artifact_id = fixture.ART_HIST_2025_NOTE
    task.source_span = old_highlight.source_span
    task.status = "open"
    current = db_session.scalar(select(Highlight).where(Highlight.task_id == task.task_id))
    if current is not None:
        current.task_id = None
    db_session.flush()
    old_highlight.task_id = task.task_id
    db_session.commit()

    report = _apply(db_session)
    row = _result(report, fixture.ART_HIST_2025_NOTE)
    assert row.tier == "hot"
    assert "unresolved_task" in row.reason_codes
    db_session.refresh(old_highlight)
    assert old_highlight.decay_adjustment == 0


def test_old_event_only_resolved_task_highlight_decays_until_real_task_reopens(
    db_session,
):
    highlight = db_session.get(Highlight, "hl_headache_once_weekly")
    task = db_session.get(Task, fixture.TASK_SYMPTOM_DIARY)
    task.event_id = fixture.EVT_HIST_2025
    task.source_artifact_id = None
    task.source_span = None
    task.status = "completed"
    current = db_session.scalar(select(Highlight).where(Highlight.task_id == task.task_id))
    if current is not None:
        current.task_id = None
    db_session.flush()
    highlight.artifact_id = None
    highlight.source_artifact_id = None
    highlight.source_span = None
    highlight.task_id = task.task_id
    highlight.feature_flags = {**highlight.feature_flags, "unresolved_task": True}
    db_session.commit()

    _apply(db_session)
    db_session.refresh(highlight)
    assert highlight.decay_adjustment == -2

    task.status = "open"
    db_session.commit()
    _apply(db_session)
    db_session.refresh(highlight)
    assert highlight.decay_adjustment == 0


def test_current_patient_instruction_is_explicitly_retained(db_session):
    event = db_session.get(Event, fixture.EVT_REVIEW_0826)
    prior_instruction_event = db_session.get(Event, fixture.EVT_DOC_0821)
    event.started_at = datetime(2020, 1, 1)
    prior_instruction_event.started_at = datetime(2019, 1, 1)
    db_session.commit()

    report = _apply(db_session)
    current = _result(report, fixture.ART_REVIEW_INSTRUCTION)
    assert current.tier == "hot"
    assert "current_patient_instruction" in current.reason_codes


def test_unverified_exact_provenance_fails_closed_to_hot(db_session):
    highlight = db_session.get(Highlight, "hl_headache_once_weekly")
    highlight.source_span = {"kind": "section", "index": "assessment", "offset": [999, 1000]}
    db_session.commit()

    report = _apply(db_session)
    row = _result(report, fixture.ART_HIST_2025_NOTE)
    assert row.tier == "hot"
    assert "provenance_unverified" in row.reason_codes
    assert row.decay_adjustment == 0


def test_final_score_discards_legacy_adaptive_component_in_base_only_serving(db_session):
    highlight = db_session.get(Highlight, "hl_headache_once_weekly")
    highlight.adaptive_adjustment = 2
    highlight.learning_metadata = {
        **highlight.learning_metadata,
        "raw_adjustment": 2,
    }
    db_session.commit()

    _apply(db_session)
    db_session.refresh(highlight)
    assert highlight.decay_adjustment == -2
    assert highlight.adaptive_adjustment == 0
    assert highlight.importance_score == highlight.base_importance_score - 2


def test_old_low_value_decay_can_move_it_out_of_glance_top_five(
    clinician_client, db_session
):
    highlights = {
        row.highlight_id: row for row in db_session.scalars(select(Highlight)).all()
    }
    for row in highlights.values():
        row.status = "rejected"
        row.feature_flags = {key: False for key in row.feature_flags}
        row.base_importance_score = 0
        row.adaptive_adjustment = 0
        row.decay_adjustment = 0
        row.importance_score = 0

    target = highlights["hl_headache_once_weekly"]
    target.status = "suggested"
    # Old data cannot earn recency. A repeated historical mention can still
    # outrank a zero-score historical control until its decay applies.
    target.feature_flags = {**target.feature_flags, "repeated_mentions": True}
    leaders = [
        highlights["hl_headache_worsening"],
        highlights["hl_nausea_persists"],
        highlights["hl_bp_elevated"],
        highlights["hl_medication_existing"],
    ]
    for row in leaders:
        row.status = "suggested"
        row.feature_flags = {
            **row.feature_flags,
            "recency": True,
            "symptom_change": True,
        }
    control = highlights["hl_headache_frequency_feb"]
    control.status = "suggested"
    db_session.commit()
    from app.glance_projection import rebuild_glance_projections

    rebuild_glance_projections(db_session, fixture.PATIENT_ID)
    db_session.commit()

    url = f"/api/patients/{fixture.PATIENT_ID}/glance"
    before = [row["highlight_id"] for row in clinician_client.get(url).json()["highlights"]]
    assert target.highlight_id in before
    assert control.highlight_id not in before

    _apply(db_session)
    after = [row["highlight_id"] for row in clinician_client.get(url).json()["highlights"]]
    assert target.highlight_id not in after
    assert control.highlight_id in after
    db_session.refresh(target)
    assert target.decay_adjustment == -2


def test_policy_apply_is_idempotent(db_session):
    first = _apply(db_session)
    before = {
        row.artifact_id: (
            row.tier,
            tuple(row.reason_codes),
            row.source_sha256,
            row.codec,
            row.compressed_payload,
            row.original_bytes,
            row.compressed_bytes,
            row.evaluated_as_of,
            row.evaluated_at,
            row.roundtrip_verified_at,
        )
        for row in db_session.scalars(select(ArtifactStorageState)).all()
    }

    second = _apply(db_session)
    after = {
        row.artifact_id: (
            row.tier,
            tuple(row.reason_codes),
            row.source_sha256,
            row.codec,
            row.compressed_payload,
            row.original_bytes,
            row.compressed_bytes,
            row.evaluated_as_of,
            row.evaluated_at,
            row.roundtrip_verified_at,
        )
        for row in db_session.scalars(select(ArtifactStorageState)).all()
    }
    assert first.updated_count == len(before)
    assert second.updated_count == 0
    assert after == before


def test_policy_apply_is_idempotent_with_a_later_runner_clock(db_session):
    run_storage_policy(
        db_session,
        as_of=AS_OF,
        apply=True,
        evaluated_at=datetime(2026, 8, 27, 8, 0),
    )
    before = {
        row.artifact_id: (row.evaluated_at, row.roundtrip_verified_at)
        for row in db_session.scalars(select(ArtifactStorageState)).all()
    }
    second = run_storage_policy(
        db_session,
        as_of=AS_OF,
        apply=True,
        evaluated_at=datetime(2026, 8, 27, 9, 0),
    )
    after = {
        row.artifact_id: (row.evaluated_at, row.roundtrip_verified_at)
        for row in db_session.scalars(select(ArtifactStorageState)).all()
    }
    assert second.updated_count == 0
    assert after == before


def test_dry_run_is_read_only(db_session):
    before_scores = {
        row.highlight_id: (row.decay_adjustment, row.importance_score)
        for row in db_session.scalars(select(Highlight)).all()
    }
    report = run_storage_policy(db_session, as_of=AS_OF, apply=False)
    assert report.archive_candidate_count >= 1
    assert db_session.scalars(select(ArtifactStorageState)).all() == []
    after_scores = {
        row.highlight_id: (row.decay_adjustment, row.importance_score)
        for row in db_session.scalars(select(Highlight)).all()
    }
    assert after_scores == before_scores


def test_explicit_e3_sqlite_migration_is_idempotent(tmp_path):
    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy-e3.db'}")
    with legacy.begin() as connection:
        connection.execute(text("CREATE TABLE artifacts (artifact_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE highlights (highlight_id VARCHAR(64) PRIMARY KEY, importance_score INTEGER NOT NULL)"))
        connection.execute(text("CREATE TABLE clinics (clinic_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (user_id VARCHAR(64) PRIMARY KEY)"))

    migrate_e3_schema(legacy)
    migrate_e3_schema(legacy)
    inspector = inspect(legacy)
    assert "artifact_storage_state" in inspector.get_table_names()
    columns = {column["name"] for column in inspector.get_columns("artifact_storage_state")}
    assert {
        "artifact_id", "tier", "reason_codes", "policy_version",
        "evaluated_as_of", "evaluated_at", "source_sha256", "codec",
        "compressed_payload", "original_bytes", "compressed_bytes",
        "roundtrip_verified_at",
    } == columns
    legacy.dispose()


def test_explicit_e3_migration_runs_on_sqlcipher_demo(tmp_path):
    database = tmp_path / "legacy-e3.encrypted.db"
    key = "e3-migration-synthetic-key-32-bytes-minimum"
    encrypted = create_engine(
        URL.create(
            "sqlite+pysqlcipher",
            username="",
            password=key,
            database=str(database),
        ),
        connect_args={"check_same_thread": False},
    )
    with encrypted.begin() as connection:
        connection.execute(text("CREATE TABLE artifacts (artifact_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE highlights (highlight_id VARCHAR(64) PRIMARY KEY, importance_score INTEGER NOT NULL)"))
        connection.execute(text("CREATE TABLE clinics (clinic_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (user_id VARCHAR(64) PRIMARY KEY)"))

    migrate_e3_schema(encrypted)
    with encrypted.connect() as connection:
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
    assert "artifact_storage_state" in tables
    encrypted.dispose()
    assert assert_sqlcipher_file(database, key)["plain_reader_blocked"] is True


def test_cli_runner_dry_run_apply_and_rerun_are_safe_and_idempotent(tmp_path):
    database = tmp_path / "runner-e3.db"
    local_engine = create_engine(f"sqlite:///{database}")
    create_schema(local_engine)
    with Session(local_engine) as session:
        seed(session)
    local_engine.dispose()

    env = {**os.environ, "NANTINGALE_DB_URL": f"sqlite:///{database}"}

    def run(mode: str) -> dict:
        result = subprocess.run(
            [
                sys.executable,
                "scripts/apply_storage_policy.py",
                "--as-of",
                "2026-08-26",
                mode,
            ],
            cwd=BACKEND,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert fixture.PATIENT_NAME not in result.stdout
        assert "once weekly" not in result.stdout
        return json.loads(result.stdout)

    dry = run("--dry-run")
    assert dry["mode"] == "dry-run"
    assert dry["updated_count"] == 0
    expected_tiers = {"cold": 8, "hot": 31, "warm": 11}
    assert dry["tier_counts"] == expected_tiers

    first = run("--apply")
    second = run("--apply")
    assert first["updated_count"] == sum(expected_tiers.values()) == 50
    assert second["updated_count"] == 0
    assert first["tier_counts"] == second["tier_counts"]
    assert "not total database savings" in first["limitation"]
