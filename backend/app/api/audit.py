"""Audit read endpoint (metadata only)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authz import authorize, require_auth, resource_not_found
from ..checkin_visibility import require_checkin_event_visible
from ..db import get_db
from ..models import AuditLog, Event
from ..role_context import RoleContext
from ..schemas import AuditLogOut

router = APIRouter(prefix="/api", tags=["audit"])


@router.get("/events/{event_id}/audit", response_model=list[AuditLogOut])
def list_audit(
    event_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = db.get(Event, event_id)
    if event is None:
        raise resource_not_found()
    authorize(ctx, "read_audit", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event_id)

    return db.scalars(
        select(AuditLog).where(AuditLog.event_id == event_id).order_by(AuditLog.created_at)
    ).all()
