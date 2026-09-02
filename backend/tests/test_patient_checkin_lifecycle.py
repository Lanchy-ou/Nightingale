from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import threading
import time

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.highlights import extract_text
from app.models import (
    Artifact,
    Event,
    Highlight,
    PatientCheckInMessage,
    PatientCheckInSession,
    Task,
)
from seed import fixture


def _start(client, session_id="checkin-lifecycle-001"):
    return client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins",
        json={"session_id": session_id},
    )


def _send(client, session_id, message_id, text, intent="answer"):
    return client.post(
        f"/api/check-ins/{session_id}/messages",
        json={"message_id": message_id, "intent": intent, "text": text},
    )


def test_start_resume_and_draft_hidden_from_timeline(patient_client, clinician_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    first = _start(patient_client)
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["status"] == "active"
    assert body["clarification_count"] == 1
    assert body["messages"][0]["role"] == "ai"
    assert body["messages"][0]["question_type"] == "change"
    assert body["formal_summary_created"] is False

    resumed = _start(patient_client, "a-different-request-id")
    assert resumed.status_code == 200
    assert resumed.json()["session_id"] == body["session_id"]
    assert resumed.json()["resumed"] is True

    timeline_ids = {
        event["event_id"]
        for event in clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/events").json()
    }
    assert body["event_id"] not in timeline_ids
    assert clinician_client.get(f"/api/events/{body['event_id']}/artifacts").status_code == 404


def test_concurrent_start_requests_resume_one_active_session(monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")

    def start_once(index: int):
        with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_ID}) as client:
            return _start(client, f"checkin-concurrent-start-00{index}")

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(start_once, (1, 2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert len({response.json()["session_id"] for response in responses}) == 1


def test_message_raw_first_idempotent_and_payload_conflict(patient_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-idempotency-001"
    assert _start(patient_client, session_id).status_code == 200
    first = _send(
        patient_client,
        session_id,
        "patient-message-001",
        "My headache is better, but I still feel nauseous.",
        "supplement",
    )
    assert first.status_code == 200, first.text
    first_body = first.json()
    patient_rows = [m for m in first_body["messages"] if m["role"] == "patient"]
    ai_rows = [m for m in first_body["messages"] if m["response_to_message_id"] == "patient-message-001"]
    assert len(patient_rows) == 1
    assert len(ai_rows) == 1
    assert ai_rows[0]["generation_method"] == "mock"

    replay = _send(
        patient_client,
        session_id,
        "patient-message-001",
        "My headache is better, but I still feel nauseous.",
        "supplement",
    )
    assert replay.status_code == 200
    assert replay.json()["messages"] == first_body["messages"]
    assert len(db_session.scalars(select(PatientCheckInMessage).where(
        PatientCheckInMessage.session_id == session_id
    )).all()) == len(first_body["messages"])

    conflict = _send(
        patient_client,
        session_id,
        "patient-message-001",
        "Different payload",
        "supplement",
    )
    assert conflict.status_code == 409


def test_concurrent_same_message_save_is_idempotent(db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-concurrent-save-001"
    with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_ID}) as setup_client:
        assert _start(setup_client, session_id).status_code == 200

    def save_once():
        with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_ID}) as client:
            return client.post(
                f"/api/check-ins/{session_id}/messages/save",
                json={
                    "message_id": "patient-concurrent-save-001",
                    "intent": "answer",
                    "text": "My nausea is still present.",
                },
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _index: save_once(), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    rows = db_session.scalars(select(PatientCheckInMessage).where(
        PatientCheckInMessage.message_id == "patient-concurrent-save-001"
    )).all()
    assert len(rows) == 1


def test_two_phase_ui_save_commits_raw_before_ai_processing(patient_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-two-phase-save-001"
    started = _start(patient_client, session_id).json()
    saved = patient_client.post(
        f"/api/check-ins/{session_id}/messages/save",
        json={
            "message_id": "patient-two-phase-message-001",
            "intent": "answer",
            "text": "My nausea is still present.",
        },
    )
    assert saved.status_code == 200
    assert saved.json()["messages"][-1]["processing_status"] == "saved"
    assert not any(
        message["response_to_message_id"] == "patient-two-phase-message-001"
        for message in saved.json()["messages"]
    )
    raw = db_session.scalar(select(Artifact).where(
        Artifact.event_id == started["event_id"], Artifact.artifact_type == "raw_conversation"
    ))
    assert any(message["id"] == "patient-two-phase-message-001" for message in raw.content["messages"])

    processed = patient_client.post(
        f"/api/check-ins/{session_id}/messages/patient-two-phase-message-001/process",
        json={},
    )
    assert processed.status_code == 200
    original = processed.json()["messages"]
    replay = patient_client.post(
        f"/api/check-ins/{session_id}/messages/patient-two-phase-message-001/process",
        json={},
    )
    assert replay.status_code == 200
    assert replay.json()["messages"] == original


class _SlowTurnClient:
    def __init__(self):
        self.calls = 0
        self.lock = threading.Lock()

    def checkin_turn(self, redacted, *_args, **_kwargs):
        from app.schemas import CheckInTurnResult

        with self.lock:
            self.calls += 1
        time.sleep(0.2)
        latest = [
            message for message in redacted.content["messages"]
            if message.get("speaker") == "patient"
        ][-1]
        return CheckInTurnResult(
            acknowledgement="Thanks for explaining that.",
            next_question="How severe is the main symptom now?",
            question_type="severity",
            conversation_action="continue",
            referenced_patient_message_ids=[latest["id"]],
        )


def test_concurrent_process_replay_waits_for_one_original_ai_result(patient_client, monkeypatch):
    client = _SlowTurnClient()
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setattr("app.checkins.build_client", lambda *_args, **_kwargs: client)
    session_id = "checkin-concurrent-process-001"
    assert _start(patient_client, session_id).status_code == 200
    saved = patient_client.post(
        f"/api/check-ins/{session_id}/messages/save",
        json={
            "message_id": "patient-concurrent-process-001",
            "intent": "answer",
            "text": "My headache is worse.",
        },
    )
    assert saved.status_code == 200

    def process_once():
        with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_ID}) as request_client:
            return request_client.post(
                f"/api/check-ins/{session_id}/messages/patient-concurrent-process-001/process",
                json={},
            )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = list(executor.map(lambda _index: process_once(), range(2)))
    assert [response.status_code for response in responses] == [200, 200]
    assert responses[0].json()["messages"] == responses[1].json()["messages"]
    assert client.calls == 1


def test_finish_resume_abandon_lifecycle(patient_client, clinician_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-state-flow-001"
    started = _start(patient_client, session_id).json()
    finished = patient_client.post(
        f"/api/check-ins/{session_id}/finish", json={"expected_status": "active"}
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "awaiting_confirmation"
    assert finished.json()["formal_summary_created"] is False

    resumed = patient_client.post(
        f"/api/check-ins/{session_id}/resume",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert resumed.status_code == 200
    assert resumed.json()["status"] == "active"

    abandoned = patient_client.post(
        f"/api/check-ins/{session_id}/abandon", json={"expected_status": "active"}
    )
    assert abandoned.status_code == 200
    assert abandoned.json()["status"] == "abandoned"
    timeline_ids = {
        event["event_id"]
        for event in clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/events").json()
    }
    assert started["event_id"] not in timeline_ids


def test_confirm_creates_summary_highlights_and_exact_patient_message_spans(
    patient_client, clinician_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-submit-provenance-001"
    started = _start(patient_client, session_id).json()
    assert _send(
        patient_client,
        session_id,
        "patient-message-submit-001",
        "My headache is better today and the blood test is completed.",
    ).status_code == 200
    # Patient explicitly ends information collection.
    ended = _send(
        patient_client,
        session_id,
        "patient-message-submit-002",
        "I have nothing else to add.",
        "no_more",
    )
    assert ended.status_code == 200
    assert ended.json()["status"] == "awaiting_confirmation"
    assert ended.json()["formal_summary_created"] is False

    submitted = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["status"] == "submitted"
    assert submitted.json()["formal_summary_created"] is True

    event = db_session.get(Event, started["event_id"])
    artifacts = db_session.scalars(select(Artifact).where(Artifact.event_id == event.event_id)).all()
    raw = next(a for a in artifacts if a.artifact_type == "raw_conversation")
    summary = next(a for a in artifacts if a.artifact_type == "ai_patient_session_summary")
    assert summary.author_role == "system" and summary.author_id is None
    assert set(summary.content["patient_message_ids"]) == {
        "patient-message-submit-001", "patient-message-submit-002"
    }
    assert all(fact["patient_message_id"].startswith("patient-message-submit") for fact in summary.content["source_facts"])

    highlights = db_session.scalars(select(Highlight).where(Highlight.event_id == event.event_id)).all()
    assert highlights
    for highlight in (item for item in highlights if item.task_id is None):
        assert isinstance(highlight.source_span["index"], str)
        source_message = next(
            message for message in raw.content["messages"]
            if message["id"] == highlight.source_span["index"]
        )
        assert source_message["speaker"] == "patient"
        assert extract_text(raw.content, highlight.source_span)

    timeline_ids = {
        row["event_id"]
        for row in clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/events").json()
    }
    assert event.event_id in timeline_ids
    clinical_artifacts = clinician_client.get(f"/api/events/{event.event_id}/artifacts").json()
    assert {a["artifact_type"] for a in clinical_artifacts} == {
        "raw_conversation", "ai_patient_session_summary"
    }

    replay = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert replay.status_code == 200
    assert replay.json()["status"] == "submitted"
    assert len(db_session.scalars(select(Artifact).where(
        Artifact.event_id == event.event_id,
        Artifact.artifact_type == "ai_patient_session_summary",
    )).all()) == 1


def test_checkin_never_changes_task_or_clinical_artifacts(patient_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    task_statuses = {task.task_id: task.status for task in db_session.scalars(select(Task)).all()}
    protected = {
        artifact.artifact_id: artifact.content
        for artifact in db_session.scalars(
            select(Artifact).where(Artifact.artifact_type.in_({"clinician_note", "patient_instruction"}))
        ).all()
    }
    session_id = "checkin-no-authority-001"
    _start(patient_client, session_id)
    _send(
        patient_client,
        session_id,
        "patient-message-task-001",
        "I completed the blood test. Should I change my medicine dose?",
    )
    _send(patient_client, session_id, "patient-message-task-002", "", "no_more")
    patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    db_session.expire_all()
    current_tasks = db_session.scalars(select(Task)).all()
    assert {
        task.task_id: task.status for task in current_tasks if task.task_id in task_statuses
    } == task_statuses
    review_tasks = [task for task in current_tasks if task.task_id not in task_statuses]
    assert {task.task_kind for task in review_tasks} == {
        "patient_report_review",
        "clinician_priority_review",
    }
    assert all(task.creation_method == "system_routed" for task in review_tasks)
    for artifact_id, content in protected.items():
        assert db_session.get(Artifact, artifact_id).content == content


def test_summary_keeps_late_correction_after_more_than_four_patient_messages(
    patient_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-summary-correction-001"
    started = _start(patient_client, session_id).json()
    messages = (
        ("patient-summary-correction-001", "My headache is 4 out of 10.", "answer"),
        ("patient-summary-correction-002", "I still feel nauseous.", "supplement"),
        ("patient-summary-correction-003", "I completed the blood test.", "answer"),
        ("patient-summary-correction-004", "My main concern is dizziness.", "answer"),
        ("patient-summary-correction-005", "Correction: the headache is 3 out of 10, not 4.", "correction"),
    )
    for message_id, text, intent in messages:
        current = _send(patient_client, session_id, message_id, text, intent)
        assert current.status_code == 200
        if current.json()["status"] == "awaiting_confirmation" and message_id != messages[-1][0]:
            patient_client.post(
                f"/api/check-ins/{session_id}/resume",
                json={"expected_status": "awaiting_confirmation"},
            )
    submitted = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert submitted.status_code == 200
    summary = db_session.scalar(select(Artifact).where(
        Artifact.event_id == started["event_id"],
        Artifact.artifact_type == "ai_patient_session_summary",
    ))
    assert "Correction: the headache is 3 out of 10, not 4." in summary.content["summary"]
    assert set(summary.content["patient_message_ids"]) == {
        message_id for message_id, _text, _intent in messages
    }
