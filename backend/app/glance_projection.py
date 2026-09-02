"""F_A2 precomputed, PHI-free role-specific Glance projections."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .highlights import SCORE_RULE_VERSION, score_factor_breakdown
from .models import Artifact, Event, GlanceProjection, Highlight, Task

GLANCE_RULE_VERSION = "attention-v1"
CLINICAL_ROLES = ("staff", "clinician")
TERMINAL_TASK_STATUSES = {"completed", "cancelled"}


def _eligibility(
    highlight: Highlight,
    task: Task | None,
    summary: Artifact | None,
    role: str,
    has_patient_review_workflow: bool,
) -> tuple[bool, str | None]:
    if highlight.status == "rejected":
        return False, "rejected"
    if task is not None and task.status in TERMINAL_TASK_STATUSES:
        return False, "terminal_task"
    if (
        highlight.status == "pinned"
        or highlight.review_status == "needs_review"
        or highlight.feature_flags.get("explicit_risk")
    ):
        return True, None
    if (
        task is None
        and summary is not None
        and summary.artifact_type == "ai_patient_session_summary"
        and has_patient_review_workflow
    ):
        return False, "patient_candidate_review_context"
    if task is not None and task.task_kind == "patient_report_review" and role != "staff":
        return False, "staff_work_queue_only"
    if task is not None and task.task_kind == "clinician_priority_review" and role != "clinician":
        return False, "clinician_work_queue_only"
    if (
        highlight.entity_type == "allergy"
        and highlight.feature_flags.get("clinician_confirmed")
    ):
        return False, "fixed_safety_context"
    return True, None


def _priority_band(
    highlight: Highlight,
    task: Task | None,
    role: str,
    as_of: datetime,
) -> tuple[int, list[str]]:
    reasons: list[str] = []
    if (
        highlight.status == "pinned"
        or highlight.review_status == "needs_review"
        or highlight.feature_flags.get("explicit_risk")
    ):
        reasons.append("protected_or_needs_review")
        return 1, reasons
    if task is not None and task.attention_class == "priority_review":
        reasons.append("current_role_priority_review")
        return 2, reasons
    if task is not None and task.task_kind == "patient_report_review" and (
        task.escalated_at is not None or (task.escalate_at is not None and task.escalate_at <= as_of)
    ):
        reasons.append("verification_overdue")
        return 3, reasons
    if task is not None and task.due_at is not None and task.due_at <= as_of:
        reasons.append("care_task_overdue")
        return 4, reasons
    if task is not None and task.assigned_role == role:
        reasons.append("current_role_unresolved_task")
        return 5, reasons
    if task is not None and task.task_kind == "patient_report_review":
        reasons.append("routine_patient_review")
        return 6, reasons
    reasons.append("other_unresolved")
    return 7, reasons


def rebuild_glance_projections(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
) -> None:
    """Rebuild one patient's two role projections on write paths only."""
    evaluated_at = as_of or datetime.now()
    db.execute(delete(GlanceProjection).where(GlanceProjection.patient_id == patient_id))
    highlights = db.scalars(
        select(Highlight).where(Highlight.patient_id == patient_id)
    ).all()
    for highlight in highlights:
        event = db.get(Event, highlight.event_id)
        if event is None:
            continue
        task = db.get(Task, highlight.task_id) if highlight.task_id else None
        summary = db.get(Artifact, highlight.artifact_id) if highlight.artifact_id else None
        has_patient_review_workflow = bool(
            db.scalar(
                select(Task.task_id).where(
                    Task.event_id == highlight.event_id,
                    Task.task_kind == "patient_report_review",
                )
            )
        )
        factors = score_factor_breakdown(
            highlight.feature_flags,
            adaptive_adjustment=0,
            decay_adjustment=highlight.decay_adjustment,
        )
        # F_A1 serving is permanently base-only. Historical E2 adjustment is
        # retained in importance_feedback and evaluated only by Shadow policy.
        highlight.base_importance_score = factors["base_total"]
        highlight.adaptive_adjustment = 0
        highlight.importance_score = factors["final_total"]
        # Persist the score's own reproducible arithmetic independently from
        # role-specific ranking bands.
        highlight.score_rule_version = SCORE_RULE_VERSION
        highlight.score_factors = factors
        db.add(highlight)
        for role in CLINICAL_ROLES:
            eligible, exclusion = _eligibility(
                highlight, task, summary, role, has_patient_review_workflow
            )
            band, reasons = _priority_band(highlight, task, role, evaluated_at)
            db.add(
                GlanceProjection(
                    projection_id=f"gp_{highlight.highlight_id}_{role}",
                    highlight_id=highlight.highlight_id,
                    patient_id=highlight.patient_id,
                    clinic_id=event.clinic_id,
                    viewer_role=role,
                    eligible=eligible,
                    exclusion_reason=exclusion,
                    priority_band=band,
                    final_score=highlight.importance_score,
                    due_at=task.due_at if task else None,
                    factor_explanation={
                        "priority_band": band,
                        "priority_reasons": reasons,
                        "eligible": eligible,
                        "exclusion_reason": exclusion,
                        "score": factors,
                    },
                    rule_version=GLANCE_RULE_VERSION,
                    updated_at=evaluated_at,
                )
            )
    db.flush()
    from .shadow_learning import capture_ranking_runs

    capture_ranking_runs(db, patient_id, evaluated_at=evaluated_at)
