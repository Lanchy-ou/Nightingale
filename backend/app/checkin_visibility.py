"""Lightweight Check-in Event visibility guard for zero-LLM read paths."""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import PatientCheckInSession

CLINICALLY_VISIBLE_CHECKIN_STATUSES = {"submitted", "safety_escalated"}


def checkin_event_is_clinically_visible(db: Session, event_id: str) -> bool:
    session = db.scalar(
        select(PatientCheckInSession).where(PatientCheckInSession.event_id == event_id)
    )
    return session is None or session.status in CLINICALLY_VISIBLE_CHECKIN_STATUSES


def require_checkin_event_visible(db: Session, event_id: str) -> None:
    if not checkin_event_is_clinically_visible(db, event_id):
        raise HTTPException(status_code=404, detail="Resource not found")
