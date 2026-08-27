from __future__ import annotations

from sqlalchemy import select

from app.llm_client import InvalidOutputError, ProviderProtocolError
from app.models import Artifact, Highlight, PatientCheckInMessage, PatientCheckInSession
from app.schemas import CheckInTurnResult
from seed import fixture


def _start(client, session_id):
    return client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )


def _send(client, session_id, message_id, text, intent="answer"):
    return client.post(
        f"/api/check-ins/{session_id}/messages",
        json={"message_id": message_id, "intent": intent, "text": text},
    )


def test_safety_escalation_is_deterministic_stops_questions_and_calls_no_llm(
    patient_client, clinician_client, db_session, monkeypatch
):
    session_id = "checkin-safety-rule-001"
    started = _start(patient_client, session_id).json()

    def forbidden_provider(*_args, **_kwargs):
        raise AssertionError("safety rules must run without an LLM")

    monkeypatch.setattr("app.checkins.build_client", forbidden_provider)
    response = _send(
        patient_client,
        session_id,
        "patient-safety-message-001",
        "I have severe chest pain and cannot breathe.",
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "safety_escalated"
    assert body["safety_escalated"] is True
    assert "has not sent a notification" in body["safety_message"]
    assert body["messages"][-1]["conversation_action"] == "safety_escalate"
    assert body["messages"][-1]["question_type"] is None
    assert _send(patient_client, session_id, "patient-safety-message-002", "more").status_code == 409
    assert not db_session.scalars(select(Artifact).where(
        Artifact.event_id == started["event_id"],
        Artifact.artifact_type == "ai_patient_session_summary",
    )).all()
    assert not db_session.scalars(select(Highlight).where(Highlight.event_id == started["event_id"])).all()
    timeline_ids = {
        event["event_id"]
        for event in clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/events").json()
    }
    assert started["event_id"] in timeline_ids


class BrokenClient:
    def checkin_turn(self, *_args, **_kwargs):
        raise ProviderProtocolError("network payload must not escape")


def test_provider_failure_keeps_raw_and_deterministic_fallback_completes_turn(
    patient_client, db_session, monkeypatch
):
    session_id = "checkin-provider-failure-001"
    started = _start(patient_client, session_id).json()
    monkeypatch.setattr("app.checkins.build_client", lambda *_args, **_kwargs: BrokenClient())
    response = _send(
        patient_client,
        session_id,
        "patient-provider-message-001",
        "My headache is worse today.",
    )
    assert response.status_code == 200
    ai = next(
        message for message in response.json()["messages"]
        if message["response_to_message_id"] == "patient-provider-message-001"
    )
    assert ai["generation_method"] == "deterministic_fallback"
    assert ai["degraded"] is True
    raw = db_session.scalar(select(Artifact).where(
        Artifact.event_id == started["event_id"], Artifact.artifact_type == "raw_conversation"
    ))
    assert any(message["id"] == "patient-provider-message-001" for message in raw.content["messages"])


class FabricatingClient:
    def checkin_turn(self, *_args, **_kwargs):
        return CheckInTurnResult(
            acknowledgement="Thanks.",
            next_question="How severe is it?",
            question_type="severity",
            conversation_action="continue",
            referenced_patient_message_ids=["ai-or-invented-message"],
        )


def test_invalid_provider_reference_falls_back(patient_client, monkeypatch):
    session_id = "checkin-invalid-provider-001"
    _start(patient_client, session_id)
    monkeypatch.setattr("app.checkins.build_client", lambda *_args, **_kwargs: FabricatingClient())
    response = _send(
        patient_client,
        session_id,
        "patient-invalid-provider-message-001",
        "I want to add a concern.",
    )
    ai = response.json()["messages"][-1]
    assert ai["generation_method"] == "deterministic_fallback"
    assert ai["referenced_patient_message_ids"] == ["patient-invalid-provider-message-001"]


class StaleReferenceClient:
    def checkin_turn(self, redacted, *_args, **_kwargs):
        patient_ids = [
            message["id"]
            for message in redacted.content["messages"]
            if message.get("speaker") == "patient"
        ]
        return CheckInTurnResult(
            acknowledgement="Thanks for the earlier information.",
            next_question="How severe is it?",
            question_type="severity",
            conversation_action="continue",
            referenced_patient_message_ids=[patient_ids[0]],
        )


def test_provider_must_reference_newest_patient_message_or_fall_back(patient_client, monkeypatch):
    session_id = "checkin-latest-reference-001"
    _start(patient_client, session_id)
    monkeypatch.setattr("app.checkins.build_client", lambda *_args, **_kwargs: StaleReferenceClient())
    first = _send(
        patient_client,
        session_id,
        "patient-latest-reference-001",
        "My headache is worse.",
    )
    assert first.status_code == 200
    second = _send(
        patient_client,
        session_id,
        "patient-latest-reference-002",
        "I also want to add that I feel dizzy.",
        "supplement",
    )
    assert second.status_code == 200
    ai = second.json()["messages"][-1]
    assert ai["generation_method"] == "deterministic_fallback"
    assert ai["referenced_patient_message_ids"] == ["patient-latest-reference-002"]


class UnsafeAdviceClient:
    def checkin_turn(self, redacted, *_args, **_kwargs):
        latest = [
            message for message in redacted.content["messages"]
            if message.get("speaker") == "patient"
        ][-1]
        return CheckInTurnResult(
            acknowledgement="You should stop the medicine and double the dose tomorrow.",
            next_question="Does that work for you?",
            question_type="patient_concern",
            conversation_action="continue",
            referenced_patient_message_ids=[latest["id"]],
        )


def test_diagnosis_stop_dose_and_test_requests_use_deterministic_refusal(patient_client, monkeypatch):
    requests = (
        "Can you diagnose this?",
        "Should I stop taking my medicine?",
        "Should I double my dose?",
        "Can you explain whether my blood test is normal?",
    )
    for index, text in enumerate(requests, start=1):
        requested_session_id = f"checkin-advice-boundary-00{index}"
        session_id = _start(patient_client, requested_session_id).json()["session_id"]
        monkeypatch.setattr("app.checkins.build_client", lambda *_args, **_kwargs: UnsafeAdviceClient())
        response = _send(
            patient_client,
            session_id,
            f"patient-advice-boundary-00{index}",
            text,
        )
        assert response.status_code == 200
        ai = response.json()["messages"][-1]
        assert ai["generation_method"] == "deterministic_fallback"
        assert "cannot diagnose" in ai["text"]
        assert "should stop" not in ai["text"].lower()
        assert "double the dose" not in ai["text"].lower()
        patient_client.post(
            f"/api/check-ins/{session_id}/abandon",
            json={"expected_status": response.json()["status"]},
        )


def test_explicit_negations_do_not_trigger_safety_but_clear_risk_phrases_do(
    patient_client, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    safe_phrases = (
        "I do not want to kill myself.",
        "I do not have severe chest pain.",
        "I do not have one-sided weakness or slurred speech.",
        "I do not have uncontrolled bleeding.",
    )
    for index, text in enumerate(safe_phrases, start=1):
        requested_session_id = f"checkin-safety-negation-00{index}"
        session_id = _start(patient_client, requested_session_id).json()["session_id"]
        response = _send(
            patient_client,
            session_id,
            f"patient-safety-negation-00{index}",
            text,
        )
        assert response.status_code == 200
        assert response.json()["status"] != "safety_escalated"
        patient_client.post(
            f"/api/check-ins/{session_id}/abandon",
            json={"expected_status": response.json()["status"]},
        )

    for index, text in enumerate((
        "I want to kill myself.",
        "I have severe chest pain.",
        "I have one-sided weakness and slurred speech.",
        "I have uncontrolled bleeding.",
    ), start=1):
        session_id = f"checkin-safety-positive-00{index}"
        _start(patient_client, session_id)
        response = _send(
            patient_client,
            session_id,
            f"patient-safety-positive-00{index}",
            text,
        )
        assert response.status_code == 200
        assert response.json()["status"] == "safety_escalated"


def test_question_cap_is_server_owned(patient_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-question-cap-001"
    _start(patient_client, session_id)
    body = None
    for index in range(1, 5):
        response = _send(
            patient_client,
            session_id,
            f"patient-cap-message-00{index}",
            f"Free answer number {index} about my symptoms.",
        )
        assert response.status_code == 200
        body = response.json()
        if body["status"] == "awaiting_confirmation":
            break
    assert body["status"] == "awaiting_confirmation"
    questions = [m for m in body["messages"] if m["role"] == "ai" and m["question_type"]]
    assert len(questions) == 4


def test_mock_adapts_next_question_to_task_progress_and_advice_request(patient_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-adaptive-question-001"
    _start(patient_client, session_id)
    task = _send(
        patient_client,
        session_id,
        "patient-adaptive-task-001",
        "I completed the blood test task.",
    ).json()
    assert task["messages"][-1]["question_type"] == "task_progress"
    advice = _send(
        patient_client,
        session_id,
        "patient-adaptive-advice-001",
        "Which medicine should I take and can you diagnose this?",
    ).json()
    assert advice["messages"][-1]["question_type"] == "patient_concern"
    assert "cannot diagnose" in advice["messages"][-1]["text"]


def test_free_supplement_advances_to_a_new_question_type(patient_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-no-mechanical-repeat-001"
    _start(patient_client, session_id)
    first = _send(
        patient_client,
        session_id,
        "patient-no-repeat-001",
        "My headache is 4 out of 10 and I still feel nauseous.",
    ).json()
    second = _send(
        patient_client,
        session_id,
        "patient-no-repeat-002",
        "I also feel dizzy when I stand up.",
        "supplement",
    ).json()
    asked_types = [
        message["question_type"]
        for message in second["messages"]
        if message["role"] == "ai" and message["question_type"] is not None
    ]
    assert len(asked_types) == len(set(asked_types))
    assert second["messages"][-1]["referenced_patient_message_ids"] == [
        "patient-no-repeat-002"
    ]
    assert "Thanks for adding that detail" in second["messages"][-1]["text"]
    assert first["messages"][-1]["question_type"] != second["messages"][-1]["question_type"]
