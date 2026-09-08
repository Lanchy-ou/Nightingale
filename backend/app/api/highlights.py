"""Glance (precomputed read) + highlight provenance + status endpoints (M3: authorized)."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth, resource_not_found
from ..db import get_db
from ..clinic_scope import load_highlight_with_event, load_patient
from ..highlights import GLANCE_LIMIT, compute_score, status_transitions
from ..models import Artifact, Event, GlanceProjection, Highlight, Patient, Task
from ..glance_projection import rebuild_glance_projections
from ..provenance_binding import resolve_highlight_source
from ..role_context import RoleContext
from ..schemas import (
    ArtifactOut,
    EventBrief,
    GlanceOut,
    HighlightOut,
    ProvenanceOut,
    StatusUpdate,
)

router = APIRouter(prefix="/api", tags=["highlights"])


@router.get("/patients/{patient_id}/glance", response_model=GlanceOut)
def get_glance(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_glance", patient.clinic_id, patient.patient_id)

    rows = db.execute(
        select(GlanceProjection, Highlight)
        .join(Highlight, Highlight.highlight_id == GlanceProjection.highlight_id)
        .where(
            GlanceProjection.patient_id == patient_id,
            GlanceProjection.clinic_id == ctx.clinic_id,
            GlanceProjection.viewer_role == ctx.role,
            GlanceProjection.eligible.is_(True),
        )
        .order_by(
            GlanceProjection.priority_band,
            Highlight.status != "pinned",
            Highlight.review_status != "needs_review",
            GlanceProjection.final_score.desc(),
            GlanceProjection.due_at.is_(None),
            GlanceProjection.due_at,
            Highlight.created_at,
            Highlight.highlight_id,
        )
        .limit(GLANCE_LIMIT)
    ).all()
    dynamic: list[HighlightOut] = []
    for projection, highlight in rows:
        task = db.get(Task, highlight.task_id) if highlight.task_id else None
        task_context = None
        if task is not None:
            task_context = {
                "task_kind": task.task_kind,
                "workflow_id": task.workflow_id,
                "assigned_role": task.assigned_role,
                "status": task.status,
                "attention_class": task.attention_class,
                "verification_outcome": task.verification_outcome,
                "due_at": task.due_at,
                "escalate_at": task.escalate_at,
                "escalated_at": task.escalated_at,
                "creation_method": task.creation_method,
            }
            if task.workflow_id:
                staff_task = db.scalar(
                    select(Task).where(
                        Task.workflow_id == task.workflow_id,
                        Task.task_kind == "patient_report_review",
                    )
                )
                if staff_task is not None:
                    task_context["verification_outcome"] = staff_task.verification_outcome
                    task_context["verification_overdue"] = staff_task.escalated_at is not None
        dynamic.append(
            HighlightOut.model_validate(highlight).model_copy(
                update={
                    "task_context": task_context,
                    "glance_explanation": projection.factor_explanation,
                    "ranking_rule_version": projection.rule_version,
                }
            )
        )
    safety = db.scalars(
        select(Highlight).where(
            Highlight.patient_id == patient_id,
            Highlight.entity_type == "allergy",
            Highlight.status != "rejected",
        )
    ).all()
    safety = [item for item in safety if item.feature_flags.get("clinician_confirmed")]
    return GlanceOut(
        safety_context=[HighlightOut.model_validate(item) for item in safety],
        highlights=dynamic,
    )


@router.get("/highlights/{highlight_id}/provenance", response_model=ProvenanceOut)
def get_provenance(
    highlight_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    scoped = load_highlight_with_event(db, ctx, highlight_id)
    if scoped is None:
        raise resource_not_found()
    hl, event = scoped
    authorize(ctx, "read_provenance", event.clinic_id, event.patient_id)

    source = db.get(Artifact, hl.source_artifact_id)
    if source is None:
        raise resource_not_found()
    resolution = resolve_highlight_source(db, hl)

    summary = None
    if hl.artifact_id != hl.source_artifact_id:
        summary = db.get(Artifact, hl.artifact_id)
        if summary is None:
            raise resource_not_found()

    conflict_artifact = None
    if hl.review_status == "needs_review" and hl.conflict_with_artifact_id:
        conflict_artifact = db.get(Artifact, hl.conflict_with_artifact_id)

    source_out = ArtifactOut.model_validate(source)
    if resolution.content is not None and resolution.bound_version is not None:
        source_out = source_out.model_copy(
            update={
                "content": resolution.content,
                "version": resolution.bound_version,
            }
        )

    return ProvenanceOut(
        highlight_id=hl.highlight_id,
        event=EventBrief.model_validate(event),
        summary_artifact=ArtifactOut.model_validate(summary) if summary else None,
        source_artifact=source_out,
        span=hl.source_span,
        quote=resolution.quote,
        conflict_artifact=ArtifactOut.model_validate(conflict_artifact) if conflict_artifact else None,
        bound_source_version=resolution.bound_version,
        current_source_version=resolution.current_version,
        source_changed=resolution.source_changed,
        binding_status=resolution.status,
    )


@router.post("/highlights/{highlight_id}/status", response_model=HighlightOut)
def update_status(
    highlight_id: str,
    body: StatusUpdate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    scoped = load_highlight_with_event(db, ctx, highlight_id)
    if scoped is None:
        raise resource_not_found()
    hl, event = scoped
    authorize(ctx, "highlight_status", event.clinic_id, event.patient_id)

    new_status = body.status
    old_status = hl.status
    confirms_clinician = (
        ctx.role == "clinician"
        and new_status in ("accepted", "pinned")
        and not hl.feature_flags.get("clinician_confirmed")
    )
    if new_status == old_status and not confirms_clinician:
        return hl  # no-op (idempotent)

    if new_status != old_status and new_status not in status_transitions().get(old_status, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Illegal status transition: {old_status} -> {new_status}",
        )

    now = datetime.now()
    history = list(hl.status_history or [])
    if new_status != old_status:
        history.append({"from": old_status, "to": new_status, "at": now.isoformat()})

    values: dict = {
        "status": new_status,
        "status_history": history,
        "updated_at": now,
    }
    # Clinician authority: only a clinician accept/pin marks clinician_confirmed
    # and triggers a base-score recompute. Staff actions never change this flag.
    flags = hl.feature_flags
    if confirms_clinician:
        flags = {**hl.feature_flags, "clinician_confirmed": True}
        values["feature_flags"] = flags

    # Import the aggregation service only on this write path. Merely importing
    # or executing GET Glance never imports or queries importance feedback.
    from ..importance_learning import compose_score, requested_adaptive_adjustment

    rescored = compose_score(
        base_importance_score=compute_score(flags),
        adaptive_adjustment=requested_adaptive_adjustment(
            hl.adaptive_adjustment, hl.learning_metadata
        ),
        decay_adjustment=hl.decay_adjustment,
        feature_flags=flags,
        status=new_status,
        review_status=hl.review_status,
        learning_metadata=hl.learning_metadata,
    )
    values.update(
        base_importance_score=rescored.base_importance_score,
        adaptive_adjustment=rescored.adaptive_adjustment,
        decay_adjustment=rescored.decay_adjustment,
        importance_score=rescored.importance_score,
        learning_metadata=rescored.learning_metadata,
    )

    # Protect both status changes and same-status clinician confirmations.
    result = db.execute(
        update(Highlight)
        .where(
            Highlight.highlight_id == highlight_id,
            Highlight.status == old_status,
            Highlight.updated_at == hl.updated_at,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        clinic_id = event.clinic_id
        patient_id = event.patient_id
        event_id = event.event_id
        db.rollback()
        current_scoped = load_highlight_with_event(db, ctx, highlight_id)
        current = current_scoped[0] if current_scoped is not None else None
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="conflict",
            target_type="highlight",
            target_id=highlight_id,
            clinic_id=clinic_id,
            patient_id=patient_id,
            event_id=event_id,
        )
        db.commit()
        return JSONResponse(
            status_code=409,
            content={
                "error": {
                    "code": "conflict",
                    "message": "Stale write: highlight status changed concurrently",
                    "current_status": current.status if current else None,
                }
            },
        )

    # F_A1 semantics: status controls affect only this Highlight. They no
    # longer append positive/negative generalization feedback.
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="highlight_status",
        target_type="highlight",
        target_id=highlight_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        details={"from_status": old_status, "to_status": new_status,
                 "clinician_confirmation_added": confirms_clinician},
    )
    db.commit()
    db.refresh(hl)
    rebuild_glance_projections(db, hl.patient_id)
    db.commit()
    db.refresh(hl)
    return hl
