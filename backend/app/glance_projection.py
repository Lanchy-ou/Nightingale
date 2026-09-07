"""F_A2 precomputed, PHI-free role-specific Glance projections."""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import and_, case, delete, func, or_, select
from sqlalchemy.orm import Session

from .highlights import SCORE_RULE_VERSION, is_recent, score_factor_breakdown
from .attention_items import build_attention_items
from .models import Event, GlanceProjection, Highlight, Task
from .workflow_state import refresh_workflow_status

GLANCE_RULE_VERSION = "attention-v1"
CLINICAL_ROLES = ("staff", "clinician")
TERMINAL_TASK_STATUSES = {"completed", "cancelled"}


def rebuild_glance_projections(
    db: Session,
    patient_id: str,
    *,
    as_of: datetime | None = None,
) -> None:
    """Rebuild one patient's two role projections on write paths only."""
    evaluated_at = as_of or datetime.now()
    # SessionLocal disables autoflush; time snapshots must include the caller's
    # pending Task/Event changes in this same transaction.
    db.flush()
    db.execute(delete(GlanceProjection).where(GlanceProjection.patient_id == patient_id))
    highlights = db.scalars(
        select(Highlight).where(Highlight.patient_id == patient_id)
    ).all()
    event_times = dict(db.execute(select(Event.event_id, Event.started_at).where(
        Event.patient_id == patient_id,
    )).all())
    task_times = dict(db.execute(select(Task.task_id, Task.created_at).where(
        Task.patient_id == patient_id,
    )).all())
    for workflow_id in sorted(
        {
            workflow_id
            for workflow_id in db.scalars(
                select(Task.workflow_id).where(
                    Task.patient_id == patient_id, Task.workflow_id.is_not(None)
                )
            ).all()
            if workflow_id
        }
    ):
        refresh_workflow_status(db, workflow_id, as_of=evaluated_at)
    for highlight in highlights:
        # A new task is current work even when its origin Event is historical.
        occurred_at = task_times.get(highlight.task_id) or event_times[highlight.event_id]
        highlight.feature_flags = {
            **highlight.feature_flags,
            "recency": is_recent(occurred_at, evaluated_at),
        }
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
    db.flush()
    by_highlight = {highlight.highlight_id: highlight for highlight in highlights}
    for role in CLINICAL_ROLES:
        for item in build_attention_items(
            db,
            patient_id=patient_id,
            viewer_role=role,
            as_of=evaluated_at,
        ):
            highlight = by_highlight[item.highlight_id]
            snapshot = item.factor_snapshot()
            snapshot["score"] = dict(highlight.score_factors or {})
            db.add(
                GlanceProjection(
                    projection_id=f"gp_{item.highlight_id}_{role}",
                    highlight_id=item.highlight_id,
                    patient_id=item.patient_id,
                    clinic_id=item.clinic_id,
                    viewer_role=role,
                    eligible=item.eligible,
                    exclusion_reason=item.exclusion_reason,
                    priority_band=item.priority_band,
                    final_score=item.final_score,
                    due_at=item.due_at,
                    factor_explanation=snapshot,
                    rule_version=GLANCE_RULE_VERSION,
                    updated_at=evaluated_at,
                )
            )
    db.flush()
    from .shadow_learning import capture_ranking_runs

    capture_ranking_runs(db, patient_id, evaluated_at=evaluated_at)


def refresh_time_sensitive_glance(db: Session, *, as_of: datetime | None = None) -> int:
    """Refresh only crossed recency/due boundaries in the maintenance worker.

    Reads metadata only; unchanged projections produce no new ranking runs.
    The Glance GET remains a materialized read with no Provider call.
    """
    now = as_of or datetime.now()
    occurred_at = func.coalesce(Task.created_at, Event.started_at)
    recent = case((and_(occurred_at <= now, occurred_at >= now - timedelta(days=7)), True), else_=False)
    changed = set(db.scalars(
        select(Highlight.patient_id)
        .join(Event, Event.event_id == Highlight.event_id)
        .outerjoin(Task, Task.task_id == Highlight.task_id)
        .where(func.coalesce(Highlight.feature_flags["recency"].as_boolean(), False) != recent)
        .distinct()
    ).all())
    changed.update(db.scalars(
        select(GlanceProjection.patient_id)
        .join(Highlight, Highlight.highlight_id == GlanceProjection.highlight_id)
        .join(Task, Task.task_id == Highlight.task_id)
        .where(
            Task.status.not_in(TERMINAL_TASK_STATUSES),
            Task.due_at.is_not(None),
            or_(
                and_(GlanceProjection.updated_at < Task.due_at, Task.due_at <= now),
                and_(now < Task.due_at, Task.due_at <= GlanceProjection.updated_at),
            ),
        ).distinct()
    ).all())
    for patient_id in sorted(changed):
        rebuild_glance_projections(db, patient_id, as_of=now)
    return len(changed)
