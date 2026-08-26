"""Server-side role context (M3: DB is the single authority for identity/role).

- `X-User-Id` must resolve to a real `User`; role, clinic_id and patient_id all
  come from the DB record — NEVER from the client.
- `X-Role` is only a demo-consistency assertion: if present and matching it is
  accepted; if present but MISMATCHING the DB role the request is rejected; if
  absent it is fine. It can never elevate privileges.
- No/unknown user => unauthenticated context (endpoints must call require_auth
  to enforce 401).
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User


@dataclass
class RoleContext:
    user_id: str | None
    role: str | None
    clinic_id: str | None
    patient_id: str | None
    authenticated: bool


def resolve_role_context(
    user_id: str | None, role_header: str | None, db: Session
) -> RoleContext:
    user = db.get(User, user_id) if user_id else None
    if user is None:
        return RoleContext(None, None, None, None, False)

    # DB is authoritative; a mismatched X-Role is a hard reject, not an override.
    if role_header is not None and role_header != user.role:
        raise HTTPException(
            status_code=403,
            detail="X-Role does not match the authenticated user's role",
        )

    return RoleContext(
        user_id=user.user_id,
        role=user.role,
        clinic_id=user.clinic_id,
        patient_id=user.patient_id,
        authenticated=True,
    )


def get_role_context(
    request: Request, db: Session = Depends(get_db)
) -> RoleContext:
    ctx = resolve_role_context(
        request.headers.get("X-User-Id"),
        request.headers.get("X-Role"),
        db,
    )
    request.state.role_context = ctx
    return ctx
