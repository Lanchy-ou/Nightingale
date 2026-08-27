"""Fail-closed in-memory inspection for browser and WAV recordings."""

from __future__ import annotations

import io
from dataclasses import dataclass
from hashlib import sha256

import av

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


_MIME_FORMATS = {
    "audio/wav": {"wav"},
    "audio/x-wav": {"wav"},
    "audio/webm": {"webm", "matroska"},
    "audio/ogg": {"ogg"},
}


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
    declared_mime_type = declared_mime_type.split(";", 1)[0].strip().lower()
    expected_formats = _MIME_FORMATS.get(declared_mime_type)
    if expected_formats is None:
        raise AudioValidationError("mime_type_mismatch")

    try:
        with av.open(io.BytesIO(audio_bytes), mode="r") as container:
            actual_formats = set(container.format.name.lower().split(","))
            if not actual_formats.intersection(expected_formats):
                raise AudioValidationError("mime_type_mismatch")
            audio_streams = list(container.streams.audio)
            if len(audio_streams) != 1 or container.streams.video:
                raise AudioValidationError("invalid_audio_streams")

            sample_rate = None
            channels = None
            sample_count = 0
            for frame in container.decode(audio_streams[0]):
                frame_rate = int(frame.sample_rate or 0)
                frame_channels = len(frame.layout.channels) if frame.layout else 0
                if frame_rate <= 0 or frame_channels <= 0 or frame.samples <= 0:
                    raise AudioValidationError("invalid_audio")
                if sample_rate is None:
                    sample_rate = frame_rate
                    channels = frame_channels
                elif sample_rate != frame_rate or channels != frame_channels:
                    raise AudioValidationError("changing_audio_format")
                sample_count += int(frame.samples)
    except AudioValidationError:
        raise
    except Exception as exc:
        reason = (
            "invalid_wav"
            if declared_mime_type in {"audio/wav", "audio/x-wav"}
            else "invalid_audio"
        )
        raise AudioValidationError(reason) from exc

    if sample_rate is None or channels is None or sample_count <= 0:
        raise AudioValidationError("invalid_audio")
    if not 8_000 <= sample_rate <= 192_000 or channels not in {1, 2}:
        raise AudioValidationError("unsupported_audio_format")

    duration_ms = round(sample_count * 1000 / sample_rate)
    if duration_ms <= 0:
        raise AudioValidationError("invalid_audio")
    if duration_ms > policy.max_duration_ms:
        raise AudioValidationError("audio_too_long")

    canonical_mime = "audio/wav" if declared_mime_type == "audio/x-wav" else declared_mime_type
    return AudioMetadata(
        mime_type=canonical_mime,
        byte_length=len(audio_bytes),
        sha256=sha256(audio_bytes).hexdigest(),
        duration_ms=duration_ms,
        sample_rate_hz=sample_rate,
        channels=channels,
    )
