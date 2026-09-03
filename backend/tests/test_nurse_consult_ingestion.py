"""E1 hard gate: Nurse-specific preview and Nurse Consult ingestion."""
from __future__ import annotations

from copy import deepcopy

import pytest
from sqlalchemy import func, select

from app.db import SessionLocal
from app.highlights import extract_text
from app.models import Artifact, AuditLog, Event, Highlight
from seed import fixture


NURSE_RAW = (
    "NURSE: Your blood pressure is elevated at 158 over 96.\n"
    "PATIENT: My headache has been happening almost every day."
)


def _payload(consult_id: str = "nurse-e1-001", ingestion_key: str = "nurse-submit-e1-001") -> dict:
    return {
        "consult_id": consult_id,
        "ingestion_key": ingestion_key,
        "started_at": "2026-08-27T09:00:00",
        "ended_at": "2026-08-27T09:15:00",
        "encounter_id": fixture.ENCOUNTER_0821,
        "content": {
            "segments": [
                {
                    "index": 0,
                    "speaker": "nurse",
                    "text": "Your blood pressure is elevated at 158 over 96.",
                },
                {
                    "index": 1,
                    "speaker": "patient",
                    "text": "My headache has been happening almost every day.",
                },
            ]
        },
    }


def _force_missing_provider(monkeypatch) -> None:
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("Natingale_API_KEY", raising=False)


def test_staff_previews_nurse_labels_without_doctor_mapping(staff_client):
    response = staff_client.post(
        "/api/transcripts/nurse-normalize", json={"raw_text": NURSE_RAW}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["outcome"] == "ACCEPT"
    assert [segment["speaker_candidate"] for segment in body["segments"]] == [
        "nurse",
        "patient",
    ]
    for segment in body["segments"]:
        assert NURSE_RAW[segment["source_start"] : segment["source_end"]] == segment["text"]

    wrong_role = staff_client.post(
        "/api/transcripts/nurse-normalize",
        json={"raw_text": "DOCTOR: I will create a clinical assessment.\nPATIENT: Okay."},
    )
    assert wrong_role.status_code == 200
    assert wrong_role.json()["outcome"] == "NEEDS_REVIEW"
    assert wrong_role.json()["segments"][0]["speaker_candidate"] is None


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        (fixture.USER_STAFF_ID, 200),
        (fixture.USER_CLINICIAN_ID, 403),
        (fixture.USER_PATIENT_ID, 403),
        (fixture.USER_ADMIN_ID, 403),
    ],
)
def test_nurse_preview_is_staff_only(client, user_id, expected):
    response = client.post(
        "/api/transcripts/nurse-normalize",
        headers={"X-User-Id": user_id},
        json={"raw_text": NURSE_RAW},
    )
    assert response.status_code == expected


def test_staff_creates_new_nurse_consult_raw_summary_and_exact_highlights(
    staff_client, db_session, monkeypatch
):
    _force_missing_provider(monkeypatch)
    response = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults", json=_payload()
    )
    assert response.status_code == 200, response.text
    body = response.json()

    event = db_session.get(Event, body["event"]["event_id"])
    raw = db_session.get(Artifact, body["source_artifact_id"])
    summary = db_session.get(Artifact, body["ai_summary_artifact_id"])
    assert event.event_id != fixture.EVT_NURSE_0821
    assert event.event_type == "nurse_consult"
    assert event.encounter_id == fixture.ENCOUNTER_0821
    assert body["event"]["artifact_count"] == 2
    assert raw.artifact_type == "transcript"
    assert raw.author_role == "system" and raw.author_id is None
    assert raw.content == _payload()["content"]
    assert summary.artifact_type == "ai_nurse_consult_summary"
    assert summary.author_role == "system" and summary.author_id is None
    assert summary.provenance_pointer["artifact_id"] == raw.artifact_id
    assert body["generation_method"] == "deterministic_fallback"
    assert body["degraded"] is True
    assert body["fallback_reason"] == "provider_missing"

    for highlight_id in body["highlight_ids"]:
        highlight = db_session.get(Highlight, highlight_id)
        assert highlight.source_artifact_id == raw.artifact_id
        assert extract_text(raw.content, highlight.source_span)

    actions = set(
        db_session.scalars(
            select(AuditLog.action).where(AuditLog.event_id == event.event_id)
        ).all()
    )
    assert {"nurse_consult_create", "source_ingest", "ai_fallback"} <= actions


def test_nurse_raw_is_committed_before_pipeline(staff_client, monkeypatch):
    _force_missing_provider(monkeypatch)
    import app.api.sources as sources

    real_run_pipeline = sources.run_pipeline
    observed: dict[str, bool] = {}

    def asserting_pipeline(db, event, raw, *args, **kwargs):
        with SessionLocal() as independent:
            observed["committed"] = independent.get(Artifact, raw.artifact_id) is not None
        return real_run_pipeline(db, event, raw, *args, **kwargs)

    monkeypatch.setattr(sources, "run_pipeline", asserting_pipeline)
    response = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults",
        json=_payload("nurse-raw-first", "nurse-raw-first-key"),
    )
    assert response.status_code == 200
    assert observed == {"committed": True}


def test_nurse_consult_replay_is_idempotent(staff_client, db_session, monkeypatch):
    _force_missing_provider(monkeypatch)
    payload = _payload("nurse-replay", "nurse-replay-key")
    first = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults", json=payload
    )
    replay = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults", json=payload
    )
    assert first.status_code == replay.status_code == 200
    assert replay.json()["idempotent_replay"] is True
    assert replay.json()["event"]["event_id"] == first.json()["event"]["event_id"]
    event_id = first.json()["event"]["event_id"]
    assert db_session.scalar(
        select(func.count()).select_from(Event).where(Event.event_id == event_id)
    ) == 1
    assert db_session.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.event_id == event_id)
    ) == 2


def test_same_consult_id_does_not_implicitly_group_doctor_and_nurse_events(
    clinician_client, staff_client, monkeypatch
):
    _force_missing_provider(monkeypatch)
    shared_consult_id = "shared-label-not-shared-encounter"
    doctor = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
        json={
            "consult_id": shared_consult_id,
            "ingestion_key": "doctor-shared-label-key",
            "started_at": "2026-08-27T10:00:00",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
            "content": {
                "segments": [
                    {"index": 0, "speaker": "doctor", "text": "Any change?"},
                    {"index": 1, "speaker": "patient", "text": "The headache is better."},
                ]
            },
        },
    )
    nurse_payload = _payload(shared_consult_id, "nurse-shared-label-key")
    nurse_payload.pop("encounter_id")
    nurse = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults",
        json=nurse_payload,
    )
    assert doctor.status_code == nurse.status_code == 200
    assert doctor.json()["encounter_id"] != nurse.json()["encounter_id"]

    explicit_payload = _payload("explicit-nurse-group", "explicit-nurse-group-key")
    explicit_payload["encounter_id"] = doctor.json()["encounter_id"]
    explicitly_grouped = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults",
        json=explicit_payload,
    )
    assert explicitly_grouped.status_code == 200
    assert explicitly_grouped.json()["encounter_id"] == doctor.json()["encounter_id"]


@pytest.mark.parametrize(
    ("user_id", "expected"),
    [
        (fixture.USER_CLINICIAN_ID, 403),
        (fixture.USER_PATIENT_ID, 403),
        (fixture.USER_ADMIN_ID, 403),
        (fixture.USER_CLINICIAN_B_ID, 404),
    ],
)
def test_nurse_consult_rbac_matrix(client, user_id, expected):
    response = client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults",
        headers={"X-User-Id": user_id},
        json=_payload(f"nurse-rbac-{user_id}", f"nurse-rbac-key-{user_id}"),
    )
    assert response.status_code == expected


@pytest.mark.parametrize("case", ["speaker", "empty", "index", "extra", "time"])
def test_nurse_consult_strict_validation(staff_client, case):
    payload = _payload(f"nurse-invalid-{case}", f"nurse-invalid-key-{case}")
    if case == "speaker":
        payload["content"]["segments"][0]["speaker"] = "doctor"
    elif case == "empty":
        payload["content"]["segments"][0]["text"] = "   "
    elif case == "index":
        payload["content"]["segments"][1]["index"] = 9
    elif case == "extra":
        payload["content"]["segments"][0]["timestamp"] = "00:01"
    elif case == "time":
        payload["ended_at"] = "2026-08-27T08:59:59"
    response = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults", json=payload
    )
    assert response.status_code == 422


def test_nurse_consult_conflicting_identity_is_rejected(staff_client, monkeypatch):
    _force_missing_provider(monkeypatch)
    first = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults",
        json=_payload("nurse-identity", "nurse-key-a"),
    )
    second = staff_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/nurse-consults",
        json=_payload("nurse-identity", "nurse-key-b"),
    )
    assert first.status_code == 200
    assert second.status_code == 409
