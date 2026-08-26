"""Read-only event artifact endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Artifact, Event
from ..schemas import ArtifactOut

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events/{event_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(event_id: str, db: Session = Depends(get_db)):
    event = db.get(Event, event_id)
    if event is None:
        raise HTTPException(status_code=404, detail=f"Event {event_id} not found")

    return db.scalars(
        select(Artifact).where(Artifact.event_id == event_id).order_by(Artifact.created_at)
    ).all()
