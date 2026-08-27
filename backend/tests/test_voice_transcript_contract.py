"""Machine transcript review must fail closed before canonical handoff."""

import pytest

from app.voice.contracts import CaptureMode, ReviewedSegment
from app.voice.transcript import TranscriptConfirmationError, confirm_transcript


def _segment(**updates) -> ReviewedSegment:
    values = {
        "index": 0,
        "speaker": "doctor",
        "text": "How has your headache changed?",
        "source_start_ms": 0,
        "source_end_ms": 900,
        "confidence": 0.98,
        "issues": [],
        "audio_range_exact": True,
    }
    values.update(updates)
    return ReviewedSegment(**values)


def test_confirmation_strips_asr_metadata_from_canonical_content():
    confirmed = confirm_transcript(
        CaptureMode.DOCTOR_CONSULT,
        [_segment()],
    )

    assert confirmed.content.model_dump() == {
        "segments": [
            {
                "index": 0,
                "speaker": "doctor",
                "text": "How has your headache changed?",
            }
        ]
    }
    assert confirmed.audio_ranges[0].model_dump() == {
        "segment_index": 0,
        "source_start_ms": 0,
        "source_end_ms": 900,
    }


@pytest.mark.parametrize(
    ("mode", "speaker"),
    [
        (CaptureMode.DOCTOR_CONSULT, "nurse"),
        (CaptureMode.NURSE_CONSULT, "doctor"),
        (CaptureMode.PATIENT_SESSION, "doctor"),
    ],
)
def test_mode_specific_speaker_allowlist_is_enforced(mode, speaker):
    with pytest.raises(TranscriptConfirmationError):
        confirm_transcript(mode, [_segment(speaker=speaker)])


@pytest.mark.parametrize("issue", ["unknown_speaker", "low_confidence", "overlap", "empty_text"])
def test_blocking_machine_issues_prevent_confirmation(issue):
    with pytest.raises(TranscriptConfirmationError):
        confirm_transcript(CaptureMode.DOCTOR_CONSULT, [_segment(issues=[issue])])


def test_indexes_must_be_continuous_and_zero_based():
    with pytest.raises(TranscriptConfirmationError):
        confirm_transcript(
            CaptureMode.DOCTOR_CONSULT,
            [_segment(index=1)],
        )


def test_unprovable_audio_range_is_omitted_not_fabricated():
    confirmed = confirm_transcript(
        CaptureMode.DOCTOR_CONSULT,
        [
            _segment(
                source_start_ms=None,
                source_end_ms=None,
                confidence=None,
                audio_range_exact=False,
            )
        ],
    )

    assert confirmed.audio_ranges == []


def test_patient_ai_or_system_speaker_requires_observed_source_evidence():
    with pytest.raises(TranscriptConfirmationError):
        confirm_transcript(
            CaptureMode.PATIENT_SESSION,
            [_segment(speaker="system", speaker_source_verified=False)],
        )

    confirmed = confirm_transcript(
        CaptureMode.PATIENT_SESSION,
        [_segment(speaker="system", speaker_source_verified=True)],
    )
    assert confirmed.content.segments[0].speaker == "system"
