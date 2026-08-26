"""Pydantic v2 response schemas for the M1 read-only API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ClinicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    clinic_id: str
    name: str


class PatientOut(BaseModel):
    patient_id: str
    clinic_id: str
    name: str
    clinic_name: str | None = None


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    patient_id: str
    clinic_id: str
    event_type: str
    encounter_id: str | None
    started_at: datetime
    ended_at: datetime | None
    created_at: datetime
    artifact_count: int = 0


class ArtifactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    artifact_id: str
    event_id: str
    artifact_type: str
    author_role: str
    author_id: str | None
    content: dict
    created_at: datetime
    version: int
    provenance_pointer: dict | None


class HighlightOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    highlight_id: str
    patient_id: str
    event_id: str
    artifact_id: str
    source_artifact_id: str
    source_span: dict
    text: str
    risk_reason: str
    feature_flags: dict
    importance_score: int
    status: str
    status_history: list = []
    created_at: datetime
    updated_at: datetime
    entity_type: str | None = None
    entity_key: str | None = None
    assertion_value: str | None = None
    conflict_with_artifact_id: str | None = None
    review_status: str | None = None


class GlanceOut(BaseModel):
    highlights: list[HighlightOut]


class StatusUpdate(BaseModel):
    status: str = Field(pattern="^(accepted|rejected|pinned)$")


class EventBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: str
    event_type: str
    started_at: datetime
    ended_at: datetime | None


class ProvenanceOut(BaseModel):
    highlight_id: str
    event: EventBrief
    summary_artifact: ArtifactOut | None
    source_artifact: ArtifactOut
    span: dict
    quote: str | None
    conflict_artifact: ArtifactOut | None = None


class CommentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    comment_id: str
    anchor_type: str
    anchor_id: str
    parent_comment_id: str | None
    author_id: str
    author_role: str
    body: str
    mentions: list
    resolved: bool
    created_at: datetime
    resolved_at: datetime | None
    resolved_by: str | None


class ArtifactVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    version_id: str
    artifact_id: str
    version: int
    content: dict
    actor_id: str
    actor_role: str
    created_at: datetime


class AuditLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    audit_id: str
    actor_id: str | None
    actor_role: str | None
    action: str
    target_type: str
    target_id: str
    from_version: int | None
    to_version: int | None
    clinic_id: str | None
    patient_id: str | None
    event_id: str | None
    created_at: datetime


class NoteCreate(BaseModel):
    artifact_type: Literal["staff_note", "clinician_note"]
    content: dict


class ArtifactUpdate(BaseModel):
    content: dict
    expected_version: int


class RevertRequest(BaseModel):
    to_version: int
    expected_version: int


class CommentCreate(BaseModel):
    anchor_type: Literal["event", "artifact"]
    anchor_id: str
    parent_comment_id: str | None = None
    body: str
    mentions: list[str] = []


class DiffOut(BaseModel):
    artifact_id: str
    since_version: int
    to_version: int
    diff: str


class SourceIngestRequest(BaseModel):
    ingestion_key: str
    artifact_type: Literal["transcript"]
    content: dict


class SessionIngestRequest(BaseModel):
    session_id: str
    event_type: Literal["patient_ai_preconsult", "patient_followup"]
    started_at: datetime
    ended_at: datetime | None = None
    content: dict


# --- C1 Doctor Consult ingestion (strict manual transcript boundary) ---
class DoctorTranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    index: int = Field(ge=0)
    speaker: Literal["doctor", "patient"]
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def trim_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("segment text must not be empty")
        return value


class DoctorTranscriptContent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    segments: list[DoctorTranscriptSegment] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def continuous_indexes(self):
        indexes = [segment.index for segment in self.segments]
        if indexes != list(range(len(indexes))):
            raise ValueError("segment indexes must start at 0 and be continuous")
        return self


class DoctorConsultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    consult_id: str = Field(min_length=1, max_length=64)
    ingestion_key: str = Field(min_length=1, max_length=64)
    # JSON transports datetimes as ISO-8601 strings; keep all other request
    # fields strict while allowing Pydantic's datetime parser at this boundary.
    started_at: datetime = Field(strict=False)
    ended_at: datetime | None = Field(default=None, strict=False)
    content: DoctorTranscriptContent

    @field_validator("consult_id", "ingestion_key")
    @classmethod
    def trim_non_empty_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be >= started_at")
        return self


class DoctorConsultOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event: EventOut
    encounter_id: str
    source_artifact_id: str
    ai_summary_artifact_id: str
    highlight_ids: list[str]
    generation_method: str
    degraded: bool
    fallback_reason: str | None
    idempotent_replay: bool


class CurrentIdentityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None
    role: str | None
    clinic_id: str | None
    patient_id: str | None
    display_name: str | None
    clinic_name: str | None
    authenticated: bool


# --- M6 Patient View (explicit field projection; extra keys are forbidden) ---
class PatientViewSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_artifact_id: str
    event_id: str
    event_time: datetime
    instruction: str
    follow_up: str | None = None


class PatientViewInstruction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    event_id: str
    event_time: datetime
    instruction: str
    follow_up: str | None = None


class PatientViewUpcoming(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_artifact_id: str
    event_id: str
    event_time: datetime
    kind: Literal["follow_up"]
    text: str


class PatientViewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: str
    event_type: str
    started_at: datetime
    ended_at: datetime | None = None


class PatientViewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    patient_id: str
    display_name: str
    current_summary: PatientViewSummary | None
    instructions: list[PatientViewInstruction]
    upcoming: list[PatientViewUpcoming]
    sessions: list[PatientViewSession]


# --- D1 Identity, Invite, Login and Session ---------------------------------
INVITE_ROLES = ("patient", "staff", "clinician", "admin")


class InviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    role: Literal["patient", "staff", "clinician", "admin"]
    # Required for patient invites (bound to the same clinic); forbidden for
    # clinical roles. The inviter can never choose a clinic — it is ctx.clinic_id.
    patient_id: str | None = None


class InviteCreatedOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_id: str
    email: str
    role: str
    patient_id: str | None
    expires_at: datetime
    # One-time copy link carrying the raw token; never returned again.
    invite_link: str


class InviteOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    invite_id: str
    email: str
    role: str
    patient_id: str | None
    created_by: str
    created_at: datetime
    expires_at: datetime
    used_at: datetime | None
    status: Literal["pending", "used", "expired"]


class InvitePreviewOut(BaseModel):
    """Minimal invite context for the accept-invite page.

    A token the caller actually holds may reveal its own binding; an unknown
    token gets the uniform 404 (no invite existence enumeration).
    """
    model_config = ConfigDict(extra="forbid")

    status: Literal["valid", "used", "expired"]
    email_masked: str
    role: str
    clinic_name: str
    patient_name: str | None
    expires_at: datetime


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1)
    password: str = Field(min_length=8, max_length=128)
    # Display name for clinical roles. For patient invites the name is ignored:
    # the bound Patient record is authoritative (invite binding wins).
    name: str | None = Field(default=None, max_length=255)


class RegisterOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    email: str
    role: str
    clinic_id: str


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=1, max_length=256)


class LogoutOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["logged_out"]
