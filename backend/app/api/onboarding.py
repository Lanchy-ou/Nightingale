"""Token-gated creation of one Clinic and its first administrator."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..auth_security import hash_password, hash_token, is_plausible_email, normalize_email
from ..authz import resource_not_found
from ..db import get_db
from ..ids import new_id
from ..models import (
    Clinic,
    ClinicOnboardingToken,
    ClinicSettings,
    User,
    UserCredential,
)
from ..schemas import (
    OnboardingCompleteOut,
    OnboardingCompleteRequest,
    OnboardingPreviewOut,
    OnboardingPreviewRequest,
)

router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _find(db: Session, token: str) -> ClinicOnboardingToken | None:
    return db.scalar(
        select(ClinicOnboardingToken).where(
            ClinicOnboardingToken.token_hash == hash_token(token)
        )
    )


def _status(row: ClinicOnboardingToken, now: datetime) -> str:
    if row.used_at is not None:
        return "used"
    if row.expires_at <= now:
        return "expired"
    return "valid"


@router.post("/preview", response_model=OnboardingPreviewOut)
def preview_onboarding(
    body: OnboardingPreviewRequest, db: Session = Depends(get_db)
):
    row = _find(db, body.token)
    if row is None:
        raise resource_not_found()
    return OnboardingPreviewOut(status=_status(row, datetime.now()), expires_at=row.expires_at)


@router.post("/complete", response_model=OnboardingCompleteOut, status_code=201)
def complete_onboarding(
    body: OnboardingCompleteRequest, db: Session = Depends(get_db)
):
    clinic_name = body.clinic_name.strip()
    admin_name = body.admin_name.strip()
    email = body.email.strip()
    normalized = normalize_email(email)
    if not clinic_name or not admin_name:
        raise HTTPException(status_code=422, detail="Clinic and administrator names are required")
    if not is_plausible_email(normalized):
        raise HTTPException(status_code=422, detail="Invalid email address")

    row = _find(db, body.token)
    if row is None:
        raise resource_not_found()
    if row.used_at is not None:
        raise HTTPException(status_code=409, detail="This setup link has already been used")
    now = datetime.now()
    if row.expires_at <= now:
        raise HTTPException(status_code=410, detail="This setup link has expired")
    if db.scalar(
        select(UserCredential.user_id).where(
            UserCredential.email_normalized == normalized
        )
    ) is not None:
        raise HTTPException(status_code=409, detail="This setup link can no longer be used")

    consumed = db.execute(
        update(ClinicOnboardingToken)
        .where(
            ClinicOnboardingToken.onboarding_token_id == row.onboarding_token_id,
            ClinicOnboardingToken.used_at.is_(None),
            ClinicOnboardingToken.expires_at > now,
        )
        .values(used_at=now)
    )
    if consumed.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="This setup link can no longer be used")

    clinic_id = new_id("cln")
    user_id = new_id("usr")
    try:
        db.add(Clinic(clinic_id=clinic_id, name=clinic_name))
        db.add(
            User(
                user_id=user_id,
                clinic_id=clinic_id,
                name=admin_name,
                role="admin",
                professional_title=None,
                patient_id=None,
            )
        )
        db.flush()
        db.add(
            UserCredential(
                user_id=user_id,
                email_normalized=normalized,
                password_hash=hash_password(body.password),
                created_at=now,
                password_changed_at=now,
                disabled_at=None,
            )
        )
        db.add(
            ClinicSettings(
                clinic_id=clinic_id,
                ai_mode_override=None,
                voice_enabled_override=None,
                version=1,
                updated_by=user_id,
                updated_at=now,
            )
        )
        db.execute(
            update(ClinicOnboardingToken)
            .where(
                ClinicOnboardingToken.onboarding_token_id == row.onboarding_token_id
            )
            .values(clinic_id=clinic_id)
        )
        add_audit(
            db,
            actor_id=user_id,
            actor_role="admin",
            action="clinic_onboarded",
            target_type="clinic",
            target_id=clinic_id,
            clinic_id=clinic_id,
            patient_id=None,
            details={"method": "deployment_token"},
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="This setup link can no longer be used")
    except Exception:
        db.rollback()
        raise

    return OnboardingCompleteOut(
        clinic_id=clinic_id,
        user_id=user_id,
        email=normalized,
    )
