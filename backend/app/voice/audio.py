"""Small fail-closed audio inspection boundary for deterministic WAV tests.

The independent slice intentionally supports measured WAV metadata only. A
future product upload API must add an approved parser for browser WebM/Ogg
before accepting those formats; it must not trust client-declared duration.
"""

from __future__ import annotations

import io
import wave
from dataclasses import dataclass
from hashlib import sha256

from .contracts import AudioMetadata


class AudioValidationError(ValueError):
    pass


@dataclass(frozen=True)
class AudioPolicy:
    max_bytes: int
    max_duration_ms: int

    def __post_init__(self):
        if self.max_bytes <= 0 or self.max_duration_ms <= 0:
            raise ValueError("audio limits must be positive")


def inspect_audio(
    audio_bytes: bytes,
    *,
    declared_mime_type: str,
    policy: AudioPolicy,
) -> AudioMetadata:
    if not audio_bytes:
        raise AudioValidationError("empty_audio")
    if len(audio_bytes) > policy.max_bytes:
        raise AudioValidationError("audio_too_large")
    if declared_mime_type not in {"audio/wav", "audio/x-wav"}:
        raise AudioValidationError("mime_type_mismatch")
    if len(audio_bytes) < 12 or audio_bytes[:4] != b"RIFF" or audio_bytes[8:12] != b"WAVE":
        raise AudioValidationError("mime_type_mismatch")

    try:
        with wave.open(io.BytesIO(audio_bytes), "rb") as wav:
            channels = wav.getnchannels()
            sample_rate = wav.getframerate()
            frame_count = wav.getnframes()
            if channels <= 0 or sample_rate <= 0 or wav.getsampwidth() <= 0:
                raise AudioValidationError("invalid_wav")
    except (EOFError, wave.Error) as exc:
        raise AudioValidationError("invalid_wav") from exc

    duration_ms = round(frame_count * 1000 / sample_rate)
    if duration_ms > policy.max_duration_ms:
        raise AudioValidationError("audio_too_long")

    return AudioMetadata(
        mime_type="audio/wav",
        byte_length=len(audio_bytes),
        sha256=sha256(audio_bytes).hexdigest(),
        duration_ms=duration_ms,
        sample_rate_hz=sample_rate,
        channels=channels,
    )
