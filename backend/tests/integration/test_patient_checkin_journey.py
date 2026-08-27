from __future__ import annotations

from seed import fixture


def test_patient_to_clinical_timeline_checkin_journey(
    patient_client, clinician_client, staff_client, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-integration-journey-001"
    started = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )
    assert started.status_code == 200
    for message_id, intent, text in (
        ("patient-integration-001", "answer", "My headache is now 3 out of 10."),
        ("patient-integration-002", "supplement", "Nausea is still present."),
        ("patient-integration-003", "correction", "Correction: the headache is 4 out of 10."),
        ("patient-integration-004", "no_more", ""),
    ):
        response = patient_client.post(
            f"/api/check-ins/{session_id}/messages",
            json={"message_id": message_id, "intent": intent, "text": text},
        )
        assert response.status_code == 200, response.text
        if response.json()["status"] == "awaiting_confirmation":
            break
    confirmed = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert confirmed.status_code == 200, confirmed.text
    event_id = confirmed.json()["event_id"]
    for clinical_client in (clinician_client, staff_client):
        events = clinical_client.get(f"/api/patients/{fixture.PATIENT_ID}/events")
        assert event_id in {event["event_id"] for event in events.json()}
        artifacts = clinical_client.get(f"/api/events/{event_id}/artifacts")
        assert {artifact["artifact_type"] for artifact in artifacts.json()} == {
            "raw_conversation", "ai_patient_session_summary"
        }
