"""Pydantic v2 response schemas for the M1 read-only API."""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    actor_id: str
    actor_role: str
    action: str
    target_type: str
    target_id: str
    from_version: int | None
    to_version: int | None
    clinic_id: str
    patient_id: str
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
