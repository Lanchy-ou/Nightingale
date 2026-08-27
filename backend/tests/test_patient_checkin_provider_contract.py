from __future__ import annotations

import json

from sqlalchemy import select

from app.models import Artifact, Highlight, PatientCheckInMessage
from app.schemas import (
    CheckInSummaryCandidate,
    CheckInSummaryResult,
    CheckInTurnResult,
)
from seed import fixture


class CapturingClient:
    def __init__(self):
        self.turn_payload = None
        self.summary_payload = None

    def checkin_turn(self, redacted, clarification_count):
        self.turn_payload = redacted
        latest = [m for m in redacted.content["messages"] if m["speaker"] == "patient"][-1]
        return CheckInTurnResult(
            acknowledgement="Thanks for explaining that.",
            next_question="How severe is the main symptom now?",
            question_type="severity",
            conversation_action="continue",
            referenced_patient_message_ids=[latest["id"]],
        )

    def checkin_summary(self, redacted):
        self.summary_payload = redacted
        first = redacted.content["messages"][0]
        return CheckInSummaryResult(
            summary=first["text"],
            referenced_patient_message_ids=[m["id"] for m in redacted.content["messages"]],
            candidates=[CheckInSummaryCandidate(
                text="Patient-reported symptom update",
                patient_message_id=first["id"],
                quote=first["text"],
                risk_reason="Patient described a symptom",
                entity_type="symptom",
                assertion_value=None,
                symptom_change=True,
            )],
        )


def test_turn_and_summary_provider_receive_redacted_patient_context_and_restore_exact_span(
    patient_client, db_session, monkeypatch
):
    client = CapturingClient()
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setattr("app.checkins.build_client", lambda *_args, **_kwargs: client)
    session_id = "checkin-redaction-contract-001"
    patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )
    raw_text = "Alice Tan says the headache is worse. Call me at 012-3456789."
    sent = patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-redaction-message-001",
            "intent": "answer",
            "text": raw_text,
        },
    )
    assert sent.status_code == 200, sent.text
    turn_json = json.dumps(client.turn_payload.content)
    assert "Alice Tan" not in turn_json and "012-3456789" not in turn_json
    assert "[NAME_1]" in turn_json and "[PHONE_1]" in turn_json
    assert db_session.get(PatientCheckInMessage, "patient-redaction-message-001").text == raw_text

    patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-redaction-end-001",
            "intent": "no_more",
            "text": "",
        },
    )
    submitted = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert submitted.status_code == 200, submitted.text
    summary_json = json.dumps(client.summary_payload.content)
    assert "Alice Tan" not in summary_json and "012-3456789" not in summary_json
    raw = db_session.scalar(select(Artifact).where(
        Artifact.event_id == submitted.json()["event_id"],
        Artifact.artifact_type == "raw_conversation",
    ))
    highlight = db_session.scalar(select(Highlight).where(
        Highlight.event_id == submitted.json()["event_id"]
    ))
    assert highlight.source_span["index"] == "patient-redaction-message-001"
    assert raw.content["messages"][1]["text"] == raw_text


def test_ai_messages_and_unconfirmed_draft_cannot_be_fact_sources(
    patient_client, clinician_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-ai-source-ban-001"
    started = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    ).json()
    patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-ai-source-ban-001",
            "intent": "answer",
            "text": "My headache is better.",
        },
    )
    assert not db_session.scalars(select(Artifact).where(
        Artifact.event_id == started["event_id"],
        Artifact.artifact_type == "ai_patient_session_summary",
    )).all()
    assert not db_session.scalars(select(Highlight).where(
        Highlight.event_id == started["event_id"]
    )).all()

    patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={"message_id": "patient-ai-source-end-001", "intent": "no_more", "text": ""},
    )
    patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    raw = db_session.scalar(select(Artifact).where(
        Artifact.event_id == started["event_id"], Artifact.artifact_type == "raw_conversation"
    ))
    for highlight in db_session.scalars(select(Highlight).where(
        Highlight.event_id == started["event_id"]
    )).all():
        source = next(message for message in raw.content["messages"] if message["id"] == highlight.source_span["index"])
        assert source["speaker"] == "patient"

    copilot = clinician_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/copilot/query",
        json={"category": "find_evidence", "question": "What has changed since your last update"},
    )
    assert copilot.status_code == 200
    assert all(
        card["quote"] != "What has changed since your last update?"
        for card in copilot.json()["evidence"]
    )
