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
    artifact_id: str | None
    source_artifact_id: str | None
    source_span: dict | None
    # D2: explicit Task↔Glance mapping (null for non-task highlights).
    task_id: str | None = None
    text: str
    risk_reason: str
    feature_flags: dict
    base_importance_score: int
    adaptive_adjustment: int
    decay_adjustment: int
    importance_score: int
    learning_metadata: dict
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
    details: dict | None
    created_at: datetime


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["staff_note", "clinician_note", "patient_instruction"]
    content: dict
    confirmation_token: str | None = Field(default=None, max_length=8192)


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


# --- Bounded persistent Patient Check-in ----------------------------------
CHECKIN_QUESTION_TYPES = (
    "severity",
    "change",
    "associated_symptoms",
    "task_progress",
    "patient_concern",
)


class CheckInStartRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    session_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class CheckInPatientMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    message_id: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    intent: Literal["answer", "supplement", "correction", "skip", "no_more"]
    text: str = Field(default="", max_length=8000)

    @model_validator(mode="after")
    def bounded_text(self):
        self.text = self.text.strip()
        if self.intent not in {"skip", "no_more"} and not self.text:
            raise ValueError("text is required for this message intent")
        if self.intent in {"skip", "no_more"} and not self.text:
            self.text = "I would prefer to skip this question." if self.intent == "skip" else "I have nothing else to add."
        return self


class CheckInStateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_status: Literal[
        "active", "awaiting_confirmation", "submitted", "safety_escalated", "abandoned"
    ]


class CheckInTurnResult(BaseModel):
    """Strict provider result; state/safety/round authority stays server-side."""

    model_config = ConfigDict(extra="forbid")

    acknowledgement: str = Field(min_length=1, max_length=1000)
    next_question: str | None = Field(default=None, max_length=1000)
    question_type: Literal[
        "severity", "change", "associated_symptoms", "task_progress", "patient_concern"
    ] | None = None
    conversation_action: Literal["continue", "await_confirmation"]
    referenced_patient_message_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def action_matches_question(self):
        if self.conversation_action == "continue":
            if not self.next_question or self.question_type is None:
                raise ValueError("continue requires one bounded next question")
        elif self.next_question is not None or self.question_type is not None:
            raise ValueError("await_confirmation cannot include a next question")
        if len(set(self.referenced_patient_message_ids)) != len(self.referenced_patient_message_ids):
            raise ValueError("referenced message ids must be unique")
        return self


class CheckInSummaryCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=512)
    patient_message_id: str = Field(min_length=1, max_length=64)
    quote: str = Field(min_length=1, max_length=4000)
    risk_reason: str = Field(min_length=1, max_length=512)
    entity_type: Literal["symptom", "medication", "allergy", "chief_complaint", "task", "risk"]
    assertion_value: str | None = Field(default=None, max_length=255)
    symptom_change: bool = False


class CheckInSummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str = Field(min_length=1, max_length=4000)
    referenced_patient_message_ids: list[str] = Field(min_length=1, max_length=100)
    candidates: list[CheckInSummaryCandidate] = Field(default_factory=list, max_length=50)


class CheckInMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    message_id: str
    sequence: int
    role: Literal["patient", "ai"]
    intent: str | None
    text: str
    question_type: str | None
    conversation_action: str | None
    referenced_patient_message_ids: list[str]
    response_to_message_id: str | None
    processing_status: str | None
    generation_method: str | None = None
    degraded: bool = False
    created_at: datetime


class CheckInSessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_id: str
    event_id: str
    status: Literal["active", "awaiting_confirmation", "submitted", "safety_escalated", "abandoned"]
    clarification_count: int
    max_clarification_questions: int
    safety_escalated: bool
    safety_message: str | None
    started_at: datetime
    ended_at: datetime | None
    submitted_at: datetime | None
    messages: list[CheckInMessageOut]
    preview_summary: list[str]
    formal_summary_created: bool
    resumed: bool = False


class CheckInListOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active_session_id: str | None
    sessions: list[CheckInSessionOut]


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


# --- E1 Nurse Consult ingestion (separate authority and speaker contract) ---
class NurseTranscriptSegment(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    index: int = Field(ge=0)
    speaker: Literal["nurse", "patient"]
    text: str = Field(min_length=1, max_length=4000)

    @field_validator("text")
    @classmethod
    def trim_non_empty_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("segment text must not be empty")
        return value


class NurseTranscriptContent(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    segments: list[NurseTranscriptSegment] = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def continuous_indexes(self):
        indexes = [segment.index for segment in self.segments]
        if indexes != list(range(len(indexes))):
            raise ValueError("segment indexes must start at 0 and be continuous")
        return self


class NurseConsultCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    consult_id: str = Field(min_length=1, max_length=64)
    ingestion_key: str = Field(min_length=1, max_length=64)
    started_at: datetime = Field(strict=False)
    ended_at: datetime | None = Field(default=None, strict=False)
    encounter_id: str | None = Field(default=None, min_length=1, max_length=64)
    content: NurseTranscriptContent

    @field_validator("consult_id", "ingestion_key", "encounter_id")
    @classmethod
    def trim_non_empty_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("identifier must not be empty")
        return value

    @model_validator(mode="after")
    def valid_time_range(self):
        if self.ended_at is not None and self.ended_at < self.started_at:
            raise ValueError("ended_at must be >= started_at")
        return self


class NurseConsultOut(BaseModel):
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


# --- D3 raw transcript normalization preview (no persistence / no LLM) ---
class TranscriptNormalizeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    raw_text: str = Field(min_length=1)


class TranscriptPreviewSegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    speaker_candidate: Literal["doctor", "patient"] | None
    text: str
    source_start: int
    source_end: int
    confidence_marker: Literal["exact_label", "mapped_label", "inferred_boundary", "unknown"]
    issues: list[str]


class NurseTranscriptPreviewSegmentOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    index: int
    speaker_candidate: Literal["nurse", "patient"] | None
    text: str
    source_start: int
    source_end: int
    confidence_marker: Literal["exact_label", "mapped_label", "inferred_boundary", "unknown"]
    issues: list[str]


class TranscriptNormalizeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["ACCEPT", "NEEDS_REVIEW", "REJECT"]
    normalize_reason: str | None
    raw_byte_length: int
    segments: list[TranscriptPreviewSegmentOut]
    issues: list[str]


class NurseTranscriptNormalizeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    outcome: Literal["ACCEPT", "NEEDS_REVIEW", "REJECT"]
    normalize_reason: str | None
    raw_byte_length: int
    segments: list[NurseTranscriptPreviewSegmentOut]
    issues: list[str]


class CurrentIdentityOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str | None
    role: str | None
    clinic_id: str | None
    patient_id: str | None
    display_name: str | None
    professional_title: str | None
    clinic_name: str | None
    authenticated: bool


# --- E1 Admin oversight: explicit metadata-only projections ----------------
class AdminUserOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    display_name: str
    email: str | None
    role: Literal["patient", "staff", "clinician", "admin"]
    professional_title: str | None
    patient_id: str | None
    account_status: Literal["active", "disabled"]
    disabled_at: datetime | None
    active_session_count: int
    last_seen_at: datetime | None


class AdminAccountStatusUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_status: Literal["active", "disabled"]
    status: Literal["active", "disabled"]

    @model_validator(mode="after")
    def status_must_change(self):
        if self.status == self.expected_status:
            raise ValueError("status must change")
        return self


class AdminSessionRevokeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    expected_active_session_count: int = Field(ge=0)


class AdminSessionRevokeOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str
    revoked_count: int


class AdminAccessAuditOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audit_id: str
    actor_id: str | None
    actor_role: str | None
    action: str
    target_type: str
    target_id: str
    details: dict | None
    created_at: datetime


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
    today: "PatientViewToday"
    care_plan: "PatientViewCarePlan"
    check_in: "PatientViewCheckIn"
    visit_summaries: "PatientViewVisitSummaries"


# --- D2 Care Tasks + patient-safe product projection ----------------------
class TaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    description: str = Field(default="", max_length=4000)
    assigned_role: Literal["patient", "staff", "clinician"]
    assigned_user_id: str | None = None
    patient_visible: bool = False
    due_at: datetime | None = None
    source_artifact_id: str | None = None
    source_span: dict | None = None
    confirmation_token: str | None = Field(default=None, max_length=8192)

    @field_validator("title")
    @classmethod
    def trim_task_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("title must not be empty")
        return value

    @model_validator(mode="after")
    def complete_provenance_pair(self):
        if (self.source_artifact_id is None) != (self.source_span is None):
            raise ValueError("source_artifact_id and source_span must be supplied together")
        return self


class TaskTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_status: Literal["open", "in_progress", "reported_done", "completed", "cancelled"]
    status: Literal["open", "in_progress", "reported_done", "completed", "cancelled"]


class ClinicalTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    task_id: str
    patient_id: str
    clinic_id: str
    event_id: str
    source_artifact_id: str | None
    source_span: dict | None
    title: str
    description: str
    assigned_role: str
    assigned_user_id: str | None
    patient_visible: bool
    status: str
    due_at: datetime | None
    created_by: str
    created_at: datetime
    updated_at: datetime
    reported_done_at: datetime | None
    completed_by: str | None
    completed_at: datetime | None
    cancelled_by: str | None
    cancelled_at: datetime | None


class PatientTaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    task_id: str
    title: str
    status: str
    due_at: datetime | None
    updated_at: datetime
    reported_done_at: datetime | None
    completed_at: datetime | None
    patient_visible: bool


class TaskProvenanceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    event: EventBrief
    source_artifact: ArtifactOut | None
    span: dict | None
    quote: str | None


class PatientViewToday(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: PatientViewInstruction | None
    tasks: list[PatientTaskOut]
    next_follow_up: str | None


class PatientViewCarePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    open: list[PatientTaskOut]
    in_progress: list[PatientTaskOut]
    reported_done: list[PatientTaskOut]
    completed: list[PatientTaskOut]


class PatientViewCheckIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sessions: list[PatientViewSession]


class PatientViewVisitSummaries(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summaries: list[PatientViewInstruction]


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


class InvitePreviewRequest(BaseModel):
    """Bearer token stays in the request body, never in the API URL."""

    model_config = ConfigDict(extra="forbid")

    token: str = Field(min_length=1, max_length=512)


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
