"""AuditLog writer (metadata only — never copies raw clinical content)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from .ids import new_id
from .models import AuditLog


def add_audit(
    db: Session,
    *,
    actor_id: str | None,
    actor_role: str | None,
    action: str,
    target_type: str,
    target_id: str,
    clinic_id: str | None,
    patient_id: str | None,
    event_id: str | None = None,
    from_version: int | None = None,
    to_version: int | None = None,
    details: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            audit_id=new_id("aud"),
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_type=target_type,
            target_id=target_id,
            from_version=from_version,
            to_version=to_version,
            clinic_id=clinic_id,
            patient_id=patient_id,
            event_id=event_id,
            details=details,
            created_at=datetime.now(),
        )
    )
