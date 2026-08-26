"""Glance (precomputed read) + highlight provenance + status endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..highlights import GLANCE_LIMIT, extract_text, status_transitions
from ..models import Artifact, Event, Highlight
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
def get_glance(patient_id: str, db: Session = Depends(get_db)):
    # Read-only warm path: precomputed scores, zero computation here.
    highlights = db.scalars(
        select(Highlight).where(
            Highlight.patient_id == patient_id,
            Highlight.status != "rejected",
        )
    ).all()
    # pinned first, then importance_score desc, then created_at asc (deterministic).
    highlights = sorted(
        highlights,
        key=lambda h: (h.status != "pinned", -h.importance_score, h.created_at),
    )
    return GlanceOut(
        highlights=[HighlightOut.model_validate(h) for h in highlights[:GLANCE_LIMIT]]
    )


@router.get("/highlights/{highlight_id}/provenance", response_model=ProvenanceOut)
def get_provenance(highlight_id: str, db: Session = Depends(get_db)):
    hl = db.get(Highlight, highlight_id)
    if hl is None:
        raise HTTPException(status_code=404, detail=f"Highlight {highlight_id} not found")

    event = db.get(Event, hl.event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {hl.event_id} not found")

    source = db.get(Artifact, hl.source_artifact_id)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source artifact {hl.source_artifact_id} not found")

    summary = None
    if hl.artifact_id != hl.source_artifact_id:
        summary = db.get(Artifact, hl.artifact_id)
        if summary is None:
            raise HTTPException(status_code=404, detail=f"Artifact {hl.artifact_id} not found")

    return ProvenanceOut(
        highlight_id=hl.highlight_id,
        event=EventBrief.model_validate(event),
        summary_artifact=ArtifactOut.model_validate(summary) if summary else None,
        source_artifact=ArtifactOut.model_validate(source),
        span=hl.source_span,
        quote=extract_text(source.content, hl.source_span),
    )


@router.post("/highlights/{highlight_id}/status", response_model=HighlightOut)
def update_status(highlight_id: str, body: StatusUpdate, db: Session = Depends(get_db)):
    hl = db.get(Highlight, highlight_id)
    if hl is None:
        raise HTTPException(status_code=404, detail=f"Highlight {highlight_id} not found")

    new_status = body.status
    if new_status == hl.status:
        return hl  # no-op, keep history unchanged

    if new_status not in status_transitions().get(hl.status, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Illegal status transition: {hl.status} -> {new_status}",
        )

    history = list(hl.status_history or [])
    history.append({"from": hl.status, "to": new_status, "at": datetime.now().isoformat()})
    hl.status_history = history
    hl.status = new_status
    hl.updated_at = datetime.now()
    db.commit()
    db.refresh(hl)
    return hl
