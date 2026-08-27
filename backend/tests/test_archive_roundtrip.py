from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import event as sqlalchemy_event, func, select

from app.data_decay import (
    ArchiveIntegrityError,
    build_shadow_archive,
    canonical_json_bytes,
    restore_shadow_archive,
    run_storage_policy,
)
from app.db import engine
from app.models import (
    Artifact,
    ArtifactStorageState,
    ArtifactVersion,
    AuditLog,
    Comment,
    Highlight,
    Task,
)
from app.tasks import resolve_exact_span
from seed import fixture


AS_OF = datetime(2026, 8, 26, 23, 59, 59)


def _counts(db_session):
    return {
        model.__tablename__: db_session.scalar(select(func.count()).select_from(model))
        for model in (Artifact, ArtifactVersion, Comment, AuditLog, Task)
    }


def test_canonical_hash_is_stable_across_dict_order():
    first = {"z": [2, 1], "a": {"β": "值", "x": True}}
    second = {"a": {"x": True, "β": "值"}, "z": [2, 1]}
    left = build_shadow_archive(first)
    right = build_shadow_archive(second)
    assert canonical_json_bytes(first) == canonical_json_bytes(second)
    assert left.source_sha256 == right.source_sha256
    assert left.compressed_payload == right.compressed_payload


def test_cold_shadow_archive_roundtrip_preserves_authoritative_content_and_span(db_session):
    artifact = db_session.get(Artifact, fixture.ART_HIST_2025_NOTE)
    highlight = db_session.get(Highlight, "hl_headache_once_weekly")
    authoritative = deepcopy(artifact.content)
    quote_before = resolve_exact_span(authoritative, highlight.source_span)

    run_storage_policy(
        db_session,
        as_of=AS_OF,
        apply=True,
        evaluated_at=datetime(2026, 8, 27, 8, 0),
    )
    state = db_session.get(ArtifactStorageState, artifact.artifact_id)
    restored = restore_shadow_archive(state)

    assert state.tier == "cold"
    assert state.codec == "zlib-json-v1"
    assert state.compressed_payload
    assert restored == authoritative == artifact.content
    assert resolve_exact_span(restored, highlight.source_span) == quote_before


def test_apply_preserves_all_authoritative_rows_versions_and_content(db_session):
    before_counts = _counts(db_session)
    before_content = {
        row.artifact_id: (deepcopy(row.content), row.version)
        for row in db_session.scalars(select(Artifact)).all()
    }

    run_storage_policy(
        db_session,
        as_of=AS_OF,
        apply=True,
        evaluated_at=datetime(2026, 8, 27, 8, 0),
    )

    assert _counts(db_session) == before_counts
    after_content = {
        row.artifact_id: (row.content, row.version)
        for row in db_session.scalars(select(Artifact)).all()
    }
    assert after_content == before_content


def test_corrupted_payload_fails_closed_and_next_apply_marks_hot(db_session):
    run_storage_policy(db_session, as_of=AS_OF, apply=True)
    state = db_session.get(ArtifactStorageState, fixture.ART_HIST_2025_NOTE)
    state.compressed_payload = b"corrupted-shadow-payload"
    db_session.commit()

    with pytest.raises(ArchiveIntegrityError):
        restore_shadow_archive(state)

    report = run_storage_policy(db_session, as_of=AS_OF, apply=True)
    row = next(item for item in report.artifacts if item.artifact_id == state.artifact_id)
    db_session.refresh(state)
    assert row.tier == state.tier == "hot"
    assert "archive_integrity_failed" in state.reason_codes
    assert state.codec is None
    assert state.compressed_payload is None
    assert state.roundtrip_verified_at is None


def test_patient_view_does_not_leak_storage_metadata(patient_client, db_session):
    run_storage_policy(db_session, as_of=AS_OF, apply=True)
    response = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view")
    assert response.status_code == 200
    rendered = response.text.lower()
    for forbidden in (
        "storage", "tier", "sha256", "codec", "compressed_payload",
        "reason_codes", "retention", "original_bytes", "compressed_bytes",
    ):
        assert forbidden not in rendered


def test_glance_get_does_not_run_policy_decompression_or_llm(
    clinician_client, db_session, monkeypatch
):
    run_storage_policy(db_session, as_of=AS_OF, apply=True)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("maintenance/archive code ran on Glance GET")

    monkeypatch.setattr("app.data_decay.run_storage_policy", forbidden)
    monkeypatch.setattr("app.data_decay.restore_shadow_archive", forbidden)
    monkeypatch.setattr("app.llm_client.build_client", forbidden)

    statements: list[str] = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement.lower())

    sqlalchemy_event.listen(engine, "before_cursor_execute", capture)
    try:
        response = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", capture)
    assert response.status_code == 200
    assert not any("artifact_storage_state" in statement for statement in statements)
    assert not any("artifacts" in statement for statement in statements)
    assert not any("events" in statement for statement in statements)


def test_cross_clinic_artifact_authorization_is_unchanged(
    clinician_client, db_session
):
    run_storage_policy(db_session, as_of=AS_OF, apply=True)
    response = clinician_client.get("/api/events/evt_other_clinic/artifacts")
    assert response.status_code == 404
