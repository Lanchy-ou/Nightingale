"""Server-side role context (M3 + D1: DB/session is the single authority for identity/role).

D1 resolution order (per Task_Card/D1_Identity_Access_Task_Card.md):
  1. A valid server-side session (HttpOnly cookie) resolves the user; role,
     clinic_id and patient_id all come from the DB record — NEVER from the client.
     Disabled credentials, expired and revoked sessions uniformly resolve to
     unauthenticated (401 on protected resources).
  2. Legacy demo headers (`X-User-Id` / `X-Role`) are accepted ONLY when the
     explicit environment flag NANTINGALE_DEMO_AUTH=true is set (default off).
     They are a test/development aid, not a product identity path. `X-Role` is
     a demo-consistency assertion: mismatching the DB role is a hard reject; it
     can never elevate privileges.
  3. Otherwise the context is unauthenticated; endpoints must call require_auth
     to enforce 401.

The DB User remains authoritative on every request, so a role change in the DB
takes effect immediately and stale headers/sessions can never escalate.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .auth_security import SESSION_COOKIE_NAME, hash_token, last_seen_refresh_seconds
from .db import get_db
from .models import AuthSession, User, UserCredential


@dataclass
class RoleContext:
    user_id: str | None
    role: str | None
    clinic_id: str | None
    patient_id: str | None
    authenticated: bool


def demo_auth_enabled() -> bool:
    return os.environ.get("NANTINGALE_DEMO_AUTH", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def resolve_role_context(
    user_id: str | None, role_header: str | None, db: Session
) -> RoleContext:
    """Legacy demo-header path. Only reachable when demo auth is explicitly enabled."""
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


def _session_user(request: Request, db: Session) -> User | None:
    """Resolve the session cookie to a DB User, or None for any invalid state.

    Invalid = missing/unknown token, revoked, expired, disabled credential or
    missing user/credential. All of these are indistinguishable to callers:
    they simply become an unauthenticated context.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None
    row = db.scalar(
        select(AuthSession).where(AuthSession.token_hash == hash_token(token))
    )
    now = datetime.now()
    if row is None or row.revoked_at is not None or row.expires_at <= now:
        return None
    credential = db.get(UserCredential, row.user_id)
    # Fail closed: a session without a credential (or a disabled account) is dead.
    if credential is None or credential.disabled_at is not None:
        return None
    user = db.get(User, row.user_id)
    if user is None:
        return None
    # Throttled last_seen refresh (metadata only, avoids a write per request).
    refresh = last_seen_refresh_seconds()
    if (now - row.last_seen_at).total_seconds() > refresh:
        row.last_seen_at = now
        db.add(row)
        db.commit()
    return user


def get_role_context(
    request: Request, db: Session = Depends(get_db)
) -> RoleContext:
    user = _session_user(request, db)
    if user is not None:
        ctx = RoleContext(
            user_id=user.user_id,
            role=user.role,
            clinic_id=user.clinic_id,
            patient_id=user.patient_id,
            authenticated=True,
        )
    elif demo_auth_enabled():
        ctx = resolve_role_context(
            request.headers.get("X-User-Id"),
            request.headers.get("X-Role"),
            db,
        )
    else:
        ctx = RoleContext(None, None, None, None, False)
    request.state.role_context = ctx
    return ctx
