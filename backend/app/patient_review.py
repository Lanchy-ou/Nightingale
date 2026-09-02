"""Deterministic F_A2 Patient Check-in review workflows."""
from __future__ import annotations

import os
from datetime import datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .audit import add_audit
from .glance_projection import rebuild_glance_projections
from .ids import stable_id
from .models import Artifact, Event, Highlight, PatientCheckInSession, PatientReviewItem, Task
from .tasks import link_task_highlight

ROUTING_RULE_VERSION = "patient-review-route-v1"
EXTRACTOR_VERSION = "checkin-summary-v1"
APPROVED_PRIORITY_REASON_CODES = frozenset(
    {
        "patient_explicit_worsening",
        "patient_explicit_severe_intensity",
        "patient_requests_urgent_contact",
        "patient_reports_medication_or_allergy_concern",
    }
)


def review_window_minutes() -> int:
    raw = os.environ.get("NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES", "720")
    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError("NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES must be an integer") from exc
    if value < 1 or value > 10080:
        raise RuntimeError("NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES must be 1..10080")
    return value


def _workflow_id(session_id: str) -> str:
    return f"prw_{stable_id(session_id, 'patient-review-v1')}"


def _task_id(workflow_id: str, kind: str, role: str) -> str:
    return f"tsk_{stable_id(workflow_id, kind, role)}"


def _ensure_review_items(
    db: Session, *, workflow_id: str, staff_task: Task, summary: Artifact, now: datetime
) -> None:
    candidates = db.scalars(
        select(Highlight)
        .where(Highlight.artifact_id == summary.artifact_id)
        .order_by(Highlight.created_at, Highlight.highlight_id)
    ).all()
    for candidate in candidates:
        review_item_id = f"pri_{stable_id(workflow_id, candidate.highlight_id)}"
        if db.get(PatientReviewItem, review_item_id) is not None:
            continue
        db.add(
            PatientReviewItem(
                review_item_id=review_item_id,
                workflow_id=workflow_id,
                staff_task_id=staff_task.task_id,
                highlight_id=candidate.highlight_id,
                outcome="pending",
                correction_artifact_id=None,
                reviewed_by=None,
                reviewed_at=None,
                created_at=now,
                updated_at=now,
            )
        )


def _priority_codes(summary: Artifact) -> list[str]:
    metadata = summary.generation_metadata or {}
    if metadata.get("degraded"):
        return []
    codes: set[str] = set()
    for item in summary.content.get("source_facts", []):
        if not isinstance(item, dict):
            continue
        for code in item.get("priority_review_reason_codes", []):
            if code in APPROVED_PRIORITY_REASON_CODES:
                codes.add(code)
    return sorted(codes)


def _create_review_task(
    db: Session,
    *,
    session: PatientCheckInSession,
    raw: Artifact,
    summary: Artifact,
    workflow_id: str,
    kind: str,
    role: str,
    attention_class: str,
    now: datetime,
    due_at: datetime | None,
    escalate_at: datetime | None,
    reason_codes: list[str],
) -> Task:
    task_id = _task_id(workflow_id, kind, role)
    existing = db.get(Task, task_id)
    if existing is not None:
        return existing
    title = (
        "Review priority patient update"
        if kind == "clinician_priority_review"
        else "Review submitted patient Check-in"
    )
    task = Task(
        task_id=task_id,
        patient_id=session.patient_id,
        clinic_id=session.clinic_id,
        event_id=session.event_id,
        source_artifact_id=raw.artifact_id,
        source_span=None,
        source_artifact_version=raw.version,
        source_quote_sha256=None,
        title=title,
        description="Internal review of a source-linked patient submission.",
        task_kind=kind,
        workflow_id=workflow_id,
        attention_class=attention_class,
        creation_method="system_routed",
        verification_outcome="pending" if kind == "patient_report_review" else "not_required",
        escalate_at=escalate_at,
        escalated_at=None,
        review_outcome=None,
        time_sensitivity=None,
        routing_metadata={
            "reason_codes": reason_codes,
            "extractor_version": EXTRACTOR_VERSION,
            "routing_rule_version": ROUTING_RULE_VERSION,
            "generation_method": summary.generation_method,
            "degraded": summary.degraded,
        },
        assigned_role=role,
        assigned_user_id=None,
        patient_visible=False,
        status="open",
        due_at=due_at,
        created_by=session.patient_user_id,
        created_at=now,
        updated_at=now,
        reported_done_at=None,
        completed_by=None,
        completed_at=None,
        cancelled_by=None,
        cancelled_at=None,
    )
    db.add(task)
    db.flush()
    link_task_highlight(db, task)
    add_audit(
        db,
        actor_id=session.patient_user_id,
        actor_role="patient",
        action="task_create",
        target_type="task",
        target_id=task.task_id,
        clinic_id=session.clinic_id,
        patient_id=session.patient_id,
        event_id=session.event_id,
        details={"status": "open", "creation_method": "system_routed", "task_kind": kind},
    )
    return task


def ensure_clinician_review_task(
    db: Session,
    *,
    staff_task: Task,
    now: datetime,
    reason_codes: list[str] | None = None,
) -> Task:
    session = db.scalar(
        select(PatientCheckInSession).where(
            PatientCheckInSession.event_id == staff_task.event_id
        )
    )
    if session is None:
        raise RuntimeError("patient review session is missing")
    raw = db.get(Artifact, session.raw_artifact_id)
    summary = db.scalar(
        select(Artifact).where(
            Artifact.event_id == session.event_id,
            Artifact.artifact_type == "ai_patient_session_summary",
        )
    )
    if raw is None or summary is None:
        raise RuntimeError("patient review source is missing")
    task = _create_review_task(
        db,
        session=session,
        raw=raw,
        summary=summary,
        workflow_id=staff_task.workflow_id or _workflow_id(session.session_id),
        kind="clinician_priority_review",
        role="clinician",
        attention_class="priority_review",
        now=now,
        due_at=None,
        escalate_at=None,
        reason_codes=reason_codes or list((staff_task.routing_metadata or {}).get("reason_codes", [])),
    )
    task.verification_outcome = staff_task.verification_outcome
    db.add(task)
    return task


def reconcile_patient_review_workflow(
    db: Session,
    session: PatientCheckInSession,
    *,
    as_of: datetime | None = None,
) -> tuple[Task, Task | None]:
    """Create/repair the one-session review workflow without duplicates."""
    if session.status != "submitted":
        raise RuntimeError("only submitted Check-ins can create review workflows")
    now = as_of or session.submitted_at or datetime.now()
    raw = db.get(Artifact, session.raw_artifact_id)
    summary = db.scalar(
        select(Artifact).where(
            Artifact.event_id == session.event_id,
            Artifact.artifact_type == "ai_patient_session_summary",
        )
    )
    if raw is None or summary is None:
        raise RuntimeError("submitted Check-in source/summary is missing")
    workflow_id = _workflow_id(session.session_id)
    codes = _priority_codes(summary)
    deadline = now + timedelta(minutes=review_window_minutes())
    staff_task = _create_review_task(
        db,
        session=session,
        raw=raw,
        summary=summary,
        workflow_id=workflow_id,
        kind="patient_report_review",
        role="staff",
        attention_class="priority_review" if codes else "routine",
        now=now,
        due_at=deadline,
        escalate_at=deadline,
        reason_codes=codes,
    )
    _ensure_review_items(
        db,
        workflow_id=workflow_id,
        staff_task=staff_task,
        summary=summary,
        now=now,
    )
    clinician_task = None
    if codes:
        clinician_task = ensure_clinician_review_task(
            db, staff_task=staff_task, now=now, reason_codes=codes
        )
    db.flush()
    rebuild_glance_projections(db, session.patient_id, as_of=now)
    return staff_task, clinician_task


def materialize_due_escalations(
    db: Session,
    *,
    as_of: datetime | None = None,
) -> int:
    """Idempotently escalate overdue Nurse reviews into clinician work."""
    now = as_of or datetime.now()
    tasks = db.scalars(
        select(Task).where(
            Task.task_kind == "patient_report_review",
            Task.status.in_(("open", "in_progress")),
            Task.escalate_at.is_not(None),
            Task.escalate_at <= now,
            Task.escalated_at.is_(None),
        )
    ).all()
    changed_patients: set[str] = set()
    count = 0
    for task in tasks:
        result = db.execute(
            update(Task)
            .where(Task.task_id == task.task_id, Task.escalated_at.is_(None))
            .values(escalated_at=now, updated_at=now)
        )
        if result.rowcount != 1:
            continue
        task.escalated_at = now
        ensure_clinician_review_task(db, staff_task=task, now=now)
        add_audit(
            db,
            actor_id=task.created_by,
            actor_role="patient",
            action="patient_review_escalate",
            target_type="task",
            target_id=task.task_id,
            clinic_id=task.clinic_id,
            patient_id=task.patient_id,
            event_id=task.event_id,
            details={"reason": "staff_review_overdue"},
        )
        changed_patients.add(task.patient_id)
        count += 1
    db.flush()
    for patient_id in changed_patients:
        rebuild_glance_projections(db, patient_id, as_of=now)
    return count
