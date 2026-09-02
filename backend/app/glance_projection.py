"""F_A2 precomputed, PHI-free role-specific Glance projections."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .highlights import SCORE_RULE_VERSION, score_factor_breakdown
from .attention_items import build_attention_items
from .models import GlanceProjection, Highlight, Task
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
    db.execute(delete(GlanceProjection).where(GlanceProjection.patient_id == patient_id))
    highlights = db.scalars(
        select(Highlight).where(Highlight.patient_id == patient_id)
    ).all()
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
