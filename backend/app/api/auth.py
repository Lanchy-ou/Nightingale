"""D1 identity, invite, login and session endpoints.

Contract highlights (Task_Card/D1_Identity_Access_Task_Card.md):
- clinician/staff/admin can only register through a clinic-scoped invite;
- patient invites are pre-bound to clinic_id + patient_id and can never create
  a second Patient record (registration only links a new User to the existing
  record);
- registrants can never override the invite's role, clinic or patient binding;
- only token hashes are persisted; the raw invite link is returned exactly once;
- login/register return generic errors (no account-existence leakage);
- invite consumption + User + UserCredential commit in ONE transaction;
- logout atomically revokes the current session;
- AuditLog records invite_created/register/login_success/login_failure/logout/
  session_revoked metadata only — never passwords, tokens or failed-login emails.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_security import (
    DUMMY_PASSWORD_HASH,
    SESSION_COOKIE_NAME,
    cleared_session_cookie,
    hash_password,
    hash_token,
    invite_ttl,
    is_plausible_email,
    new_invite_token,
    new_session_token,
    normalize_email,
    session_cookie_value,
    session_ttl,
    verify_password,
)
from ..authz import authorize, require_auth, resource_not_found
from ..db import get_db
from ..ids import new_id
from ..models import (
    AuthSession,
    Clinic,
    Invite,
    Patient,
    User,
    UserCredential,
)
from ..role_context import RoleContext
from ..schemas import (
    CurrentIdentityOut,
    InviteCreate,
    InviteCreatedOut,
    InviteOut,
    InvitePreviewRequest,
    InvitePreviewOut,
    LoginRequest,
    LogoutOut,
    RegisterOut,
    RegisterRequest,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

INVITE_LINK_PATH = "/register"


def _identity_out(user: User, clinic: Clinic | None) -> CurrentIdentityOut:
    return CurrentIdentityOut(
        user_id=user.user_id,
        role=user.role,
        clinic_id=user.clinic_id,
        patient_id=user.patient_id,
        display_name=user.name,
        professional_title=user.professional_title,
        clinic_name=clinic.name if clinic else None,
        authenticated=True,
    )


def _mask_email(email: str) -> str:
    local, sep, domain = email.partition("@")
    if not sep or len(local) < 1:
        return "***"
    return f"{local[0]}{'*' * 3}@{domain}"


def _invite_status(invite: Invite, now: datetime) -> str:
    if invite.used_at is not None:
        return "used"
    if invite.expires_at <= now:
        return "expired"
    return "valid"


def _find_invite_by_token(db: Session, token: str) -> Invite | None:
    return db.scalar(select(Invite).where(Invite.token_hash == hash_token(token)))


@router.post("/invites", response_model=InviteCreatedOut)
def create_invite(
    body: InviteCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Admin-only, clinic-scoped invite creation. The clinic always comes from
    the inviter's own session/DB identity — it can never be specified."""
    authorize(ctx, "create_invite", ctx.clinic_id, None)

    email = body.email.strip()
    normalized = normalize_email(email)
    if not is_plausible_email(normalized):
        raise HTTPException(status_code=422, detail="Invalid email address")

    patient_id: str | None = None
    if body.role == "patient":
        if not body.patient_id:
            raise HTTPException(
                status_code=422, detail="patient invite requires patient_id"
            )
        patient = db.get(Patient, body.patient_id)
        # A patient outside the inviter's clinic looks exactly like an absent
        # patient: uniform 404, no cross-clinic existence leak.
        if patient is None or patient.clinic_id != ctx.clinic_id:
            raise resource_not_found()
        patient_id = patient.patient_id
    elif body.patient_id:
        raise HTTPException(
            status_code=422, detail="only patient invites may bind a patient"
        )

    now = datetime.now()
    pending = db.scalar(
        select(Invite).where(
            Invite.clinic_id == ctx.clinic_id,
            Invite.email_normalized == normalized,
            Invite.used_at.is_(None),
            Invite.expires_at > now,
        )
    )
    if pending is not None:
        raise HTTPException(
            status_code=409, detail="A pending invite already exists for this email"
        )

    token = new_invite_token()
    invite = Invite(
        invite_id=new_id("inv"),
        clinic_id=ctx.clinic_id,
        email=email,
        email_normalized=normalized,
        role=body.role,
        patient_id=patient_id,
        token_hash=hash_token(token),
        expires_at=now + invite_ttl(),
        used_at=None,
        created_by=ctx.user_id,
        created_at=now,
    )
    db.add(invite)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="invite_created",
        target_type="invite",
        target_id=invite.invite_id,
        clinic_id=ctx.clinic_id,
        patient_id=patient_id,
    )
    db.commit()

    return InviteCreatedOut(
        invite_id=invite.invite_id,
        email=invite.email,
        role=invite.role,
        patient_id=invite.patient_id,
        expires_at=invite.expires_at,
        # Raw token appears only here, one time. No email is sent in the demo.
        invite_link=f"{INVITE_LINK_PATH}?token={token}",
    )


@router.get("/invites", response_model=list[InviteOut])
def list_invites(
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Clinic-scoped invite administration list (no tokens, no hashes)."""
    authorize(ctx, "list_invites", ctx.clinic_id, None)
    now = datetime.now()
    invites = db.scalars(
        select(Invite)
        .where(Invite.clinic_id == ctx.clinic_id)
        .order_by(Invite.created_at.desc(), Invite.invite_id)
    ).all()
    # Admin list uses "pending" for a still-usable invite; the preview
    # endpoint reports the same state as "valid".
    list_status = {"valid": "pending", "used": "used", "expired": "expired"}
    return [
        InviteOut(
            invite_id=i.invite_id,
            email=i.email,
            role=i.role,
            patient_id=i.patient_id,
            created_by=i.created_by,
            created_at=i.created_at,
            expires_at=i.expires_at,
            used_at=i.used_at,
            status=list_status[_invite_status(i, now)],
        )
        for i in invites
    ]


@router.post("/invites/preview", response_model=InvitePreviewOut)
def preview_invite(body: InvitePreviewRequest, db: Session = Depends(get_db)):
    """Minimal invite context for the accept-invite page.

    Unknown/tampered tokens receive the uniform 404. Distinct used/expired
    states are returned only for a token the caller actually holds (the token
    is a 256-bit bearer secret, so this is not an enumeration channel).
    """
    invite = _find_invite_by_token(db, body.token)
    if invite is None:
        raise resource_not_found()

    clinic = db.get(Clinic, invite.clinic_id)
    patient_name = None
    if invite.patient_id is not None:
        patient = db.get(Patient, invite.patient_id)
        if patient is not None:
            patient_name = patient.name

    return InvitePreviewOut(
        status=_invite_status(invite, datetime.now()),
        email_masked=_mask_email(invite.email),
        role=invite.role,
        clinic_name=clinic.name if clinic else "",
        patient_name=patient_name,
        expires_at=invite.expires_at,
    )


@router.post("/register", response_model=RegisterOut, status_code=201)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    """Consume an invite and create User + UserCredential in ONE transaction.

    The invite's role, clinic and patient binding are authoritative; the
    request cannot override any of them. A patient invite links a new User to
    the EXISTING Patient record — it never creates a second Patient row.
    """
    invite = _find_invite_by_token(db, body.token)
    if invite is None:
        # Uniform 404 for unknown/tampered tokens (no invite enumeration).
        raise resource_not_found()
    if invite.used_at is not None:
        raise HTTPException(status_code=409, detail="This invite has already been used")
    now = datetime.now()
    if invite.expires_at <= now:
        raise HTTPException(status_code=410, detail="This invite has expired")

    normalized = invite.email_normalized
    if db.scalar(
        select(UserCredential).where(UserCredential.email_normalized == normalized)
    ) is not None:
        # Generic: never reveals whether the email is already registered.
        raise HTTPException(
            status_code=409, detail="This invite can no longer be used"
        )

    user_id = new_id("usr")
    if invite.role == "patient":
        patient = db.get(Patient, invite.patient_id)
        if patient is None or patient.clinic_id != invite.clinic_id:
            raise resource_not_found()
        # Invite binding wins: the bound Patient record supplies the name.
        name = patient.name
    else:
        name = (body.name or "").strip()
        if not name:
            raise HTTPException(status_code=422, detail="name is required")

    user = User(
        user_id=user_id,
        clinic_id=invite.clinic_id,
        name=name,
        role=invite.role,
        patient_id=invite.patient_id,
    )
    password_hash = hash_password(body.password)
    registered_at = datetime.now()
    consumed = db.execute(
        update(Invite)
        .where(
            Invite.invite_id == invite.invite_id,
            Invite.used_at.is_(None),
            Invite.expires_at > registered_at,
        )
        .values(used_at=registered_at)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="This invite can no longer be used"
        )

    credential = UserCredential(
        user_id=user_id,
        email_normalized=normalized,
        password_hash=password_hash,
        created_at=registered_at,
        password_changed_at=registered_at,
        disabled_at=None,
    )
    db.add(user)
    db.add(credential)
    add_audit(
        db,
        actor_id=user_id,
        actor_role=invite.role,
        action="register",
        target_type="user",
        target_id=user_id,
        clinic_id=invite.clinic_id,
        patient_id=invite.patient_id,
    )
    # Single commit: invite consumption, User and UserCredential are atomic.
    db.commit()

    return RegisterOut(
        user_id=user_id,
        email=invite.email,
        role=invite.role,
        clinic_id=invite.clinic_id,
    )


@router.post("/login", response_model=CurrentIdentityOut)
def login(body: LoginRequest, db: Session = Depends(get_db), response: Response = None):
    """Email + password login issuing an HttpOnly session cookie.

    Unknown email, wrong password and disabled account all return the same
    401 body. Only a SHA-256 hash of the session token is persisted.
    """
    normalized = normalize_email(body.email)
    credential = db.scalar(
        select(UserCredential).where(UserCredential.email_normalized == normalized)
    )
    user = db.get(User, credential.user_id) if credential is not None else None

    password_hash = (
        credential.password_hash
        if credential is not None and credential.disabled_at is None
        else DUMMY_PASSWORD_HASH
    )
    password_ok = verify_password(body.password, password_hash)
    ok = credential is not None and credential.disabled_at is None and password_ok
    if not ok or user is None:
        # Metadata-only failure audit; the email itself is never logged.
        add_audit(
            db,
            actor_id=user.user_id if user is not None else None,
            actor_role=user.role if user is not None else None,
            action="login_failure",
            target_type="user",
            target_id=user.user_id if user is not None else "unknown",
            clinic_id=user.clinic_id if user is not None else None,
            patient_id=user.patient_id if user is not None else None,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = new_session_token()
    now = datetime.now()
    session = AuthSession(
        session_id=new_id("ses"),
        user_id=user.user_id,
        token_hash=hash_token(token),
        created_at=now,
        expires_at=now + session_ttl(),
        revoked_at=None,
        last_seen_at=now,
    )
    db.add(session)
    add_audit(
        db,
        actor_id=user.user_id,
        actor_role=user.role,
        action="login_success",
        target_type="session",
        target_id=session.session_id,
        clinic_id=user.clinic_id,
        patient_id=user.patient_id,
    )
    db.commit()

    response.headers.append("set-cookie", session_cookie_value(token))
    clinic = db.get(Clinic, user.clinic_id)
    return _identity_out(user, clinic)


@router.post("/logout", response_model=LogoutOut)
def logout(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Atomically revoke the current session and clear the cookie.

    A conditional UPDATE guarantees exactly one revoke even under concurrent
    requests; a second logout on an already-revoked session is a no-op.
    """
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        row = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == hash_token(token))
        )
        if row is not None and row.revoked_at is None:
            now = datetime.now()
            result = db.execute(
                update(AuthSession)
                .where(
                    AuthSession.session_id == row.session_id,
                    AuthSession.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            if result.rowcount == 1:
                add_audit(
                    db,
                    actor_id=ctx.user_id,
                    actor_role=ctx.role,
                    action="logout",
                    target_type="session",
                    target_id=row.session_id,
                    clinic_id=ctx.clinic_id,
                    patient_id=ctx.patient_id,
                )
                add_audit(
                    db,
                    actor_id=ctx.user_id,
                    actor_role=ctx.role,
                    action="session_revoked",
                    target_type="session",
                    target_id=row.session_id,
                    clinic_id=ctx.clinic_id,
                    patient_id=ctx.patient_id,
                )
                db.commit()
            else:
                db.rollback()
    response.headers.append("set-cookie", cleared_session_cookie())
    return LogoutOut(status="logged_out")


@router.get("/session", response_model=CurrentIdentityOut)
def current_session(
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Current session identity (refresh/restore path). 401 without a session."""
    user = db.get(User, ctx.user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    clinic = db.get(Clinic, ctx.clinic_id)
    return _identity_out(user, clinic)
