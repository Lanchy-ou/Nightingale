"""E1 clinic-scoped identity, account, session and access-audit oversight."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session, aliased

from ..audit import add_audit
from ..authz import authorize, require_auth, resource_not_found
from ..db import get_db
from ..clinic_scope import load_clinic_user
from ..models import AuditLog, AuthSession, User, UserCredential
from ..role_context import RoleContext
from ..schemas import (
    AdminAccessAuditOut,
    AdminAccountStatusUpdate,
    AdminSessionRevokeOut,
    AdminSessionRevokeRequest,
    AdminUserOut,
)


router = APIRouter(prefix="/api/admin", tags=["admin"])

ACCESS_AUDIT_ACTIONS = {
    "invite_created",
    "register",
    "login_success",
    "login_failure",
    "logout",
    "session_revoked",
    "account_disabled",
    "account_reactivated",
    "system_ai_mode_changed",
    "system_key_rotated",
    "system_key_removed",
    "system_voice_changed",
    "voice_model_started",
    "voice_model_completed",
    "voice_model_failed",
}


def _target_user(db: Session, ctx: RoleContext, user_id: str, action: str) -> User:
    user = load_clinic_user(db, ctx, user_id)
    if user is None:
        raise resource_not_found()
    authorize(ctx, action, user.clinic_id, user.patient_id)
    return user


def _active_sessions(db: Session, user_id: str, now: datetime) -> list[AuthSession]:
    return list(
        db.scalars(
            select(AuthSession).where(
                AuthSession.user_id == user_id,
                AuthSession.revoked_at.is_(None),
                AuthSession.expires_at > now,
            )
        ).all()
    )


def _user_out(db: Session, user: User, now: datetime) -> AdminUserOut:
    credential = db.get(UserCredential, user.user_id)
    sessions = _active_sessions(db, user.user_id, now)
    return AdminUserOut(
        user_id=user.user_id,
        display_name=user.name,
        email=credential.email_normalized if credential else None,
        role=user.role,
        professional_title=user.professional_title,
        patient_id=user.patient_id,
        account_status=(
            "active" if credential is not None and credential.disabled_at is None else "disabled"
        ),
        disabled_at=credential.disabled_at if credential else None,
        active_session_count=len(sessions),
        last_seen_at=max((row.last_seen_at for row in sessions), default=None),
    )


@router.get("/users", response_model=list[AdminUserOut])
def list_users(
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_list_users", ctx.clinic_id, None)
    users = db.scalars(
        select(User)
        .where(User.clinic_id == ctx.clinic_id)
        .order_by(User.role, User.name, User.user_id)
    ).all()
    now = datetime.now()
    return [_user_out(db, user, now) for user in users]


@router.patch("/users/{user_id}/status", response_model=AdminUserOut)
def update_account_status(
    user_id: str,
    body: AdminAccountStatusUpdate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    user = _target_user(db, ctx, user_id, "admin_update_account")
    credential = db.get(UserCredential, user.user_id)
    if credential is None:
        raise resource_not_found()
    current = "disabled" if credential.disabled_at is not None else "active"
    if current != body.expected_status:
        raise HTTPException(status_code=409, detail="Account status conflict")
    if body.status == "disabled" and user.user_id == ctx.user_id:
        raise HTTPException(status_code=403, detail="Cannot disable current admin")

    now = datetime.now()
    expected_disabled_at = (
        UserCredential.disabled_at.is_(None)
        if body.expected_status == "active"
        else UserCredential.disabled_at.is_not(None)
    )
    update_conditions = [
        UserCredential.user_id == user.user_id,
        expected_disabled_at,
    ]
    if body.status == "disabled" and user.role == "admin":
        other_user = aliased(User)
        other_credential = aliased(UserCredential)
        update_conditions.append(
            exists(
                select(1)
                .select_from(other_user)
                .join(
                    other_credential,
                    other_credential.user_id == other_user.user_id,
                )
                .where(
                    other_user.clinic_id == ctx.clinic_id,
                    other_user.role == "admin",
                    other_user.user_id != user.user_id,
                    other_credential.disabled_at.is_(None),
                )
            )
        )
    result = db.execute(
        update(UserCredential)
        .where(*update_conditions)
        .values(disabled_at=now if body.status == "disabled" else None)
    )
    if result.rowcount != 1:
        db.rollback()
        if body.status == "disabled" and user.role == "admin":
            raise HTTPException(status_code=409, detail="Cannot disable last active admin")
        raise HTTPException(status_code=409, detail="Account status conflict")

    if body.status == "disabled":
        sessions = _active_sessions(db, user.user_id, now)
        if sessions:
            session_ids = [row.session_id for row in sessions]
            revoked = db.execute(
                update(AuthSession)
                .where(
                    AuthSession.session_id.in_(session_ids),
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            if revoked.rowcount != len(session_ids):
                db.rollback()
                raise HTTPException(status_code=409, detail="Session state conflict")
            for session_id in session_ids:
                add_audit(
                    db,
                    actor_id=ctx.user_id,
                    actor_role=ctx.role,
                    action="session_revoked",
                    target_type="session",
                    target_id=session_id,
                    clinic_id=user.clinic_id,
                    patient_id=user.patient_id,
                    details={"reason": "account_disabled", "user_id": user.user_id},
                )

    action = "account_disabled" if body.status == "disabled" else "account_reactivated"
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action=action,
        target_type="user",
        target_id=user.user_id,
        clinic_id=user.clinic_id,
        patient_id=user.patient_id,
        details={"from_status": body.expected_status, "to_status": body.status},
    )
    db.commit()
    db.expire_all()
    return _user_out(db, user, datetime.now())


@router.post(
    "/users/{user_id}/revoke-sessions",
    response_model=AdminSessionRevokeOut,
)
def revoke_user_sessions(
    user_id: str,
    body: AdminSessionRevokeRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    user = _target_user(db, ctx, user_id, "admin_revoke_sessions")
    now = datetime.now()
    sessions = _active_sessions(db, user.user_id, now)
    if len(sessions) != body.expected_active_session_count:
        raise HTTPException(status_code=409, detail="Active session count conflict")
    if not sessions:
        return AdminSessionRevokeOut(user_id=user.user_id, revoked_count=0)

    session_ids = [row.session_id for row in sessions]
    result = db.execute(
        update(AuthSession)
        .where(
            AuthSession.session_id.in_(session_ids),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > now,
        )
        .values(revoked_at=now)
    )
    if result.rowcount != len(session_ids):
        db.rollback()
        raise HTTPException(status_code=409, detail="Session state conflict")
    for session_id in session_ids:
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="session_revoked",
            target_type="session",
            target_id=session_id,
            clinic_id=user.clinic_id,
            patient_id=user.patient_id,
            details={"reason": "admin_revoke", "user_id": user.user_id},
        )
    db.commit()
    return AdminSessionRevokeOut(user_id=user.user_id, revoked_count=len(session_ids))


@router.get("/access-audit", response_model=list[AdminAccessAuditOut])
def list_access_audit(
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "admin_read_access_audit", ctx.clinic_id, None)
    rows = db.scalars(
        select(AuditLog)
        .where(
            AuditLog.clinic_id == ctx.clinic_id,
            AuditLog.action.in_(ACCESS_AUDIT_ACTIONS),
        )
        .order_by(AuditLog.created_at.desc(), AuditLog.audit_id)
    ).all()
    return [
        AdminAccessAuditOut(
            audit_id=row.audit_id,
            actor_id=row.actor_id,
            actor_role=row.actor_role,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            details=row.details,
            created_at=row.created_at,
        )
        for row in rows
    ]
