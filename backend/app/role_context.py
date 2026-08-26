"""Server-side role context parsing.

M1 scope: parse X-User-Id / X-Role headers and inject a RoleContext into
request.state. There is NO auth and NO enforcement yet (Phase 3). The resolved
context must be testable, so /api/me echoes it back.

Semantics:
- user_id comes from the X-User-Id header.
- role comes from the X-Role header (takes precedence); if absent, falls back
  to the DB role of the resolved user.
- clinic_id is resolved from the DB user (basis for clinic scoping in Phase 3).
"""
from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .db import get_db
from .models import User


@dataclass
class RoleContext:
    user_id: str | None
    role: str | None
    clinic_id: str | None


def resolve_role_context(
    user_id: str | None, role: str | None, db: Session
) -> RoleContext:
    clinic_id: str | None = None
    user = db.get(User, user_id) if user_id else None
    if user is not None:
        clinic_id = user.clinic_id
        if role is None:
            role = user.role
    return RoleContext(user_id=user_id, role=role, clinic_id=clinic_id)


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
