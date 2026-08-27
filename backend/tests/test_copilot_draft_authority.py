"""D4 editable preview, signed confirmation, and write-authority gates."""
from __future__ import annotations

from sqlalchemy import func, select
from fastapi.testclient import TestClient

from app.copilot_confirmation import issue_confirmation_token
from app.main import app
from app.models import Artifact, AuditLog, Event, Task, User
from seed import fixture

URL = f"/api/patients/{fixture.PATIENT_ID}/copilot/query"


def _preview(client, draft_type: str):
    response = client.post(URL, json={"category": "draft_action", "draft_type": draft_type})
    assert response.status_code == 200
    return response.json()


def _audit_for(db, target_id: str):
    return db.scalar(select(AuditLog).where(AuditLog.target_id == target_id))


def test_draft_action_requires_clinician_selected_type(clinician_client):
    assert clinician_client.post(URL, json={"category": "draft_action"}).status_code == 422


def test_clinician_selected_note_preview_is_editable_and_token_confirmed(clinician_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    before = db_session.scalar(select(func.count()).select_from(Artifact))
    result = _preview(clinician_client, "clinician_note")
    draft = result["draft"]
    assert draft["artifact_type"] == "clinician_note" and draft["patient_visible"] is False
    assert db_session.scalar(select(func.count()).select_from(Artifact)) == before

    edited = {**draft["content"], "plan": "Clinician-edited plan."}
    saved = clinician_client.post(f"/api/events/{draft['event_id']}/notes", json={
        "artifact_type": "clinician_note",
        "content": edited,
        "confirmation_token": draft["confirmation_token"],
    })
    assert saved.status_code == 200
    artifact = saved.json()
    assert artifact["content"] == edited
    assert artifact["author_role"] == "clinician" and artifact["author_id"] == fixture.USER_CLINICIAN_ID
    audit = _audit_for(db_session, artifact["artifact_id"])
    assert audit.details["draft_origin"] == "copilot"
    assert audit.details["evidence_count"] == 1 and audit.details["confirmation_id"]


def test_client_cannot_self_assert_copilot_origin(clinician_client):
    response = clinician_client.post(f"/api/events/{fixture.EVT_REVIEW_0826}/notes", json={
        "artifact_type": "clinician_note", "content": {"body": "manual"}, "draft_origin": "copilot",
    })
    assert response.status_code == 422


def test_forged_wrong_event_and_wrong_type_tokens_are_rejected(clinician_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    draft = _preview(clinician_client, "clinician_note")["draft"]
    forged = draft["confirmation_token"][:-1] + ("A" if draft["confirmation_token"][-1] != "A" else "B")
    payload = {"artifact_type": "clinician_note", "content": draft["content"], "confirmation_token": forged}
    assert clinician_client.post(f"/api/events/{draft['event_id']}/notes", json=payload).status_code == 422
    payload["confirmation_token"] = draft["confirmation_token"]
    assert clinician_client.post(f"/api/events/{fixture.EVT_DOC_0821}/notes", json=payload).status_code == 422
    payload["artifact_type"] = "patient_instruction"
    payload["content"] = {"instruction": "Clear patient-facing guidance."}
    assert clinician_client.post(f"/api/events/{draft['event_id']}/notes", json=payload).status_code == 422


def test_confirmation_token_is_bound_to_actor(clinician_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    draft = _preview(clinician_client, "clinician_note")["draft"]
    db_session.add(User(
        user_id="usr_clinician_token_other", clinic_id=fixture.CLINIC_ID,
        name="Dr. Token Other", role="clinician", patient_id=None,
    ))
    db_session.commit()
    with TestClient(app, headers={"X-User-Id": "usr_clinician_token_other"}) as other:
        response = other.post(f"/api/events/{draft['event_id']}/notes", json={
            "artifact_type": "clinician_note", "content": draft["content"],
            "confirmation_token": draft["confirmation_token"],
        })
    assert response.status_code == 422


def test_expired_confirmation_token_is_rejected(clinician_client, db_session):
    event = db_session.get(Event, fixture.EVT_REVIEW_0826)
    evidence = [{
        "event_id": event.event_id,
        "artifact_id": fixture.ART_REVIEW_NOTE,
        "span": {"kind": "section", "index": "assessment", "offset": [0, 34]},
        "quote_sha256": "unused-because-expired-first",
    }]
    token = issue_confirmation_token(
        actor_id=fixture.USER_CLINICIAN_ID, clinic_id=event.clinic_id,
        patient_id=event.patient_id, event_id=event.event_id,
        draft_type="clinician_note", evidence=evidence,
        template_content={"body": "draft"}, now=0,
    )
    response = clinician_client.post(f"/api/events/{event.event_id}/notes", json={
        "artifact_type": "clinician_note", "content": {"body": "edited"}, "confirmation_token": token,
    })
    assert response.status_code == 422


def test_task_confirmation_binds_server_visibility_event_and_evidence(clinician_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    before = db_session.scalar(select(func.count()).select_from(Task))
    result = _preview(clinician_client, "task")
    draft = result["draft"]
    source = next(card for card in result["evidence"] if card["evidence_id"] == draft["evidence_ids"][0])
    base = {
        "title": "Clinician-edited task", "description": draft["content"]["description"],
        "assigned_role": "clinician", "assigned_user_id": None, "patient_visible": False,
        "due_at": None, "source_artifact_id": source["artifact_id"], "source_span": source["span"],
        "confirmation_token": draft["confirmation_token"],
    }
    tampered = {**base, "patient_visible": True}
    assert clinician_client.post(f"/api/events/{draft['event_id']}/tasks", json=tampered).status_code == 422
    assert db_session.scalar(select(func.count()).select_from(Task)) == before
    created = clinician_client.post(f"/api/events/{draft['event_id']}/tasks", json=base)
    assert created.status_code == 200 and created.json()["status"] == "open"
    audit = _audit_for(db_session, created.json()["task_id"])
    assert audit.details["status"] == "open" and audit.details["draft_origin"] == "copilot"


def test_patient_instruction_requires_edit_then_uses_clinician_authority(clinician_client, patient_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    draft = _preview(clinician_client, "patient_instruction")["draft"]
    unedited = clinician_client.post(f"/api/events/{draft['event_id']}/notes", json={
        "artifact_type": "patient_instruction", "content": draft["content"],
        "confirmation_token": draft["confirmation_token"],
    })
    assert unedited.status_code == 422
    edited = {"instruction": "Continue your current medicine and contact the clinic if symptoms worsen.", "follow_up": "Attend the planned follow-up."}
    saved = clinician_client.post(f"/api/events/{draft['event_id']}/notes", json={
        "artifact_type": "patient_instruction", "content": edited,
        "confirmation_token": draft["confirmation_token"],
    })
    assert saved.status_code == 200
    assert saved.json()["author_role"] == "clinician" and saved.json()["content"] == edited
    assert _audit_for(db_session, saved.json()["artifact_id"]).details["draft_origin"] == "copilot"
    patient_view = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view")
    assert patient_view.status_code == 200
    assert "EDIT REQUIRED" not in str(patient_view.json())
    assert edited["instruction"] in str(patient_view.json())
