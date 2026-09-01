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
from ..highlights import GLANCE_LIMIT, compute_score, status_transitions
from ..models import Artifact, Event, Highlight, Patient
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
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_glance", patient.clinic_id, patient.patient_id)

    highlights = db.scalars(
        select(Highlight).where(
            Highlight.patient_id == patient_id,
            Highlight.status != "rejected",
        )
    ).all()
    # Deterministic safety ordering (H1): pinned first, then unresolved clinical
    # conflicts, score desc, record time, and a stable final tiebreak.
    highlights = sorted(
        highlights,
        key=lambda h: (
            h.status != "pinned",
            h.review_status != "needs_review",
            -h.importance_score,
            h.created_at,
            h.highlight_id,
        ),
    )
    return GlanceOut(
        highlights=[HighlightOut.model_validate(h) for h in highlights[:GLANCE_LIMIT]]
    )


@router.get("/highlights/{highlight_id}/provenance", response_model=ProvenanceOut)
def get_provenance(
    highlight_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    hl = db.get(Highlight, highlight_id)
    if hl is None:
        raise resource_not_found()

    event = db.get(Event, hl.event_id)
    if event is None:
        raise resource_not_found()
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
    hl = db.get(Highlight, highlight_id)
    if hl is None:
        raise resource_not_found()

    event = db.get(Event, hl.event_id)
    if event is None:
        raise resource_not_found()
    authorize(ctx, "highlight_status", event.clinic_id, event.patient_id)

    new_status = body.status
    old_status = hl.status
    if new_status == old_status:
        return hl  # no-op (idempotent)

    if new_status not in status_transitions().get(old_status, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Illegal status transition: {old_status} -> {new_status}",
        )

    now = datetime.now()
    history = list(hl.status_history or [])
    history.append({"from": old_status, "to": new_status, "at": now.isoformat()})

    values: dict = {
        "status": new_status,
        "status_history": history,
        "updated_at": now,
    }
    # Clinician authority: only a clinician accept/pin marks clinician_confirmed
    # and triggers a base-score recompute. Staff actions never change this flag.
    flags = hl.feature_flags
    if ctx.role == "clinician" and new_status in ("accepted", "pinned"):
        if not hl.feature_flags.get("clinician_confirmed"):
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

    # Deterministic optimistic lock (H3): the current status is the version.
    # A concurrent writer that already moved the status matches 0 rows and is
    # rejected with 409 instead of silently overwriting history/score.
    result = db.execute(
        update(Highlight)
        .where(
            Highlight.highlight_id == highlight_id,
            Highlight.status == old_status,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        clinic_id = event.clinic_id
        patient_id = event.patient_id
        event_id = event.event_id
        db.rollback()
        current = db.get(Highlight, highlight_id)
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

    # Only the winning CAS reaches this point. No-op and conflict paths return
    # earlier and therefore cannot append learning feedback.
    from ..importance_learning import record_feedback

    record_feedback(
        db,
        highlight=hl,
        event=event,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        status=new_status,
        created_at=now,
    )
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
    )
    db.commit()
    db.refresh(hl)
    return hl
