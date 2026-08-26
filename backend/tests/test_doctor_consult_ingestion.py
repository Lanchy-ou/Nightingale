"""C1 hard gate: Encounter + strict manual Doctor Consult ingestion."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.highlights import extract_text
from app.llm_client import InvalidOutputError
from app.models import Artifact, AuditLog, Event, Highlight
from seed import fixture


def _payload(consult_id: str = "consult-c1-001", ingestion_key: str = "submit-c1-001") -> dict:
    return {
        "consult_id": consult_id,
        "ingestion_key": ingestion_key,
        "started_at": "2026-08-26T10:00:00",
        "ended_at": "2026-08-26T10:20:00",
        "content": deepcopy(fixture.C1_DEMO_DOCTOR_TRANSCRIPT),
    }


def _force_missing_provider(monkeypatch) -> None:
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("Natingale_API_KEY", raising=False)


def test_clinician_creates_new_consult_raw_summary_highlights_and_audit(
    clinician_client, db_session, monkeypatch
):
    _force_missing_provider(monkeypatch)
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=_payload()
    )
    assert response.status_code == 200, response.text
    body = response.json()

    event = db_session.get(Event, body["event"]["event_id"])
    raw = db_session.get(Artifact, body["source_artifact_id"])
    summary = db_session.get(Artifact, body["ai_summary_artifact_id"])

    assert event.event_id != fixture.EVT_DOC_0821
    assert event.event_type == "doctor_consult"
    assert event.encounter_id == body["encounter_id"] == body["event"]["encounter_id"]
    assert event.encounter_id
    assert body["event"]["artifact_count"] == 2

    assert raw.event_id == event.event_id
    assert raw.artifact_type == "transcript"
    assert raw.author_role == "system" and raw.author_id is None
    assert raw.content == fixture.C1_DEMO_DOCTOR_TRANSCRIPT
    assert [s["index"] for s in raw.content["segments"]] == list(
        range(len(raw.content["segments"]))
    )

    assert summary.event_id == event.event_id
    assert summary.artifact_type == "ai_doctor_consult_summary"
    assert summary.author_role == "system" and summary.author_id is None
    assert summary.provenance_pointer["artifact_id"] == raw.artifact_id
    assert body["generation_method"] == "deterministic_fallback"
    assert body["degraded"] is True
    assert body["fallback_reason"] == "provider_missing"
    assert body["idempotent_replay"] is False
    assert body["highlight_ids"]

    for highlight_id in body["highlight_ids"]:
        highlight = db_session.get(Highlight, highlight_id)
        assert highlight.event_id == event.event_id
        assert highlight.artifact_id == summary.artifact_id
        assert highlight.source_artifact_id == raw.artifact_id
        assert extract_text(raw.content, highlight.source_span)

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.event_id == event.event_id)
    ).all()
    assert {audit.action for audit in audits} >= {
        "doctor_consult_create",
        "source_ingest",
        "ai_fallback",
    }
    assert all(not hasattr(audit, "content") for audit in audits)


def test_raw_transcript_is_committed_before_pipeline(
    clinician_client, monkeypatch
):
    _force_missing_provider(monkeypatch)
    import app.api.sources as sources

    real_run_pipeline = sources.run_pipeline
    observed: dict[str, bool] = {}

    def asserting_pipeline(db, event, raw, *args, **kwargs):
        # A separate DB session proves durability, not merely same-session flush.
        with SessionLocal() as independent:
            persisted_event = independent.get(Event, event.event_id)
            persisted_raw = independent.get(Artifact, raw.artifact_id)
            observed["committed"] = (
                persisted_event is not None
                and persisted_raw is not None
                and persisted_raw.content == fixture.C1_DEMO_DOCTOR_TRANSCRIPT
            )
        return real_run_pipeline(db, event, raw, *args, **kwargs)

    monkeypatch.setattr(sources, "run_pipeline", asserting_pipeline)
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-raw-first", "submit-raw-first"),
    )
    assert response.status_code == 200
    assert observed == {"committed": True}


def test_consult_replay_is_idempotent(clinician_client, db_session, monkeypatch):
    _force_missing_provider(monkeypatch)
    payload = _payload("consult-replay", "submit-replay")
    first = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=payload
    )
    replay = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults", json=payload
    )
    assert first.status_code == replay.status_code == 200
    a, b = first.json(), replay.json()
    assert b["idempotent_replay"] is True
    assert b["event"]["event_id"] == a["event"]["event_id"]
    assert b["encounter_id"] == a["encounter_id"]
    assert b["source_artifact_id"] == a["source_artifact_id"]
    assert b["ai_summary_artifact_id"] == a["ai_summary_artifact_id"]
    assert set(b["highlight_ids"]) == set(a["highlight_ids"])

    event_id = a["event"]["event_id"]
    assert db_session.scalar(
        select(func.count()).select_from(Event).where(Event.event_id == event_id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.event_id == event_id)
    ) == 2


def test_same_consult_id_with_different_ingestion_key_conflicts(
    clinician_client, monkeypatch
):
    _force_missing_provider(monkeypatch)
    first = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-key-conflict", "submission-a"),
    )
    second = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-key-conflict", "submission-b"),
    )
    assert first.status_code == 200
    assert second.status_code == 409


class _InvalidSchemaClient:
    def summarize(self, redacted, flow_type):
        raise InvalidOutputError("invalid schema")


def test_provider_schema_failure_returns_explicit_fallback(
    clinician_client, monkeypatch
):
    import app.api.sources as sources

    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setattr(sources, "build_client", lambda provider: _InvalidSchemaClient())
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-invalid-provider", "submit-invalid-provider"),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["generation_method"] == "deterministic_fallback"
    assert body["degraded"] is True
    assert body["fallback_reason"] == "invalid_output"


def test_generated_highlight_provenance_endpoint_resolves_exact_segment(
    clinician_client, monkeypatch
):
    _force_missing_provider(monkeypatch)
    created = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-provenance", "submit-provenance"),
    ).json()
    assert created["highlight_ids"]

    response = clinician_client.get(
        f"/api/highlights/{created['highlight_ids'][0]}/provenance"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_id"] == created["event"]["event_id"]
    assert body["source_artifact"]["artifact_id"] == created["source_artifact_id"]
    assert body["span"]["kind"] == "segment"
    assert body["quote"]
    assert body["quote"] == extract_text(
        body["source_artifact"]["content"], body["span"]
    )


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        (fixture.USER_STAFF_ID, 403),
        (fixture.USER_PATIENT_ID, 403),
        (fixture.USER_ADMIN_ID, 403),
        (fixture.USER_CLINICIAN_B_ID, 404),
    ],
)
def test_doctor_consult_rbac_matrix(client, user_id, expected):
    response = client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        headers={"X-User-Id": user_id},
        json=_payload(f"consult-rbac-{user_id}", f"submit-rbac-{user_id}"),
    )
    assert response.status_code == expected


def test_doctor_consult_absent_patient_and_anonymous_are_hidden(client):
    missing = client.post(
        "/api/patients/not-a-patient/doctor-consults",
        headers={"X-User-Id": fixture.USER_CLINICIAN_ID},
        json=_payload("consult-missing", "submit-missing"),
    )
    anonymous = client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-anon", "submit-anon"),
    )
    assert missing.status_code == 404
    assert anonymous.status_code == 401
    assert missing.json()["error"]["message"] == "Resource not found"


def _invalid_payload(case: str) -> dict:
    payload = _payload(f"consult-invalid-{case}", f"submit-invalid-{case}")
    if case == "speaker":
        payload["content"]["segments"][0]["speaker"] = "nurse"
    elif case == "empty":
        payload["content"]["segments"][0]["text"] = "   "
    elif case == "index":
        payload["content"]["segments"][1]["index"] = 9
    elif case == "segment-extra":
        payload["content"]["segments"][0]["timestamp"] = "00:01"
    elif case == "request-extra":
        payload["preview"] = "untrusted"
    elif case == "time":
        payload["ended_at"] = "2026-08-26T09:59:59"
    else:  # pragma: no cover
        raise AssertionError(case)
    return payload


@pytest.mark.parametrize(
    "case", ["speaker", "empty", "index", "segment-extra", "request-extra", "time"]
)
def test_invalid_transcript_requests_fail_closed(clinician_client, case):
    response = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_invalid_payload(case),
    )
    assert response.status_code == 422


def test_transcript_cannot_be_edited_or_reverted(
    clinician_client, monkeypatch
):
    _force_missing_provider(monkeypatch)
    created = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json=_payload("consult-immutable", "submit-immutable"),
    ).json()
    artifact_id = created["source_artifact_id"]

    edit = clinician_client.patch(
        f"/api/artifacts/{artifact_id}",
        json={"content": {"segments": []}, "expected_version": 1},
    )
    revert = clinician_client.post(
        f"/api/artifacts/{artifact_id}/revert",
        json={"to_version": 1, "expected_version": 1},
    )
    assert edit.status_code == 403
    assert revert.status_code == 403


def test_event_api_exposes_explicit_encounter_and_does_not_group_by_date(
    clinician_client, db_session
):
    db_session.add(
        Event(
            event_id="evt_same_day_separate",
            patient_id=fixture.PATIENT_ID,
            clinic_id=fixture.CLINIC_ID,
            event_type="doctor_consult",
            encounter_id="enc_explicitly_separate",
            started_at=datetime(2026, 8, 21, 11, 0),
            ended_at=None,
            created_at=datetime(2026, 8, 21, 11, 1),
        )
    )
    db_session.commit()

    response = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/events")
    assert response.status_code == 200
    by_id = {event["event_id"]: event for event in response.json()}
    assert by_id[fixture.EVT_NURSE_0821]["encounter_id"] == fixture.ENCOUNTER_0821
    assert by_id[fixture.EVT_DOC_0821]["encounter_id"] == fixture.ENCOUNTER_0821
    assert by_id["evt_same_day_separate"]["encounter_id"] == "enc_explicitly_separate"


def test_current_identity_and_clinic_patient_list_handoff(
    clinician_client, patient_client
):
    identity = clinician_client.get("/api/me")
    assert identity.status_code == 200
    assert identity.json() == {
        "user_id": fixture.USER_CLINICIAN_ID,
        "role": "clinician",
        "clinic_id": fixture.CLINIC_ID,
        "patient_id": None,
        "display_name": "Dr. Carol Wong",
        "clinic_name": fixture.CLINIC_NAME,
        "authenticated": True,
    }

    patients = clinician_client.get("/api/patients")
    assert patients.status_code == 200
    assert [patient["patient_id"] for patient in patients.json()] == [
        fixture.PATIENT_ID,
        fixture.PATIENT_B_ID,
    ]
    assert {patient["clinic_id"] for patient in patients.json()} == {fixture.CLINIC_ID}
    assert patient_client.get("/api/patients").status_code == 403


def test_other_clinic_patient_list_is_scoped(client):
    response = client.get(
        "/api/patients", headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}
    )
    assert response.status_code == 200
    assert response.json() == []
