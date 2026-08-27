"""Provider-neutral contracts for the E4 voice adapter foundation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class CaptureMode(str, Enum):
    DOCTOR_CONSULT = "doctor_consult"
    NURSE_CONSULT = "nurse_consult"
    PATIENT_SESSION = "patient_session"


class AudioMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    mime_type: str = Field(min_length=1, max_length=128)
    byte_length: int = Field(ge=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_ms: int | None = Field(default=None, ge=0)
    sample_rate_hz: int | None = Field(default=None, ge=1)
    channels: int | None = Field(default=None, ge=1)


@dataclass(frozen=True)
class AuthorizedRecording:
    """Audio that an API boundary has already authorized for this identity.

    The ASR boundary accepts this wrapper instead of anonymous bytes. This does
    not perform authorization itself and must not be constructed from request
    fields before server-side scope/role checks.
    """

    capture_id: str
    clinic_id: str
    patient_id: str
    capture_mode: CaptureMode
    audio_bytes: bytes
    metadata: AudioMetadata


class ASRSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    machine_segment_id: str = Field(min_length=1, max_length=128)
    source_start_ms: int | None = Field(default=None, ge=0)
    source_end_ms: int | None = Field(default=None, ge=0)
    speaker_candidate: str | None = Field(default=None, max_length=32)
    text: str = Field(max_length=4000)
    confidence: float | None = Field(default=None, ge=0, le=1)
    issues: list[str] = Field(default_factory=list, max_length=32)

    @model_validator(mode="after")
    def validate_machine_observations(self):
        has_start = self.source_start_ms is not None
        has_end = self.source_end_ms is not None
        if has_start != has_end:
            raise ValueError("audio range must provide both start and end")
        if has_start and self.source_end_ms < self.source_start_ms:
            raise ValueError("source_end_ms must be >= source_start_ms")
        if not self.text.strip() and "empty_text" not in self.issues:
            raise ValueError("empty machine text must carry empty_text issue")
        known_speakers = {"doctor", "nurse", "patient", "ai", "system"}
        if (
            self.speaker_candidate not in known_speakers
            and "unknown_speaker" not in self.issues
        ):
            raise ValueError("unknown speaker must carry unknown_speaker issue")
        return self


class ASRResult(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    provider: str = Field(min_length=1, max_length=128)
    method: str = Field(min_length=1, max_length=128)
    model: str | None = Field(default=None, max_length=128)
    version: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)
    segments: list[ASRSegment] = Field(default_factory=list, max_length=500)
    degraded: bool
    failure_reason: str | None = Field(default=None, max_length=256)

    @model_validator(mode="after")
    def failure_is_not_an_empty_success(self):
        if self.failure_reason is not None and self.segments:
            raise ValueError("failed ASR result must not contain partial segments")
        if self.failure_reason is not None and not self.degraded:
            raise ValueError("failed ASR result must be degraded")
        if self.failure_reason is None and not self.segments:
            raise ValueError("successful ASR result must contain segments")
        return self


class ReviewedSegment(BaseModel):
    """Human-review draft; issues are unresolved current blockers.

    The immutable ASRResult preserves the original provider observations and
    issue history. Clearing an issue here does not rewrite that machine result.
    """

    model_config = ConfigDict(extra="forbid", strict=True)

    index: int = Field(ge=0)
    source_machine_segment_ids: list[str] = Field(default_factory=list, max_length=500)
    speaker: str | None = Field(default=None, max_length=32)
    text: str = Field(max_length=4000)
    source_start_ms: int | None = Field(default=None, ge=0)
    source_end_ms: int | None = Field(default=None, ge=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    issues: list[str] = Field(default_factory=list, max_length=32)
    audio_range_exact: bool = False
    speaker_source_verified: bool = False


class CanonicalTranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    index: int = Field(ge=0)
    speaker: str = Field(min_length=1, max_length=32)
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def trim_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("segment text must not be empty")
        return value


class CanonicalTranscriptContent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    segments: list[CanonicalTranscriptSegment] = Field(min_length=1, max_length=500)


class AudioRangeLink(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    segment_index: int = Field(ge=0)
    source_start_ms: int = Field(ge=0)
    source_end_ms: int = Field(ge=0)


class ConfirmedTranscript(BaseModel):
    """Canonical LLM handoff plus separately bounded audio provenance."""

    model_config = ConfigDict(extra="forbid", strict=True)

    content: CanonicalTranscriptContent
    audio_ranges: list[AudioRangeLink]
