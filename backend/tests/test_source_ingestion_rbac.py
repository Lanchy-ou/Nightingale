"""M4: source ingestion RBAC + idempotency (direct API)."""
from __future__ import annotations

from sqlalchemy import select

from app.models import Artifact
from seed import fixture


def test_patient_creates_own_session_reduced_response(patient_client):
    r = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/sessions",
        json={
            "session_id": "sess-1",
            "event_type": "patient_followup",
            "started_at": "2026-08-26T10:00:00",
            "content": {"messages": [{"id": "m1", "speaker": "patient", "text": "Headache is worse."}]},
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["event_id"] and body["source_artifact_id"]
    assert body["processing_status"] == "completed"
    # patient reduced response leaks no internal ids
    assert "ai_summary_artifact_id" not in body
    assert "highlight_ids" not in body


def test_patient_session_replay_keeps_reduced_response(patient_client):
    payload = {
        "session_id": "sess-patient-replay",
        "event_type": "patient_followup",
        "started_at": "2026-08-26T10:00:00",
        "content": {"messages": [{"id": "m1", "speaker": "patient", "text": "Headache is worse."}]},
    }
    first = patient_client.post(f"/api/patients/{fixture.PATIENT_ID}/sessions", json=payload)
    replay = patient_client.post(f"/api/patients/{fixture.PATIENT_ID}/sessions", json=payload)

    assert first.status_code == replay.status_code == 200
    assert replay.json() == first.json()
    assert "ai_summary_artifact_id" not in replay.json()
    assert "highlight_ids" not in replay.json()


def test_patient_cannot_create_other_patient_session(patient_client):
    r = patient_client.post(
        f"/api/patients/{fixture.PATIENT_B_ID}/sessions",
        json={
            "session_id": "sess-x",
            "event_type": "patient_followup",
            "started_at": "2026-08-26T10:00:00",
            "content": {"messages": [{"id": "m1", "speaker": "patient", "text": "hi"}]},
        },
    )
    assert r.status_code == 404


def test_staff_nurse_transcript_ok(staff_client):
    r = staff_client.post(
        f"/api/events/{fixture.EVT_NURSE_0821}/sources",
        json={
            "ingestion_key": "k-nurse-1",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "nurse", "text": "BP elevated."}]},
        },
    )
    assert r.status_code == 200
    assert r.json()["ai_summary_artifact_id"]
    assert r.json()["idempotent_replay"] is False


def test_staff_cannot_doctor_transcript(staff_client):
    r = staff_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/sources",
        json={
            "ingestion_key": "k-x",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "doctor", "text": "hi"}]},
        },
    )
    assert r.status_code == 422


def test_clinician_doctor_transcript_ok(clinician_client):
    r = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/sources",
        json={
            "ingestion_key": "k-doc-1",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "doctor", "text": "Blood test ordered."}]},
        },
    )
    assert r.status_code == 200


def test_clinician_cannot_nurse_transcript(clinician_client):
    r = clinician_client.post(
        f"/api/events/{fixture.EVT_NURSE_0821}/sources",
        json={
            "ingestion_key": "k-y",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "nurse", "text": "hi"}]},
        },
    )
    assert r.status_code == 422


def test_admin_cannot_ingest(admin_client):
    r = admin_client.post(
        f"/api/events/{fixture.EVT_NURSE_0821}/sources",
        json={
            "ingestion_key": "k-z",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "nurse", "text": "hi"}]},
        },
    )
    assert r.status_code == 403


def test_patient_cannot_use_source_endpoint(patient_client):
    r = patient_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/sources",
        json={
            "ingestion_key": "k-p",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "doctor", "text": "hi"}]},
        },
    )
    assert r.status_code == 403


def test_cross_clinic_source_404(client):
    r = client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/sources",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
        json={
            "ingestion_key": "k-cross",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 1, "speaker": "doctor", "text": "hi"}]},
        },
    )
    assert r.status_code == 404


def test_source_idempotent_replay(staff_client, db_session):
    payload = {
        "ingestion_key": "k-idem",
        "artifact_type": "transcript",
        "content": {"segments": [{"index": 1, "speaker": "nurse", "text": "BP elevated."}]},
    }
    r1 = staff_client.post(f"/api/events/{fixture.EVT_NURSE_0821}/sources", json=payload)
    r2 = staff_client.post(f"/api/events/{fixture.EVT_NURSE_0821}/sources", json=payload)
    assert r1.status_code == 200 and r2.status_code == 200
    assert r2.json()["idempotent_replay"] is True
    assert r2.json()["source_artifact_id"] == r1.json()["source_artifact_id"]
    assert r2.json()["ai_summary_artifact_id"] == r1.json()["ai_summary_artifact_id"]

    key = f"{fixture.CLINIC_ID}:{fixture.EVT_NURSE_0821}:k-idem"
    raws = db_session.scalars(select(Artifact).where(Artifact.ingestion_key == key)).all()
    assert len(raws) == 1
