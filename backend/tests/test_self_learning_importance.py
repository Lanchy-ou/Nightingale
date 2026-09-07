"""E2 synthetic evaluation: bounded metadata feedback changes future priority."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import URL, create_engine, event as sqlalchemy_event, inspect, select, text, update

from app.ai_pipeline import AnchoredCandidate, PipelineOutput, persist_derived
from app.db import SessionLocal, engine, migrate_e2_schema
from app.highlights import compute_score, locate_span
from app.importance_learning import (
    MAX_ADJUSTMENT,
    MIN_ADJUSTMENT,
    adjustment,
    compose_score,
    score_new_candidate,
)
from app.main import app
from app.models import Artifact, AuditLog, Event, Highlight, ImportanceFeedback, Patient
from app.storage_security import assert_sqlcipher_file
from seed import fixture

BACKEND = Path(__file__).resolve().parent.parent
BASE_FLAGS = {
    "recency": False,
    "explicit_risk": False,
    "unresolved_task": False,
    "clinician_confirmed": False,
    "symptom_change": False,
    "repeated_mentions": False,
}


def _persist_future_candidate(
    db,
    *,
    suffix: str,
    entity_type: str = "symptom",
    clinic_id: str = fixture.CLINIC_ID,
    patient_id: str = fixture.PATIENT_B_ID,
    actor_id: str = fixture.USER_CLINICIAN_ID,
    flags: dict | None = None,
    review_status: str | None = None,
) -> Highlight:
    """Persist one independent synthetic AI candidate with an exact source span."""
    event_id = f"evt_e2_{suffix}"
    source_id = f"art_e2_source_{suffix}"
    quote = f"Synthetic evaluation source statement {suffix}."
    event = Event(
        event_id=event_id,
        patient_id=patient_id,
        clinic_id=clinic_id,
        event_type="doctor_consult",
        encounter_id=None,
        started_at=datetime(2026, 8, 27, 9, 0),
        ended_at=None,
        created_at=datetime(2026, 8, 27, 9, 1),
    )
    source = Artifact(
        artifact_id=source_id,
        event_id=event_id,
        artifact_type="transcript",
        author_role="system",
        author_id=None,
        content={"segments": [{"index": 0, "speaker": "patient", "text": quote}]},
        created_at=datetime(2026, 8, 27, 9, 1),
        version=1,
        provenance_pointer=None,
        ingestion_key=None,
        generation_metadata=None,
    )
    db.add_all([event, source])
    db.commit()
    span = locate_span(source.content, quote)
    assert span is not None
    candidate_flags = {**BASE_FLAGS, **(flags or {})}
    output = PipelineOutput(
        summary_content={"summary": f"Synthetic E2 evaluation {suffix}", "key_points": []},
        provenance_pointer={"event_id": event_id, "artifact_id": source_id, "span": span},
        candidates=[
            AnchoredCandidate(
                text=f"Synthetic {entity_type} candidate {suffix}",
                risk_reason="Controlled synthetic importance evaluation",
                entity_type=entity_type,
                entity_key=f"{entity_type}:synthetic-e2-{suffix}",
                assertion_value="synthetic",
                span=span,
                feature_flags=candidate_flags,
                score=compute_score(candidate_flags),
                review_status=review_status,
                conflict_with_artifact_id=None,
            )
        ],
        method="mock",
        degraded=False,
        fallback_reason=None,
        redaction_counts={"name": 0, "id": 0, "phone": 0},
        recompute_existing=[],
    )
    _, highlight_ids = persist_derived(
        db,
        event,
        source,
        "ai_doctor_consult_summary",
        output,
        actor_id=actor_id,
        actor_role="clinician",
        provider="mock",
        model="deterministic-e2-eval",
    )
    assert len(highlight_ids) == 1
    return db.get(Highlight, highlight_ids[0])


def _feedback_rows(db) -> list[ImportanceFeedback]:
    return db.scalars(
        select(ImportanceFeedback).order_by(
            ImportanceFeedback.created_at, ImportanceFeedback.feedback_id
        )
    ).all()


def test_clinician_pin_changes_current_order_and_future_similar_score_independently(
    clinician_client, db_session
):
    response = clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "pinned"}
    )
    assert response.status_code == 200

    current = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").json()
    assert current["highlights"][0]["highlight_id"] == "hl_headache_worsening"
    assert current["highlights"][0]["status"] == "pinned"

    future = _persist_future_candidate(db_session, suffix="pin_future")
    control = _persist_future_candidate(
        db_session, suffix="pin_control", entity_type="medication"
    )
    assert future.base_importance_score == 0
    assert future.adaptive_adjustment == 0
    assert future.importance_score == 0
    assert future.learning_metadata["serving_mode"] == "base_only"
    assert future.status == "suggested"
    assert control.base_importance_score == 0
    assert control.adaptive_adjustment == 0
    future_order = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_B_ID}/glance"
    ).json()["highlights"]
    assert {row["highlight_id"] for row in future_order[:2]} == {
        future.highlight_id,
        control.highlight_id,
    }


def test_reject_decreases_future_similar_but_same_base_control_is_unchanged(
    clinician_client, db_session
):
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "rejected"}
    ).status_code == 200

    symptom = _persist_future_candidate(db_session, suffix="reject_symptom")
    control = _persist_future_candidate(
        db_session, suffix="reject_medication", entity_type="medication"
    )
    assert symptom.base_importance_score == control.base_importance_score == 0
    assert symptom.adaptive_adjustment == 0
    assert symptom.importance_score == 0
    assert control.adaptive_adjustment == 0
    assert control.importance_score == 0
    future_order = clinician_client.get(
        f"/api/patients/{fixture.PATIENT_B_ID}/glance"
    ).json()["highlights"]
    assert {row["highlight_id"] for row in future_order[:2]} == {
        control.highlight_id,
        symptom.highlight_id,
    }


def test_learning_is_clinic_scoped(clinician_client, db_session):
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "pinned"}
    ).status_code == 200
    db_session.add(
        Patient(patient_id="pat_e2_other_clinic", clinic_id=fixture.CLINIC_B_ID, name="Synthetic E2 Control")
    )
    db_session.commit()

    clinic_a = _persist_future_candidate(db_session, suffix="clinic_a")
    clinic_b = _persist_future_candidate(
        db_session,
        suffix="clinic_b",
        clinic_id=fixture.CLINIC_B_ID,
        patient_id="pat_e2_other_clinic",
        actor_id=fixture.USER_CLINICIAN_B_ID,
    )
    assert clinic_a.adaptive_adjustment == 0
    assert clinic_b.adaptive_adjustment == 0
    assert clinic_b.learning_metadata["review_count"] == 0


def test_staff_signal_works_without_clinician_confirmation(staff_client, db_session):
    response = staff_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    )
    assert response.status_code == 200
    assert response.json()["feature_flags"]["clinician_confirmed"] is False

    future = _persist_future_candidate(db_session, suffix="staff_future")
    assert future.adaptive_adjustment == 0
    assert future.feature_flags["clinician_confirmed"] is False


def test_patient_admin_and_non_ai_rows_do_not_train(
    patient_client, admin_client, clinician_client, db_session
):
    for client in (patient_client, admin_client):
        response = client.post(
            "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
        )
        assert response.status_code == 403
    assert _feedback_rows(db_session) == []

    # This historical clinician-authored row can still be reviewed, but it is
    # not an AI-derived Highlight and therefore cannot enter learning.
    response = clinician_client.post(
        "/api/highlights/hl_medication_existing/status", json={"status": "accepted"}
    )
    assert response.status_code == 200
    assert _feedback_rows(db_session) == []


def test_successful_status_cas_with_missing_offset_does_not_train(
    clinician_client, db_session
):
    highlight = db_session.get(Highlight, "hl_headache_worsening")
    highlight.source_span = {"kind": "message", "index": 1}
    db_session.commit()

    response = clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    db_session.expire_all()
    assert _feedback_rows(db_session) == []


def test_successful_status_cas_with_ai_summary_self_citation_does_not_train(
    clinician_client, db_session
):
    highlight = db_session.get(Highlight, "hl_headache_worsening")
    summary = db_session.get(Artifact, highlight.artifact_id)
    quote = summary.content["summary"]
    self_span = locate_span(summary.content, quote)
    assert self_span is not None
    highlight.source_artifact_id = summary.artifact_id
    highlight.source_span = self_span
    db_session.commit()

    response = clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    )
    assert response.status_code == 200
    assert response.json()["status"] == "accepted"
    db_session.expire_all()
    assert _feedback_rows(db_session) == []


def test_latest_feedback_per_actor_highlight_prevents_toggle_inflation(
    clinician_client, db_session
):
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    ).status_code == 200
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "pinned"}
    ).status_code == 200

    assert _feedback_rows(db_session) == []


def test_noop_and_losing_cas_produce_no_feedback(clinician_client, db_session):
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    ).status_code == 200
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    ).status_code == 200
    assert _feedback_rows(db_session) == []

    # Deterministic stale-writer probe mirroring the endpoint's conditional
    # UPDATE: only the winning rowcount may call record_feedback.
    from app.importance_learning import record_feedback

    with SessionLocal() as winner, SessionLocal() as loser:
        winner_hl = winner.get(Highlight, "hl_nausea_persists")
        loser_hl = loser.get(Highlight, "hl_nausea_persists")
        winner_event = winner.get(Event, winner_hl.event_id)
        loser_event = loser.get(Event, loser_hl.event_id)
        won = winner.execute(
            update(Highlight)
            .where(Highlight.highlight_id == winner_hl.highlight_id, Highlight.status == "suggested")
            .values(status="accepted")
        )
        assert won.rowcount == 1
        record_feedback(
            winner,
            highlight=winner_hl,
            event=winner_event,
            actor_id=fixture.USER_CLINICIAN_ID,
            actor_role="clinician",
            status="accepted",
            created_at=datetime(2026, 8, 27, 10, 0),
            feedback_id="ifb_e2_winner",
        )
        winner.commit()

        lost = loser.execute(
            update(Highlight)
            .where(Highlight.highlight_id == loser_hl.highlight_id, Highlight.status == "suggested")
            .values(status="rejected")
        )
        assert lost.rowcount == 0
        loser.rollback()

    db_session.expire_all()
    assert len(_feedback_rows(db_session)) == 1


def test_adjustment_caps_and_other_key_fail_safe(db_session):
    pairs = [
        (fixture.USER_CLINICIAN_ID, "hl_headache_worsening", "clinician", 2),
        (fixture.USER_STAFF_ID, "hl_headache_worsening", "staff", 1),
        (fixture.USER_CLINICIAN_ID, "hl_nausea_persists", "clinician", 2),
        (fixture.USER_STAFF_ID, "hl_nausea_persists", "staff", 1),
    ]
    start = datetime(2026, 8, 27, 11, 0)
    for index, (actor, highlight, role, signal) in enumerate(pairs):
        db_session.add(
            ImportanceFeedback(
                feedback_id=f"ifb_cap_pos_{index}",
                highlight_id=highlight,
                clinic_id=fixture.CLINIC_ID,
                actor_id=actor,
                actor_role=role,
                feedback_key="symptom",
                status="pinned",
                signal_value=signal,
                created_at=start + timedelta(seconds=index),
            )
        )
    db_session.commit()
    assert adjustment(db_session, fixture.CLINIC_ID, "symptom")[0] == MAX_ADJUSTMENT

    for index, (actor, highlight, role, _signal) in enumerate(pairs):
        db_session.add(
            ImportanceFeedback(
                feedback_id=f"ifb_cap_neg_{index}",
                highlight_id=highlight,
                clinic_id=fixture.CLINIC_ID,
                actor_id=actor,
                actor_role=role,
                feedback_key="symptom",
                status="rejected",
                signal_value=-1,
                created_at=start + timedelta(minutes=1, seconds=index),
            )
        )
    # Unknown/unsupported entity types map to `other`, which is recorded but
    # deliberately never generalized across unrelated clinical concepts.
    db_session.add(
        ImportanceFeedback(
            feedback_id="ifb_other",
            highlight_id="hl_headache_worsening",
            clinic_id=fixture.CLINIC_ID,
            actor_id=fixture.USER_CLINICIAN_ID,
            actor_role="clinician",
            feedback_key="other",
            status="pinned",
            signal_value=2,
            created_at=start + timedelta(minutes=2),
        )
    )
    db_session.commit()
    assert adjustment(db_session, fixture.CLINIC_ID, "symptom")[0] == MIN_ADJUSTMENT
    assert adjustment(db_session, fixture.CLINIC_ID, "chief_complaint")[0] == 0


def test_negative_learning_cannot_lower_any_hard_protection(db_session):
    protected_cases = [
        ({"explicit_risk": True}, "suggested", None),
        ({"unresolved_task": True}, "suggested", None),
        ({"clinician_confirmed": True}, "suggested", None),
        ({}, "pinned", None),
        ({}, "suggested", "needs_review"),
    ]
    for extra_flags, status, review_status in protected_cases:
        flags = {**BASE_FLAGS, **extra_flags}
        result = compose_score(
            base_importance_score=compute_score(flags),
            adaptive_adjustment=-2,
            decay_adjustment=0,
            feature_flags=flags,
            status=status,
            review_status=review_status,
            learning_metadata={"reason": "clinic_latest_reviews", "protection_applied": False},
        )
        assert result.adaptive_adjustment == 0
        assert result.importance_score == result.base_importance_score
        assert result.learning_metadata["protection_applied"] is True


def test_feedback_and_audit_are_metadata_only(clinician_client, db_session):
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    ).status_code == 200
    from app.importance_learning import record_feedback

    highlight = db_session.get(Highlight, "hl_headache_worsening")
    event = db_session.get(Event, highlight.event_id)
    row = record_feedback(
        db_session,
        highlight=highlight,
        event=event,
        actor_id=fixture.USER_CLINICIAN_ID,
        actor_role="clinician",
        status="accepted",
    )
    db_session.commit()
    assert row is not None
    assert set(row.__table__.columns.keys()) == {
        "feedback_id",
        "highlight_id",
        "clinic_id",
        "actor_id",
        "actor_role",
        "feedback_key",
        "status",
        "signal_value",
        "created_at",
    }
    serialized = json.dumps(
        {column.name: getattr(row, column.name) for column in row.__table__.columns},
        default=str,
    )
    assert "Worsening headache frequency" not in serialized
    assert "My headaches used to happen once a week" not in serialized
    assert "Headache frequency increased from once weekly" not in serialized
    assert fixture.PATIENT_NAME not in serialized

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "highlight_status",
            AuditLog.target_id == "hl_headache_worsening",
        )
    )
    assert audit is not None
    assert audit.details == {
        "from_status": "suggested", "to_status": "accepted",
        "clinician_confirmation_added": True,
    }


def test_future_learned_highlight_keeps_exact_provenance(clinician_client, db_session):
    assert clinician_client.post(
        "/api/highlights/hl_headache_worsening/status", json={"status": "accepted"}
    ).status_code == 200
    future = _persist_future_candidate(db_session, suffix="provenance")
    assert future.adaptive_adjustment == 0

    response = clinician_client.get(f"/api/highlights/{future.highlight_id}/provenance")
    assert response.status_code == 200
    body = response.json()
    assert body["quote"] == "Synthetic evaluation source statement provenance."
    assert body["span"] == future.source_span
    assert body["source_artifact"]["artifact_id"] == future.source_artifact_id


def test_glance_read_neither_imports_nor_queries_learning_aggregation(
    clinician_client,
):
    code = (
        "import json, sys\n"
        "__import__('app.api.highlights')\n"
        "print(json.dumps('app.importance_learning' in sys.modules))\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=str(BACKEND), capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) is False

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    sqlalchemy_event.listen(engine, "before_cursor_execute", capture)
    try:
        response = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert not any("importance_feedback" in statement for statement in statements)
    assert not any("artifacts" in statement for statement in statements)
    assert not any("audit_logs" in statement for statement in statements)


def test_future_final_tiebreak_remains_stable(clinician_client, db_session):
    first = _persist_future_candidate(db_session, suffix="tie_z")
    second = _persist_future_candidate(db_session, suffix="tie_a")
    tied_at = datetime(2026, 8, 27, 12, 0)
    for row in (first, second):
        row.created_at = tied_at
        row.updated_at = tied_at
    db_session.commit()

    response = clinician_client.get(f"/api/patients/{fixture.PATIENT_B_ID}/glance")
    assert response.status_code == 200
    ids = [row["highlight_id"] for row in response.json()["highlights"]]
    assert ids == sorted(ids)


def test_glance_ui_explains_base_only_feedback_semantics_without_actor_details():
    component = (BACKEND.parent / "frontend/src/components/GlancePanel.tsx").read_text(
        encoding="utf-8"
    )
    types = (BACKEND.parent / "frontend/src/types.ts").read_text(encoding="utf-8")
    assert "Learned priority" in component
    assert "Base {h.base_importance_score}" in component
    assert "final {h.importance_score}" in component
    assert "These controls do not teach future ranking" in component
    assert "remain Shadow-only" in component
    assert "actor_id" not in component
    for field in (
        "base_importance_score",
        "adaptive_adjustment",
        "decay_adjustment",
        "learning_metadata",
    ):
        assert field in types


def test_explicit_e2_migration_backfills_legacy_score_and_is_idempotent(tmp_path):
    legacy = create_engine(f"sqlite:///{tmp_path / 'legacy-e2.db'}")
    with legacy.begin() as connection:
        connection.execute(text("CREATE TABLE clinics (clinic_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (user_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE highlights ("
                "highlight_id VARCHAR(64) PRIMARY KEY, importance_score INTEGER NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO highlights (highlight_id, importance_score) VALUES ('legacy_hl', 7)")
        )

    migrate_e2_schema(legacy)
    migrate_e2_schema(legacy)
    inspector = inspect(legacy)
    columns = {column["name"] for column in inspector.get_columns("highlights")}
    assert {
        "base_importance_score",
        "adaptive_adjustment",
        "decay_adjustment",
        "learning_metadata",
    } <= columns
    assert "importance_feedback" in inspector.get_table_names()
    with legacy.connect() as connection:
        row = connection.execute(
            text(
                "SELECT base_importance_score, adaptive_adjustment, decay_adjustment, "
                "importance_score, learning_metadata FROM highlights WHERE highlight_id='legacy_hl'"
            )
        ).one()
    assert tuple(row[:4]) == (7, 0, 0, 7)
    assert json.loads(row[4]) == {}
    legacy.dispose()


def test_explicit_e2_migration_runs_on_sqlcipher_demo(tmp_path):
    database = tmp_path / "legacy-e2.encrypted.db"
    key = "e2-migration-synthetic-key-32-bytes-minimum"
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
        connection.execute(text("CREATE TABLE clinics (clinic_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(text("CREATE TABLE users (user_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE highlights ("
                "highlight_id VARCHAR(64) PRIMARY KEY, importance_score INTEGER NOT NULL)"
            )
        )
        connection.execute(
            text("INSERT INTO highlights (highlight_id, importance_score) VALUES ('legacy_hl', 5)")
        )

    migrate_e2_schema(encrypted)
    with encrypted.connect() as connection:
        row = connection.execute(
            text("SELECT base_importance_score, importance_score FROM highlights")
        ).one()
    assert tuple(row) == (5, 5)
    encrypted.dispose()
    probe = assert_sqlcipher_file(database, key)
    assert probe["plain_reader_blocked"] is True
