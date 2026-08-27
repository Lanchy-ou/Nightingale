from __future__ import annotations

import io
import math
import struct
import wave
from hashlib import sha256

from app.voice.asr import DeterministicMockASRClient
from app.voice.contracts import ASRResult, ASRSegment


def synthetic_wav(duration_ms: int = 250, sample_rate: int = 8_000) -> bytes:
    frame_count = duration_ms * sample_rate // 1000
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frame_count):
            sample = int(3_000 * math.sin(2 * math.pi * 440 * index / sample_rate))
            wav.writeframesraw(struct.pack("<h", sample))
    return output.getvalue()


def mock_asr_for(
    audio: bytes,
    *,
    speaker: str | None = "doctor",
    text: str = "My headache is worse and happening almost every day.",
    confidence: float | None = 0.99,
    issues: list[str] | None = None,
) -> DeterministicMockASRClient:
    result = ASRResult(
        provider="deterministic_mock",
        method="fixture_lookup",
        model=None,
        version="1",
        language="en",
        segments=[
            ASRSegment(
                machine_segment_id="seg_0",
                source_start_ms=0,
                source_end_ms=duration_ms(audio),
                speaker_candidate=speaker,
                text=text,
                confidence=confidence,
                issues=issues or [],
            )
        ],
        degraded=False,
        failure_reason=None,
    )
    return DeterministicMockASRClient({sha256(audio).hexdigest(): result})


def duration_ms(audio: bytes) -> int:
    with wave.open(io.BytesIO(audio), "rb") as wav:
        return round(wav.getnframes() * 1000 / wav.getframerate())


def create_payload(
    *,
    capture_mode: str = "doctor_consult",
    patient_id: str = "pat_001",
    idempotency_key: str = "create-voice-1",
) -> dict:
    payload = {
        "idempotency_key": idempotency_key,
        "patient_id": patient_id,
        "capture_mode": capture_mode,
        "started_at": "2026-08-27T10:00:00",
        "ended_at": "2026-08-27T10:02:00",
    }
    if capture_mode == "patient_session":
        payload["patient_event_type"] = "patient_followup"
    return payload


def upload(client, capture_id: str, audio: bytes, revision: int = 0):
    return client.put(
        f"/api/voice/captures/{capture_id}/audio",
        content=audio,
        headers={
            "Content-Type": "audio/wav",
            "X-Expected-Revision": str(revision),
            "Idempotency-Key": "upload-voice-1",
        },
    )
