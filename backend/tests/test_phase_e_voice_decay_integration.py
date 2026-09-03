from datetime import datetime

from sqlalchemy import select

from app.api import voice as voice_api
from app.data_decay import restore_shadow_archive, run_storage_policy
from app.highlights import extract_text
from app.models import Artifact, ArtifactStorageState, Highlight
from app.voice.models import VoiceCaptureRecord
from seed import fixture
from tests.voice_api_helpers import create_payload, mock_asr_for, synthetic_wav, upload


def test_confirmed_voice_uses_e2_score_and_e3_shadow_archive_without_touching_audio(
    clinician_client, db_session, monkeypatch
):
    audio = synthetic_wav()
    monkeypatch.setattr(voice_api, "build_asr_client", lambda _provider: mock_asr_for(audio))
    capture_id = clinician_client.post(
        "/api/voice/captures",
        json=create_payload(idempotency_key="phase-e-cross-feature"),
    ).json()["capture_id"]
    assert upload(clinician_client, capture_id, audio).status_code == 200
    assert clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": 2, "idempotency_key": "phase-e-transcribe"},
    ).status_code == 200
    processed = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": 4,
            "idempotency_key": "phase-e-confirm",
            **fixture.DOCTOR_CONSULT_REVIEW_ATTESTATION,
        },
    )
    assert processed.status_code == 200

    capture = db_session.get(VoiceCaptureRecord, capture_id)
    transcript = db_session.get(Artifact, capture.transcript_artifact_id)
    highlights = db_session.scalars(
        select(Highlight).where(Highlight.source_artifact_id == transcript.artifact_id)
    ).all()
    assert highlights
    assert all(
        item.importance_score
        == item.base_importance_score + item.adaptive_adjustment + item.decay_adjustment
        for item in highlights
    )

    run_storage_policy(
        db_session,
        as_of=datetime(2028, 1, 1),
        apply=True,
        evaluated_at=datetime(2028, 1, 1, 0, 1),
    )
    db_session.refresh(capture)
    db_session.refresh(transcript)
    state = db_session.get(ArtifactStorageState, transcript.artifact_id)

    assert state.tier == "cold"
    assert restore_shadow_archive(state) == transcript.content
    assert capture.audio_bytes == audio
    assert db_session.get(ArtifactStorageState, capture.capture_id) is None
    assert transcript.provenance_pointer["recording_capture_id"] == capture_id
    assert transcript.provenance_pointer["audio_ranges"] == [
        {"segment_index": 0, "source_start_ms": 0, "source_end_ms": 250}
    ]
    for item in highlights:
        db_session.refresh(item)
        assert extract_text(transcript.content, item.source_span)
        assert item.importance_score == (
            item.base_importance_score + item.adaptive_adjustment + item.decay_adjustment
        )
