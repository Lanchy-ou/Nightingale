"""The E4 table initializer must never rebuild existing patient data."""

from sqlalchemy import select

from app.models import Patient
from app.voice.models import VoiceCaptureRecord
from scripts.create_voice_schema import main as create_voice_schema
from tests.voice_api_helpers import create_payload


def test_voice_schema_initializer_is_idempotent_and_non_destructive(
    clinician_client, db_session, capsys
):
    capture_id = clinician_client.post(
        "/api/voice/captures", json=create_payload(idempotency_key="schema-check")
    ).json()["capture_id"]
    patient_count = len(db_session.scalars(select(Patient)).all())

    create_voice_schema()
    create_voice_schema()

    db_session.expire_all()
    assert db_session.get(VoiceCaptureRecord, capture_id) is not None
    assert len(db_session.scalars(select(Patient)).all()) == patient_count
    assert capsys.readouterr().out.count("VOICE_SCHEMA_READY") == 2
