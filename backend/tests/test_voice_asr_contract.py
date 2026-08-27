"""E4 ASR boundary: authorized bytes in, strict provider-neutral result out."""

from hashlib import sha256

import pytest
from pydantic import ValidationError

from app.voice.asr import DeterministicMockASRClient
from app.voice.contracts import (
    ASRResult,
    ASRSegment,
    AudioMetadata,
    AuthorizedRecording,
    CaptureMode,
)


def _recording(data: bytes = b"synthetic-audio") -> AuthorizedRecording:
    return AuthorizedRecording(
        capture_id="cap_demo",
        clinic_id="clinic_a",
        patient_id="patient_a",
        capture_mode=CaptureMode.DOCTOR_CONSULT,
        audio_bytes=data,
        metadata=AudioMetadata(
            mime_type="audio/wav",
            byte_length=len(data),
            sha256=sha256(data).hexdigest(),
            duration_ms=None,
            sample_rate_hz=None,
            channels=None,
        ),
    )


def test_mock_asr_is_keyed_by_exact_audio_digest():
    recording = _recording()
    expected = ASRResult(
        provider="deterministic_mock",
        method="fixture_lookup",
        model=None,
        version="1",
        language="en",
        segments=[
            ASRSegment(
                machine_segment_id="seg_0",
                source_start_ms=0,
                source_end_ms=900,
                speaker_candidate="doctor",
                text="How has your headache changed?",
                confidence=0.99,
                issues=[],
            )
        ],
        degraded=False,
        failure_reason=None,
    )
    client = DeterministicMockASRClient(
        {recording.metadata.sha256: expected}
    )

    assert client.transcribe(recording) == expected


def test_unknown_fixture_returns_explicit_failure_not_empty_success():
    result = DeterministicMockASRClient({}).transcribe(_recording())

    assert result.segments == []
    assert result.degraded is True
    assert result.failure_reason == "mock_fixture_not_found"


def test_recording_digest_mismatch_fails_before_adapter_result_lookup():
    recording = _recording()
    recording.metadata.sha256 = "0" * 64

    result = DeterministicMockASRClient({}).transcribe(recording)

    assert result.segments == []
    assert result.failure_reason == "recording_digest_mismatch"


def test_absent_timestamp_and_confidence_remain_null():
    segment = ASRSegment(
        machine_segment_id="seg_0",
        source_start_ms=None,
        source_end_ms=None,
        speaker_candidate="patient",
        text="My headache is better.",
        confidence=None,
        issues=[],
    )

    assert segment.source_start_ms is None
    assert segment.source_end_ms is None
    assert segment.confidence is None


def test_provider_raw_payload_is_not_part_of_the_result_contract():
    with pytest.raises(ValidationError):
        ASRResult(
            provider="deterministic_mock",
            method="fixture_lookup",
            model=None,
            version="1",
            language="en",
            segments=[
                ASRSegment(
                    machine_segment_id="seg_0",
                    source_start_ms=None,
                    source_end_ms=None,
                    speaker_candidate="patient",
                    text="My headache is better.",
                    confidence=None,
                    issues=[],
                )
            ],
            degraded=False,
            failure_reason=None,
            raw_response={"secret": "must not cross boundary"},
        )


def test_unmapped_provider_speaker_requires_explicit_unknown_issue():
    with pytest.raises(ValidationError):
        ASRSegment(
            machine_segment_id="seg_0",
            source_start_ms=None,
            source_end_ms=None,
            speaker_candidate="speaker_0",
            text="Unmapped diarization label",
            confidence=0.8,
            issues=[],
        )

    segment = ASRSegment(
        machine_segment_id="seg_0",
        source_start_ms=None,
        source_end_ms=None,
        speaker_candidate="speaker_0",
        text="Unmapped diarization label",
        confidence=0.8,
        issues=["unknown_speaker"],
    )
    assert segment.speaker_candidate == "speaker_0"
