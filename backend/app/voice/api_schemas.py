"""Strict HTTP contracts for the E4 voice lifecycle."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .contracts import ASRResult, ReviewedSegment


class VoiceCapabilitiesOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
    provider: str
    asr_ready: bool
    allowed_modes: list[str]
    eligible_modes: list[str]
    disabled_reason: str | None
    accepted_mime_types: list[str]
    max_bytes: int
    max_duration_ms: int


class VoiceCaptureCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    idempotency_key: str = Field(min_length=1, max_length=64)
    patient_id: str = Field(min_length=1, max_length=64)
    capture_mode: Literal["doctor_consult", "nurse_consult", "patient_session"]
    patient_event_type: Literal["patient_ai_preconsult", "patient_followup"] | None = None
    started_at: datetime = Field(strict=False)
    ended_at: datetime | None = Field(default=None, strict=False)
    encounter_id: str | None = Field(default=None, min_length=1, max_length=64)

    @field_validator("idempotency_key", "patient_id", "encounter_id")
    @classmethod
    def trim_identifiers(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value

    @model_validator(mode="after")
    def mode_specific_fields(self):
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be >= started_at")
        if self.capture_mode == "patient_session":
            if self.patient_event_type is None:
                raise ValueError("patient_event_type is required for patient_session")
            if self.encounter_id is not None:
                raise ValueError("patient_session cannot set encounter_id")
        elif self.patient_event_type is not None:
            raise ValueError("patient_event_type is only valid for patient_session")
        return self


class VoiceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=0)
    idempotency_key: str = Field(min_length=1, max_length=64)

    @field_validator("idempotency_key")
    @classmethod
    def trim_key(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("idempotency_key must not be empty")
        return value


class VoiceConfirmCommand(VoiceCommand):
    """Mode-aware confirmation body.

    Doctor Consult captures require all three values at the endpoint. They are
    optional in the wire schema so Nurse and patient confirmation paths are not
    forced to make clinician-only attestations.
    """

    speaker_labels_reviewed: Literal[True] | None = None
    mixed_language_content_reviewed: Literal[True] | None = None
    medication_dosage_mentions_reviewed: Literal[True] | None = None


class VoiceReviewEdit(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    source_machine_segment_ids: list[str] = Field(min_length=1, max_length=500)
    speaker: Literal["doctor", "nurse", "patient", "ai", "system"] | None
    text: str = Field(min_length=1, max_length=4000)
    resolved_issues: list[str] = Field(default_factory=list, max_length=32)
    speaker_source_verified: bool = False

    @field_validator("text")
    @classmethod
    def trim_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("segment text must not be empty")
        return value


class VoiceReviewPatch(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_revision: int = Field(ge=0)
    segments: list[VoiceReviewEdit] = Field(min_length=1, max_length=500)


class VoiceAudioMetadataOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mime_type: str
    byte_length: int
    sha256: str
    duration_ms: int | None
    sample_rate_hz: int | None
    channels: int | None


class VoiceProcessingOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    degraded: bool
    fallback_reason: str | None


class VoiceCaptureOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    capture_id: str
    patient_id: str
    capture_mode: str
    event_type: str
    encounter_id: str | None
    status: str
    revision: int
    failure_reason: str | None
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime
    updated_at: datetime
    audio: VoiceAudioMetadataOut | None
    machine_transcript: ASRResult | None
    reviewed_segments: list[ReviewedSegment] | None
    event_id: str | None
    processing: VoiceProcessingOut | None
