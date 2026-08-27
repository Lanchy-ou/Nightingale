from __future__ import annotations

import json

from sqlalchemy import select

from app.models import AuditLog, PatientCheckInMessage
from seed import fixture


def test_checkin_audit_and_errors_never_copy_patient_text(patient_client, db_session, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    session_id = "checkin-log-sentinel-001"
    sentinel = "CHECKIN_RAW_SENTINEL_7f0a patient headache"
    patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )
    sent = patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-log-sentinel-001",
            "intent": "answer",
            "text": sentinel,
        },
    )
    assert sent.status_code == 200
    assert db_session.get(PatientCheckInMessage, "patient-log-sentinel-001").text == sentinel
    audits = db_session.scalars(select(AuditLog).where(AuditLog.event_id == sent.json()["event_id"])).all()
    assert sentinel not in json.dumps([audit.details for audit in audits])

    conflict = patient_client.post(
        f"/api/check-ins/{session_id}/messages",
        json={
            "message_id": "patient-log-sentinel-001",
            "intent": "answer",
            "text": "DIFFERENT_RAW_SENTINEL",
        },
    )
    assert conflict.status_code == 409
    assert sentinel not in conflict.text and "DIFFERENT_RAW_SENTINEL" not in conflict.text
