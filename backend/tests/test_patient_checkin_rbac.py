from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed import fixture


def test_patient_owns_checkin_and_other_patient_gets_uniform_404(patient_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-owner-scope-001"
    created = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )
    assert created.status_code == 200
    with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_B_ID}) as other_patient:
        assert other_patient.get(f"/api/check-ins/{session_id}").status_code == 404
        assert other_patient.post(
            f"/api/check-ins/{session_id}/messages",
            json={"message_id": "other-patient-message-001", "intent": "answer", "text": "probe"},
        ).status_code == 404


def test_clinical_roles_cannot_author_patient_messages_and_hidden_draft_is_404(
    patient_client, clinician_client, staff_client, admin_client, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-clinical-read-boundary-001"
    started = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )
    assert started.status_code == 200
    event_id = started.json()["event_id"]
    patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-unconfirmed-sentinel-001",
            "intent": "answer",
            "text": "UNCONFIRMED_CHECKIN_SENTINEL headache update",
        },
    )
    for client in (clinician_client, staff_client, admin_client):
        assert client.get(f"/api/check-ins/{session_id}").status_code == 404
        assert client.post(
            f"/api/check-ins/{session_id}/messages",
            json={"message_id": "clinical-author-message", "intent": "answer", "text": "probe"},
        ).status_code == 404
        assert client.get(f"/api/events/{event_id}/audit").status_code == (403 if client is admin_client else 404)
        assert client.get(f"/api/events/{event_id}/comments").status_code == (403 if client is admin_client else 404)

    assert clinician_client.post(
        f"/api/events/{event_id}/notes",
        json={"artifact_type": "clinician_note", "content": {"assessment": "probe"}},
    ).status_code == 404
    assert clinician_client.post(
        f"/api/events/{event_id}/tasks",
        json={
            "title": "probe", "description": "", "assigned_role": "clinician",
            "assigned_user_id": None, "patient_visible": False, "due_at": None,
            "source_artifact_id": None, "source_span": None,
        },
    ).status_code == 404
    assert clinician_client.post(
        f"/api/events/{event_id}/sources",
        json={
            "ingestion_key": "hidden-draft-probe",
            "artifact_type": "transcript",
            "content": {"segments": [{"index": 0, "speaker": "patient", "text": "probe"}]},
        },
    ).status_code == 404
    copilot = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/copilot/query",
        json={"category": "find_evidence", "question": "UNCONFIRMED_CHECKIN_SENTINEL"},
    )
    assert copilot.status_code == 200
    assert "UNCONFIRMED_CHECKIN_SENTINEL" not in copilot.text


def test_cross_clinic_clinician_cannot_read_visible_checkin(patient_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-cross-clinic-001"
    started = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    ).json()
    patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-cross-clinic-safety",
            "intent": "answer",
            "text": "I cannot breathe.",
        },
    )
    with TestClient(app, headers={"X-User-Id": "usr_clinician_02"}) as other_clinic:
        assert other_clinic.get(f"/api/check-ins/{session_id}").status_code == 404
        assert other_clinic.get(f"/api/events/{started['event_id']}/artifacts").status_code == 404
