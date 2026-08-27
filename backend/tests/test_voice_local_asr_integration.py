import os
from hashlib import sha256
from pathlib import Path

import pytest

from app.voice.asr import FasterWhisperASRClient
from app.voice.audio import AudioPolicy, inspect_audio
from app.voice.contracts import AuthorizedRecording, CaptureMode
from tests.voice_api_helpers import create_payload, upload


MODEL_PATH = os.environ.get("NANTINGALE_ASR_MODEL_PATH", "")
SYNTHETIC_AUDIO = os.environ.get("NANTINGALE_ASR_SYNTHETIC_AUDIO", "")


@pytest.mark.skipif(
    not MODEL_PATH or not SYNTHETIC_AUDIO,
    reason="local ASR smoke requires explicit ignored model and synthetic audio paths",
)
def test_real_local_asr_smoke_is_nonempty_timestamped_and_speaker_unknown():
    audio_bytes = Path(SYNTHETIC_AUDIO).read_bytes()
    metadata = inspect_audio(
        audio_bytes,
        declared_mime_type="audio/wav",
        policy=AudioPolicy(max_bytes=8 * 1024 * 1024, max_duration_ms=120_000),
    )
    result = FasterWhisperASRClient(Path(MODEL_PATH)).transcribe(
        AuthorizedRecording(
            capture_id="synthetic_gate0",
            clinic_id="synthetic_clinic",
            patient_id="synthetic_patient",
            capture_mode=CaptureMode.DOCTOR_CONSULT,
            audio_bytes=audio_bytes,
            metadata=metadata,
        )
    )

    assert sha256(audio_bytes).hexdigest() == metadata.sha256
    assert result.failure_reason is None
    assert result.segments
    assert all(segment.text.strip() for segment in result.segments)
    assert all(segment.source_start_ms is not None for segment in result.segments)
    assert all(segment.source_end_ms is not None for segment in result.segments)
    assert all(segment.speaker_candidate is None for segment in result.segments)
    assert all("unknown_speaker" in segment.issues for segment in result.segments)


@pytest.mark.skipif(
    not MODEL_PATH or not SYNTHETIC_AUDIO,
    reason="local ASR endpoint journey requires explicit ignored model and audio paths",
)
def test_real_local_asr_endpoint_requires_review_then_processes(
    clinician_client, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_VOICE_ENABLED", "true")
    monkeypatch.setenv("NANTINGALE_ASR_PROVIDER", "faster_whisper")
    monkeypatch.setenv("NANTINGALE_ASR_MODEL_PATH", MODEL_PATH)
    audio_bytes = Path(SYNTHETIC_AUDIO).read_bytes()
    capture_id = clinician_client.post(
        "/api/voice/captures",
        json=create_payload(idempotency_key="real-local-endpoint"),
    ).json()["capture_id"]
    uploaded = upload(clinician_client, capture_id, audio_bytes)
    assert uploaded.status_code == 200

    transcribed = clinician_client.post(
        f"/api/voice/captures/{capture_id}/transcribe",
        json={"expected_revision": uploaded.json()["revision"], "idempotency_key": "real-local-asr"},
    )
    assert transcribed.status_code == 200
    body = transcribed.json()
    assert body["status"] == "needs_review"
    assert all(segment["speaker"] is None for segment in body["reviewed_segments"])
    assert all("unknown_speaker" in segment["issues"] for segment in body["reviewed_segments"])

    reviewed = clinician_client.patch(
        f"/api/voice/captures/{capture_id}/segments",
        json={
            "expected_revision": body["revision"],
            "segments": [
                {
                    "source_machine_segment_ids": segment["source_machine_segment_ids"],
                    "speaker": "doctor",
                    "text": segment["text"],
                    "resolved_issues": ["unknown_speaker"],
                    "speaker_source_verified": False,
                }
                for segment in body["reviewed_segments"]
            ],
        },
    )
    assert reviewed.status_code == 200
    processed = clinician_client.post(
        f"/api/voice/captures/{capture_id}/confirm",
        json={
            "expected_revision": reviewed.json()["revision"],
            "idempotency_key": "real-local-confirm",
        },
    )
    assert processed.status_code == 200
    assert processed.json()["status"] == "processed"
    assert processed.json()["event_id"]
