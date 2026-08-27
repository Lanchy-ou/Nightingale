"""Fail-closed review-to-canonical Transcript conversion."""

from __future__ import annotations

from pydantic import ValidationError

from .contracts import (
    AudioRangeLink,
    CanonicalTranscriptContent,
    CanonicalTranscriptSegment,
    CaptureMode,
    ConfirmedTranscript,
    ReviewedSegment,
)


class TranscriptConfirmationError(ValueError):
    pass


BLOCKING_ISSUES = {"unknown_speaker", "low_confidence", "overlap", "empty_text"}

SPEAKER_ALLOWLISTS = {
    CaptureMode.DOCTOR_CONSULT: {"doctor", "patient"},
    CaptureMode.NURSE_CONSULT: {"nurse", "patient"},
    CaptureMode.PATIENT_SESSION: {"patient", "ai", "system"},
}


def confirm_transcript(
    capture_mode: CaptureMode,
    reviewed_segments: list[ReviewedSegment],
) -> ConfirmedTranscript:
    if not reviewed_segments:
        raise TranscriptConfirmationError("at least one reviewed segment is required")
    if len(reviewed_segments) > 500:
        raise TranscriptConfirmationError("segment limit exceeded")

    indexes = [segment.index for segment in reviewed_segments]
    if indexes != list(range(len(reviewed_segments))):
        raise TranscriptConfirmationError("segment indexes must be zero-based and continuous")

    allowed_speakers = SPEAKER_ALLOWLISTS[capture_mode]
    canonical: list[CanonicalTranscriptSegment] = []
    audio_ranges: list[AudioRangeLink] = []

    for segment in reviewed_segments:
        blocking = BLOCKING_ISSUES.intersection(segment.issues)
        if blocking:
            raise TranscriptConfirmationError(
                f"segment {segment.index} has unresolved issues: {sorted(blocking)}"
            )
        if segment.speaker not in allowed_speakers:
            raise TranscriptConfirmationError(
                f"speaker {segment.speaker!r} is not allowed for {capture_mode.value}"
            )
        if (
            capture_mode is CaptureMode.PATIENT_SESSION
            and segment.speaker in {"ai", "system"}
            and not segment.speaker_source_verified
        ):
            raise TranscriptConfirmationError(
                "ai/system speaker requires explicit source verification"
            )

        try:
            canonical.append(
                CanonicalTranscriptSegment(
                    index=segment.index,
                    speaker=segment.speaker,
                    text=segment.text,
                )
            )
        except ValidationError as exc:
            raise TranscriptConfirmationError(
                f"segment {segment.index} is not canonical"
            ) from exc

        if segment.audio_range_exact:
            if segment.source_start_ms is None or segment.source_end_ms is None:
                raise TranscriptConfirmationError(
                    f"segment {segment.index} claims an unproven audio range"
                )
            if segment.source_end_ms < segment.source_start_ms:
                raise TranscriptConfirmationError(
                    f"segment {segment.index} has an invalid audio range"
                )
            audio_ranges.append(
                AudioRangeLink(
                    segment_index=segment.index,
                    source_start_ms=segment.source_start_ms,
                    source_end_ms=segment.source_end_ms,
                )
            )

    return ConfirmedTranscript(
        content=CanonicalTranscriptContent(segments=canonical),
        audio_ranges=audio_ranges,
    )
