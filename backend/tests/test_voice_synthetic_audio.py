"""Synthetic WAV validates audio plumbing, not acoustic recognition accuracy."""

import io
import math
import struct
import wave

import pytest

from app.voice.audio import AudioPolicy, AudioValidationError, inspect_audio


def _synthetic_wav(duration_ms: int = 250, sample_rate: int = 8_000) -> bytes:
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


def test_synthetic_wav_metadata_is_measured_not_invented():
    audio = _synthetic_wav()
    metadata = inspect_audio(
        audio,
        declared_mime_type="audio/wav",
        policy=AudioPolicy(max_bytes=100_000, max_duration_ms=1_000),
    )

    assert metadata.mime_type == "audio/wav"
    assert metadata.byte_length == len(audio)
    assert metadata.duration_ms == 250
    assert metadata.sample_rate_hz == 8_000
    assert metadata.channels == 1


def test_mime_mismatch_and_size_limit_fail_closed():
    audio = _synthetic_wav()

    with pytest.raises(AudioValidationError, match="mime_type_mismatch"):
        inspect_audio(
            audio,
            declared_mime_type="audio/webm",
            policy=AudioPolicy(max_bytes=100_000, max_duration_ms=1_000),
        )

    with pytest.raises(AudioValidationError, match="audio_too_large"):
        inspect_audio(
            audio,
            declared_mime_type="audio/wav",
            policy=AudioPolicy(max_bytes=10, max_duration_ms=1_000),
        )


def test_invalid_wav_and_duration_limit_fail_closed():
    policy = AudioPolicy(max_bytes=100_000, max_duration_ms=100)

    with pytest.raises(AudioValidationError, match="invalid_wav"):
        inspect_audio(
            b"RIFF\x04\x00\x00\x00WAVE",
            declared_mime_type="audio/wav",
            policy=policy,
        )

    with pytest.raises(AudioValidationError, match="audio_too_long"):
        inspect_audio(
            _synthetic_wav(duration_ms=250),
            declared_mime_type="audio/wav",
            policy=policy,
        )
