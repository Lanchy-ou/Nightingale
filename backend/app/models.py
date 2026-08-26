"""M1 data model. Only the five tables required for M1.

Span is NOT a table — it is expressed as a JSON pointer inside
Artifact.provenance_pointer. Comment / Version / Task / AuditLog arrive in
Phase 3 and are deliberately absent here.

Field names intentionally leave room for later encryption of content columns
(content / provenance_pointer are large JSON/Text fields).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Allowed values (enforced by the seed fixture + tests, not DB constraints in M1).
ROLES = ("patient", "staff", "clinician", "admin")
EVENT_TYPES = (
    "patient_ai_preconsult",
    "nurse_consult",
    "doctor_consult",
    "patient_followup",
    "clinician_review",
    "historical_review",
)
ARTIFACT_TYPES = (
    "raw_conversation",
    "transcript",
    "clinician_note",
    "staff_note",
    "ai_doctor_consult_summary",
    "ai_nurse_consult_summary",
    "ai_patient_session_summary",
    "patient_instruction",
)

HIGHLIGHT_STATUSES = ("suggested", "accepted", "rejected", "pinned")

COMMENT_ANCHOR_TYPES = ("event", "artifact")

AUDIT_ACTIONS = (
    "create_note",
    "edit_note",
    "revert",
    "comment",
    "resolve",
    "unresolve",
    "highlight_status",
    "conflict",
)


class Clinic(Base):
    __tablename__ = "clinics"

    clinic_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # Maps a patient-role user to their own Patient record (M3).
    patient_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=True
    )


class Patient(Base):
    __tablename__ = "patients"

    patient_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # Real-world clinical time axis (what the Timeline sorts by).
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Record-keeping time axis.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("events.event_id"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # AI-scribed artifacts are always "system"; human notes use their role.
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    author_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance_pointer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Namespaced idempotency key (raw sources only); globally unique.
    ingestion_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    # Metadata-only generation record for AI artifacts (never prompt/raw text).
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class Highlight(Base):
    __tablename__ = "highlights"

    highlight_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_id: Mapped[str] = mapped_column(String(64), nullable=False)  # derived-from (AI summary / note)
    source_artifact_id: Mapped[str] = mapped_column(String(64), nullable=False)  # contains the quote
    source_span: Mapped[dict] = mapped_column(JSON, nullable=False)
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    risk_reason: Mapped[str] = mapped_column(String(512), nullable=False)
    feature_flags: Mapped[dict] = mapped_column(JSON, nullable=False)
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested")
    # Temporary audit field; folds into AuditLog in Phase 3.
    status_history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # M4: deterministic ranking / conflict / provenance fields.
    entity_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    entity_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    assertion_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    conflict_with_artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    review_status: Mapped[str | None] = mapped_column(String(16), nullable=True)


class Comment(Base):
    __tablename__ = "comments"

    comment_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    anchor_type: Mapped[str] = mapped_column(String(16), nullable=False)  # event | artifact
    anchor_id: Mapped[str] = mapped_column(String(64), nullable=False)  # polymorphic, no FK
    parent_comment_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    author_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False
    )
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    body: Mapped[str] = mapped_column(String(4000), nullable=False)
    mentions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    resolved: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    resolved_by: Mapped[str | None] = mapped_column(String(64), nullable=True)


class ArtifactVersion(Base):
    __tablename__ = "artifact_versions"
    __table_args__ = (UniqueConstraint("artifact_id", "version", name="uq_artifact_version"),)

    version_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifacts.artifact_id"), nullable=False, index=True
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[dict] = mapped_column(JSON, nullable=False)  # full snapshot
    actor_id: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    audit_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clinic_id: Mapped[str] = mapped_column(String(64), nullable=False)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
