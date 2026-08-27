"""Deterministic raw-text transcript normalization for D3.

The normalizer is intentionally pure: it does not read the database, call an
LLM/provider, persist records, or infer missing speakers.  It only recognizes a
small frozen label map and preserves character ranges into the submitted text.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal


MAX_RAW_TEXT_BYTES = 4096
MAX_SEGMENTS = 500
MAX_SEGMENT_TEXT_CHARACTERS = 4000

NormalizeOutcome = Literal["ACCEPT", "NEEDS_REVIEW", "REJECT"]
SpeakerCandidate = Literal["doctor", "patient"] | None
ConfidenceMarker = Literal["exact_label", "mapped_label", "inferred_boundary", "unknown"]

_LABEL_MAP = {
    "doctor": "doctor",
    "dr": "doctor",
    "patient": "patient",
    "pt": "patient",
}
_THIRD_PARTY_LABELS = {"caregiver", "nurse", "relative", "interpreter"}
_LABEL_LINE = re.compile(r"^(?P<label>[^:：\r\n]+?)(?P<separator>[:：])(?P<after>.*)$")


@dataclass
class PreviewSegment:
    index: int
    speaker_candidate: SpeakerCandidate
    text: str
    source_start: int
    source_end: int
    confidence_marker: ConfidenceMarker
    issues: list[str] = field(default_factory=list)


@dataclass
class NormalizationResult:
    outcome: NormalizeOutcome
    reason: str | None
    raw_byte_length: int
    segments: list[PreviewSegment]
    issues: list[str]


def _trimmed_range(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _mapped_label(label: str) -> tuple[SpeakerCandidate, ConfidenceMarker]:
    stripped = label.strip()
    normalized = stripped.lower()
    if normalized.endswith("."):
        normalized = normalized[:-1]
    speaker = _LABEL_MAP.get(normalized)
    if speaker is None:
        return None, "unknown"
    if stripped in {"DOCTOR", "PATIENT"}:
        return speaker, "exact_label"
    return speaker, "mapped_label"


def _append_issue(issues: list[str], issue: str) -> None:
    if issue not in issues:
        issues.append(issue)


def normalize_transcript(raw_text: str) -> NormalizationResult:
    raw_byte_length = len(raw_text.encode("utf-8"))
    if raw_byte_length > MAX_RAW_TEXT_BYTES:
        return NormalizationResult("REJECT", "INPUT_TOO_LONG", raw_byte_length, [], ["INPUT_TOO_LONG"])
    if not raw_text.strip():
        return NormalizationResult("REJECT", "EMPTY_INPUT", raw_byte_length, [], ["EMPTY_INPUT"])

    segments: list[PreviewSegment] = []
    top_issues: list[str] = []
    supported_label_count = 0
    label_line_count = 0
    empty_label = False
    unowned_continuation = False
    third_party = False
    offset = 0

    for raw_line in raw_text.splitlines(keepends=True):
        line_end = offset + len(raw_line)
        content_end = line_end
        while content_end > offset and raw_text[content_end - 1] in "\r\n":
            content_end -= 1
        line = raw_text[offset:content_end]
        if not line.strip():
            offset = line_end
            continue

        match = _LABEL_LINE.match(line)
        if match is not None:
            label_line_count += 1
            label = match.group("label").strip()
            speaker, marker = _mapped_label(label)
            after_start = offset + match.start("after")
            text_start, text_end = _trimmed_range(raw_text, after_start, content_end)
            text = raw_text[text_start:text_end]
            issues: list[str] = []
            if speaker is None:
                normalized_label = label.lower().rstrip(".")
                issue = f"unknown_speaker_label:{label}"
                issues.append(issue)
                _append_issue(top_issues, issue)
                if normalized_label in _THIRD_PARTY_LABELS:
                    third_party = True
            else:
                supported_label_count += 1
            if not text:
                empty_label = True
                issues.append("empty_segment_text")
                _append_issue(top_issues, "empty_segment_text")
            segments.append(
                PreviewSegment(
                    index=len(segments),
                    speaker_candidate=speaker,
                    text=text,
                    source_start=text_start,
                    source_end=text_end,
                    confidence_marker=marker,
                    issues=issues,
                )
            )
            offset = line_end
            continue

        text_start, text_end = _trimmed_range(raw_text, offset, content_end)
        if segments:
            previous = segments[-1]
            previous.source_end = text_end
            previous.text = raw_text[previous.source_start:previous.source_end]
            previous.confidence_marker = "inferred_boundary"
            _append_issue(previous.issues, "continuation_line")
        else:
            unowned_continuation = True
            _append_issue(top_issues, "unowned_continuation")
            segments.append(
                PreviewSegment(
                    index=0,
                    speaker_candidate=None,
                    text=raw_text[text_start:text_end],
                    source_start=text_start,
                    source_end=text_end,
                    confidence_marker="unknown",
                    issues=["unowned_continuation"],
                )
            )
        offset = line_end

    # splitlines() returns no element for an empty trailing suffix, which is
    # fine: trailing whitespace is not clinical content and is never invented.
    if len(segments) > MAX_SEGMENTS:
        return NormalizationResult("REJECT", "TOO_MANY_SEGMENTS", raw_byte_length, [], ["TOO_MANY_SEGMENTS"])
    if any(len(segment.text) > MAX_SEGMENT_TEXT_CHARACTERS for segment in segments):
        return NormalizationResult(
            "REJECT",
            "SEGMENT_TEXT_TOO_LONG",
            raw_byte_length,
            [],
            ["SEGMENT_TEXT_TOO_LONG"],
        )
    if empty_label:
        return NormalizationResult("REJECT", "EMPTY_SEGMENT_TEXT", raw_byte_length, segments, top_issues)
    if label_line_count == 0 or supported_label_count == 0 and not any(
        segment.speaker_candidate is None and "unknown_speaker_label" in " ".join(segment.issues)
        for segment in segments
    ):
        return NormalizationResult("REJECT", "NO_SPEAKER_LABELS", raw_byte_length, segments, top_issues)
    if third_party:
        return NormalizationResult(
            "NEEDS_REVIEW", "UNSUPPORTED_THIRD_SPEAKER", raw_byte_length, segments, top_issues
        )
    if unowned_continuation:
        return NormalizationResult(
            "NEEDS_REVIEW", "UNOWNED_CONTINUATION", raw_byte_length, segments, top_issues
        )
    if any(segment.speaker_candidate is None for segment in segments):
        return NormalizationResult(
            "NEEDS_REVIEW", "UNKNOWN_SPEAKER_LABEL", raw_byte_length, segments, top_issues
        )
    return NormalizationResult("ACCEPT", None, raw_byte_length, segments, top_issues)
