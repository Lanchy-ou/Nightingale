"""Voice storage responses/audit remain metadata-only."""

from sqlalchemy import select

from app.models import AuditLog
from app.voice.models import VoiceCaptureRecord
from tests.voice_api_helpers import create_payload, synthetic_wav, upload


def test_audio_blob_is_stored_but_never_copied_to_audit_or_json(
    clinician_client, db_session
):
    audio = synthetic_wav()
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    response = upload(clinician_client, capture_id, audio)
    assert response.status_code == 200

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.audio_bytes == audio
    assert "audio_bytes" not in response.json()

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.target_id == capture_id)
    ).all()
    assert audits
    serialized = " ".join(str(audit.details) for audit in audits)
    assert audio.hex() not in serialized
    assert "My headache" not in serialized


def test_invalid_mime_size_and_audio_do_not_persist_bytes(clinician_client, db_session):
    capture_id = clinician_client.post("/api/voice/captures", json=create_payload()).json()["capture_id"]
    wrong_mime = clinician_client.put(
        f"/api/voice/captures/{capture_id}/audio",
        content=b"not audio",
        headers={
            "Content-Type": "audio/webm",
            "X-Expected-Revision": "0",
            "Idempotency-Key": "wrong-mime",
        },
    )
    # WebM is a supported browser format, but these bytes are not a valid
    # WebM container and must fail validation without persistence.
    assert wrong_mime.status_code == 422

    invalid_wav = clinician_client.put(
        f"/api/voice/captures/{capture_id}/audio",
        content=b"RIFF\x04\x00\x00\x00WAVE",
        headers={
            "Content-Type": "audio/wav",
            "X-Expected-Revision": "0",
            "Idempotency-Key": "invalid-wav",
        },
    )
    assert invalid_wav.status_code == 422

    too_large = clinician_client.put(
        f"/api/voice/captures/{capture_id}/audio",
        content=b"0" * (8 * 1024 * 1024 + 1),
        headers={
            "Content-Type": "audio/wav",
            "X-Expected-Revision": "0",
            "Idempotency-Key": "too-large",
        },
    )
    assert too_large.status_code == 413

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    assert capture.audio_bytes is None
    assert capture.status == "created"
