"""D4 previews never persist; confirmation retains existing write authority."""
from sqlalchemy import func, select

from app.models import Artifact, AuditLog, Task
from seed import fixture

URL = f"/api/patients/{fixture.PATIENT_ID}/copilot/query"


def test_draft_is_preview_only_then_confirmed_through_normal_note_api(clinician_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    before = db_session.scalar(select(func.count()).select_from(Artifact))
    response = clinician_client.post(URL, json={"category": "draft_action"})
    assert response.status_code == 200
    draft = response.json()["draft"]
    assert draft and draft["artifact_type"] == "clinician_note"
    assert db_session.scalar(select(func.count()).select_from(Artifact)) == before

    saved = clinician_client.post(
        f"/api/events/{draft['event_id']}/notes",
        json={"artifact_type": "clinician_note", "content": draft["content"], "draft_origin": "copilot"},
    )
    assert saved.status_code == 200
    artifact = saved.json()
    assert artifact["author_role"] == "clinician" and artifact["author_id"] == fixture.USER_CLINICIAN_ID
    audit = db_session.scalar(select(AuditLog).where(AuditLog.target_id == artifact["artifact_id"]))
    assert audit.details == {"draft_origin": "copilot"}


def test_copilot_task_preview_does_not_complete_or_create_a_task(clinician_client, db_session, monkeypatch):
    from app.api import copilot as copilot_api
    from app.copilot_models import CopilotProviderDraft, CopilotProviderResult

    class TaskProposal:
        def copilot(self, redacted, category):
            return CopilotProviderResult(draft=CopilotProviderDraft(artifact_type="task", evidence_ids=[redacted.content["evidence"][0]["evidence_id"]]))

    before = db_session.scalar(select(func.count()).select_from(Task))
    monkeypatch.setattr(copilot_api, "build_client", lambda provider: TaskProposal())
    result = clinician_client.post(URL, json={"category": "draft_action"}).json()
    assert result["draft"]["artifact_type"] == "task"
    assert db_session.scalar(select(func.count()).select_from(Task)) == before

    source = next(card for card in result["evidence"] if card["evidence_id"] == result["draft"]["evidence_ids"][0])
    created = clinician_client.post(f"/api/events/{result['draft']['event_id']}/tasks", json={
        "title": result["draft"]["content"]["title"], "description": result["draft"]["content"]["description"],
        "assigned_role": "clinician", "assigned_user_id": None, "patient_visible": False, "due_at": None,
        "source_artifact_id": source["artifact_id"], "source_span": source["span"], "draft_origin": "copilot",
    })
    assert created.status_code == 200
    audit = db_session.scalar(select(AuditLog).where(AuditLog.target_id == created.json()["task_id"]))
    assert audit.details == {"status": "open", "draft_origin": "copilot"}


def test_confirmed_patient_instruction_is_clinician_authored_and_audited(clinician_client, db_session, monkeypatch):
    from app.api import copilot as copilot_api
    from app.copilot_models import CopilotProviderDraft, CopilotProviderResult

    class InstructionProposal:
        def copilot(self, redacted, category):
            return CopilotProviderResult(draft=CopilotProviderDraft(artifact_type="patient_instruction", evidence_ids=[redacted.content["evidence"][0]["evidence_id"]]))

    monkeypatch.setattr(copilot_api, "build_client", lambda provider: InstructionProposal())
    result = clinician_client.post(URL, json={"category": "draft_action"}).json()
    draft = result["draft"]
    saved = clinician_client.post(f"/api/events/{draft['event_id']}/notes", json={
        "artifact_type": "patient_instruction", "content": draft["content"], "draft_origin": "copilot",
    })
    assert saved.status_code == 200
    assert saved.json()["author_role"] == "clinician"
    audit = db_session.scalar(select(AuditLog).where(AuditLog.target_id == saved.json()["artifact_id"]))
    assert audit.details == {"draft_origin": "copilot"}
