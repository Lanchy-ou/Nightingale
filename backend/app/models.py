"""Nightingale relational model.

Span is NOT a table — it is expressed as a JSON pointer inside Artifact,
Highlight and Task provenance fields. Task is a first-class D2 entity; its
status history is metadata-only AuditLog data rather than a second authority.

Field names intentionally leave room for later encryption of content columns
(content / provenance_pointer are large JSON/Text fields).
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    JSON,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base

# Allowed values (enforced by the seed fixture + tests, not DB constraints in M1).
ROLES = ("patient", "staff", "clinician", "admin")
EVENT_TYPES = (
    "patient_checkin",
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

WORKFLOW_KINDS = ("patient_report_response", "care_action_chain")
WORKFLOW_STATUSES = ("active", "completed", "cancelled")
WORKFLOW_NODE_TYPES = ("event", "task")
WORKFLOW_RELATION_TYPES = (
    "triggered_review",
    "triggered_action",
    "verification_updates",
    "depends_on",
    "requires_action",
    "follow_up_for",
    "superseded_by",
)

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
    "doctor_consult_create",
    "nurse_consult_create",
    "source_ingest",
    "ai_generate",
    "ai_fallback",
    # D1 identity/access (metadata only — never secrets, passwords or tokens).
    "invite_created",
    "register",
    "login_success",
    "login_failure",
    "logout",
    "session_revoked",
    "account_disabled",
    "account_reactivated",
    # D2 care-task lifecycle (metadata-only status history).
    "task_create",
    "task_transition",
    "patient_review_verify",
    "patient_review_escalate",
    "clinician_review_complete",
    # Patient Check-in lifecycle (metadata-only; message text is never audited).
    "checkin_start",
    "checkin_message",
    "checkin_state",
    # Device-level Admin settings. Details are metadata-only and never keys.
    "system_ai_mode_changed",
    "system_key_rotated",
    "system_key_removed",
    "system_voice_changed",
    "voice_model_started",
    "voice_model_completed",
    "voice_model_failed",
)

TASK_STATUSES = ("open", "in_progress", "reported_done", "completed", "cancelled")
TASK_ASSIGNED_ROLES = ("patient", "staff", "clinician")
TASK_KINDS = ("care_action", "patient_report_review", "clinician_priority_review")


class Clinic(Base):
    __tablename__ = "clinics"

    clinic_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)


class SystemSettings(Base):
    """One device-level settings row; secrets live outside the database."""

    __tablename__ = "system_settings"

    settings_id: Mapped[str] = mapped_column(String(32), primary_key=True)
    deployment_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    ai_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="local")
    voice_enabled: Mapped[bool] = mapped_column(nullable=False, default=False)
    deepseek_secret_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    deepseek_key_suffix: Mapped[str | None] = mapped_column(String(8), nullable=True)
    deepseek_key_source: Mapped[str | None] = mapped_column(String(32), nullable=True)
    deepseek_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # Professional identity is presentation metadata, never an RBAC authority.
    professional_title: Mapped[str | None] = mapped_column(String(128), nullable=True)
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
    # Optional explicit grouping for Events from the same real-world clinic visit.
    # Never infer grouping from date/time; C1 deliberately has no Encounter table.
    encounter_id: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    # Real-world clinical time axis (what the Timeline sorts by).
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Record-keeping time axis.
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class Artifact(Base):
    __tablename__ = "artifacts"

    artifact_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("events.event_id", deferrable=True, initially="DEFERRED"),
        nullable=False,
        index=True,
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    # AI-scribed artifacts are always "system"; human notes use their role.
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    author_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("users.user_id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    content: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    provenance_pointer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Namespaced idempotency key (raw sources only); globally unique.
    ingestion_key: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    # Metadata-only generation record for AI artifacts (never prompt/raw text).
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    @property
    def generation_method(self) -> str | None:
        return (self.generation_metadata or {}).get("method")

    @property
    def degraded(self) -> bool:
        return bool((self.generation_metadata or {}).get("degraded", False))


class ArtifactStorageState(Base):
    """E3 maintenance metadata for a reversible shadow archive.

    ``Artifact.content`` remains authoritative.  The optional payload is only a
    verified compressed copy and is never read by the normal clinical paths.
    """

    __tablename__ = "artifact_storage_state"

    artifact_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifacts.artifact_id"), primary_key=True
    )
    tier: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    policy_version: Mapped[str] = mapped_column(String(32), nullable=False)
    evaluated_as_of: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    source_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    codec: Mapped[str | None] = mapped_column(String(32), nullable=True)
    compressed_payload: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    original_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    compressed_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    roundtrip_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True
    )


class Highlight(Base):
    __tablename__ = "highlights"
    __table_args__ = (UniqueConstraint("task_id", name="uq_highlight_task"),)

    highlight_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    # D2: task-owned highlights may be event-level (no artifact/span).
    artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # derived-from (AI summary / note)
    source_artifact_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # contains the quote
    source_span: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # Immutable provenance binding. The span is interpreted against this exact
    # source version and verified with the original quote hash.
    source_artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_quote_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # D2 explicit Task↔Glance mapping: exactly one Task may own a Highlight and
    # exactly one Highlight may represent a Task. Never inferred from the Event.
    task_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("tasks.task_id"),
        nullable=True,
        index=True,
    )
    text: Mapped[str] = mapped_column(String(512), nullable=False)
    risk_reason: Mapped[str] = mapped_column(String(512), nullable=False)
    feature_flags: Mapped[dict] = mapped_column(JSON, nullable=False)
    # E2 separates the transparent deterministic score from bounded adaptive
    # learning and the E3-reserved decay component. ``importance_score`` stays
    # the stored final score used by the Glance read path.
    base_importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    adaptive_adjustment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    decay_adjustment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    importance_score: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # Counts/reason only. Never stores Highlight/source/comment/note text.
    learning_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    score_rule_version: Mapped[str] = mapped_column(
        String(32), nullable=False, default="importance-v1"
    )
    score_factors: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
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


class ImportanceFeedback(Base):
    """Append-only, clinic-scoped E2 ranking feedback metadata."""

    __tablename__ = "importance_feedback"

    feedback_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    highlight_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("highlights.highlight_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    actor_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False, index=True
    )
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    signal_value: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


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
    # Nullable since D1: auth events (e.g. login_failure for an unknown email)
    # may have no resolved actor, role, clinic or patient context. Clinical
    # events always populate these fields. No secrets are ever stored.
    actor_id: Mapped[str | None] = mapped_column(
        String(64),
        ForeignKey("users.user_id", deferrable=True, initially="DEFERRED"),
        nullable=True,
    )
    actor_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    target_type: Mapped[str] = mapped_column(String(16), nullable=False)
    target_id: Mapped[str] = mapped_column(String(64), nullable=False)
    from_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    to_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    clinic_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    patient_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    event_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Structured metadata only. D2 uses this for task status history; raw task
    # descriptions and clinical content are never copied here.
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CareWorkflow(Base):
    """One explicit clinic/patient-scoped operational handling process.

    This is metadata-only workflow identity. It never replaces the root Event
    or stores copied clinical content.
    """

    __tablename__ = "care_workflows"
    __table_args__ = (
        CheckConstraint(
            "workflow_kind IN ('patient_report_response', 'care_action_chain')",
            name="ck_care_workflow_kind",
        ),
        CheckConstraint(
            "status IN ('active', 'completed', 'cancelled')",
            name="ck_care_workflow_status",
        ),
        CheckConstraint(
            "created_by_role IN ('system', 'staff', 'clinician')",
            name="ck_care_workflow_creator_role",
        ),
    )

    workflow_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    workflow_kind: Mapped[str] = mapped_column(String(32), nullable=False)
    root_event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("events.event_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    created_by_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Task(Base):
    """First-class, provenance-linked care action (D2)."""

    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("events.event_id"), nullable=False, index=True
    )
    source_artifact_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("artifacts.artifact_id"), nullable=True
    )
    source_span: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(String(4000), nullable=False)
    task_kind: Mapped[str] = mapped_column(
        String(32), nullable=False, default="care_action", index=True
    )
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    attention_class: Mapped[str] = mapped_column(
        String(32), nullable=False, default="routine"
    )
    creation_method: Mapped[str] = mapped_column(
        String(32), nullable=False, default="human"
    )
    verification_outcome: Mapped[str] = mapped_column(
        String(32), nullable=False, default="not_required"
    )
    escalate_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    escalated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    review_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    time_sensitivity: Mapped[str | None] = mapped_column(String(32), nullable=True)
    follow_up_task_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("tasks.task_id"), nullable=True
    )
    routing_metadata: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    source_artifact_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_quote_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_role: Mapped[str] = mapped_column(String(32), nullable=False)
    assigned_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    patient_visible: Mapped[bool] = mapped_column(nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    reported_done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    cancelled_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "task_kind", "assigned_role", name="uq_task_workflow_role"
        ),
    )


class WorkflowLink(Base):
    """A validated directed edge between the workflow root and Task steps."""

    __tablename__ = "workflow_links"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "from_type",
            "from_id",
            "relation_type",
            "to_type",
            "to_id",
            name="uq_workflow_link_edge",
        ),
        CheckConstraint(
            "from_type IN ('event', 'task')", name="ck_workflow_link_from_type"
        ),
        CheckConstraint("to_type = 'task'", name="ck_workflow_link_to_type"),
        CheckConstraint(
            "relation_type IN ('triggered_review', 'triggered_action', "
            "'verification_updates', 'depends_on', 'requires_action', "
            "'follow_up_for', 'superseded_by')",
            name="ck_workflow_link_relation",
        ),
        CheckConstraint(
            "created_by_role IN ('system', 'staff', 'clinician')",
            name="ck_workflow_link_creator_role",
        ),
    )

    link_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("care_workflows.workflow_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    from_type: Mapped[str] = mapped_column(String(16), nullable=False)
    from_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    relation_type: Mapped[str] = mapped_column(String(32), nullable=False)
    to_type: Mapped[str] = mapped_column(String(16), nullable=False, default="task")
    to_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_by_role: Mapped[str] = mapped_column(String(32), nullable=False)
    created_by_user_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PatientReviewItem(Base):
    """One Nurse decision for one exact-source patient-report candidate."""

    __tablename__ = "patient_review_items"
    __table_args__ = (
        UniqueConstraint("workflow_id", "highlight_id", name="uq_patient_review_item"),
    )

    review_item_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    workflow_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    staff_task_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("tasks.task_id"), nullable=False, index=True
    )
    highlight_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("highlights.highlight_id"), nullable=False, index=True
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    correction_artifact_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("artifacts.artifact_id"), nullable=True
    )
    reviewed_by: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class GlanceProjection(Base):
    """PHI-free, precomputed role-specific Glance eligibility and ordering."""

    __tablename__ = "glance_projections"
    __table_args__ = (
        UniqueConstraint("highlight_id", "viewer_role", name="uq_glance_projection_role"),
    )

    projection_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    highlight_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("highlights.highlight_id"), nullable=False, index=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    viewer_role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority_band: Mapped[int] = mapped_column(Integer, nullable=False)
    final_score: Mapped[int] = mapped_column(Integer, nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    factor_explanation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class RankingRun(Base):
    """Immutable, content-free snapshot of one role-specific ranking decision."""

    __tablename__ = "ranking_runs"
    __table_args__ = (
        UniqueConstraint(
            "clinic_id",
            "patient_id",
            "viewer_role",
            "state_fingerprint",
            "policy_version",
            name="uq_ranking_run_state",
        ),
    )

    run_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True)
    patient_id: Mapped[str] = mapped_column(String(64), ForeignKey("patients.patient_id"), nullable=False, index=True)
    viewer_role: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    rule_version: Mapped[str] = mapped_column(String(32), nullable=False)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    top_k: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    state_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    evaluated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class RankingDecision(Base):
    __tablename__ = "ranking_decisions"
    __table_args__ = (
        UniqueConstraint("run_id", "highlight_id", name="uq_ranking_decision_candidate"),
    )

    decision_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(64), ForeignKey("ranking_runs.run_id"), nullable=False, index=True)
    highlight_id: Mapped[str] = mapped_column(String(64), ForeignKey("highlights.highlight_id"), nullable=False, index=True)
    workflow_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    feedback_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    eligible: Mapped[bool] = mapped_column(Boolean, nullable=False)
    exclusion_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    priority_band: Mapped[int] = mapped_column(Integer, nullable=False)
    factor_snapshot: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    base_score: Mapped[int] = mapped_column(Integer, nullable=False)
    shadow_adjustment: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    shadow_score: Mapped[int] = mapped_column(Integer, nullable=False)
    base_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    shadow_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    surfaced_base: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    surfaced_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    source_binding_status: Mapped[str] = mapped_column(String(32), nullable=False)


class LearningSignal(Base):
    __tablename__ = "learning_signals"

    signal_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(96), ForeignKey("ranking_decisions.decision_id"), nullable=False, index=True)
    clinic_id: Mapped[str] = mapped_column(String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False, index=True)
    actor_role: Mapped[str] = mapped_column(String(32), nullable=False)
    signal_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    feedback_key: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    signal_value: Mapped[int] = mapped_column(Integer, nullable=False)
    eligible_for_shadow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    ineligibility_reason: Mapped[str | None] = mapped_column(String(64), nullable=True)
    independence_key: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    supersedes_signal_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class LearningPolicyVersion(Base):
    __tablename__ = "learning_policy_versions"
    __table_args__ = (
        UniqueConstraint("clinic_id", "version_name", name="uq_learning_policy_clinic_version"),
    )

    policy_id: Mapped[str] = mapped_column(String(96), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True)
    version_name: Mapped[str] = mapped_column(String(64), nullable=False)
    serving_mode: Mapped[str] = mapped_column(String(32), nullable=False, default="base_only")
    shadow_policy: Mapped[str] = mapped_column(String(64), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    frozen_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    signal_cutoff_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str | None] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class LearningEvaluation(Base):
    __tablename__ = "learning_evaluations"

    evaluation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True)
    policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    run_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    metrics: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_by: Mapped[str] = mapped_column(String(64), ForeignKey("users.user_id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)


class Invite(Base):
    """Clinic-scoped registration invite (D1).

    - clinician/staff/admin join only through a clinic invite;
    - a patient invite is pre-bound to clinic_id + patient_id;
    - only the SHA-256 hash of the one-time token is persisted;
    - the raw token is returned exactly once, embedded in the invite link.
    """
    __tablename__ = "invites"

    invite_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(255), nullable=False)
    email_normalized: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    # Required for patient invites; NULL for clinical roles.
    patient_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_by: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class UserCredential(Base):
    """Login credential (D1). Argon2id password hash only — never plaintext."""
    __tablename__ = "user_credentials"

    user_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("users.user_id", deferrable=True, initially="DEFERRED"),
        primary_key=True,
    )
    email_normalized: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    password_changed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    disabled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuthSession(Base):
    """Server-side login session (D1).

    The bearer token travels only in the HttpOnly cookie; the database stores
    only its SHA-256 hash. Expiry, revocation and account disablement are all
    enforced server-side on every request.
    """
    __tablename__ = "auth_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False, index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class PatientCheckInSession(Base):
    """One bounded Check-in mapped to one longitudinal Patient Event.

    Draft visibility is controlled by ``status``. ``active_key`` is populated
    only while a session is active/awaiting confirmation, giving each patient
    user one recoverable active session without a second chat silo.
    """

    __tablename__ = "patient_checkin_sessions"

    session_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("events.event_id"), nullable=False, unique=True
    )
    raw_artifact_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("artifacts.artifact_id"), nullable=False, unique=True
    )
    patient_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patients.patient_id"), nullable=False, index=True
    )
    clinic_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("clinics.clinic_id"), nullable=False, index=True
    )
    patient_user_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("users.user_id"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    active_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, unique=True
    )
    clarification_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    safety_reason_codes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    abandoned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class PatientCheckInMessage(Base):
    """Stable, append-only message row for a Patient Check-in.

    The raw Artifact is the longitudinal presentation; rows here enforce
    message idempotency and one AI response per patient message.
    """

    __tablename__ = "patient_checkin_messages"
    __table_args__ = (
        UniqueConstraint("session_id", "sequence", name="uq_checkin_message_sequence"),
        UniqueConstraint(
            "response_to_message_id", name="uq_checkin_message_response_to"
        ),
    )

    message_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("patient_checkin_sessions.session_id"), nullable=False, index=True
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    intent: Mapped[str | None] = mapped_column(String(32), nullable=True)
    text: Mapped[str] = mapped_column(String(8000), nullable=False)
    question_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    conversation_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    referenced_patient_message_ids: Mapped[list] = mapped_column(
        JSON, nullable=False, default=list
    )
    response_to_message_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("patient_checkin_messages.message_id"), nullable=True
    )
    processing_status: Mapped[str | None] = mapped_column(String(16), nullable=True)
    generation_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
