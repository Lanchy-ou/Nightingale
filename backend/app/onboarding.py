"""Deployment-owned issuance for one-time clinic onboarding links."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy.orm import Session

from .auth_security import hash_token, new_invite_token
from .ids import new_id
from .models import ClinicOnboardingToken

ONBOARDING_TOKEN_TTL = timedelta(hours=24)


@dataclass(frozen=True)
class IssuedOnboardingToken:
    onboarding_token_id: str
    setup_link: str
    expires_at: datetime


def _setup_origin(base_url: str) -> str:
    parsed = urlsplit(base_url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base_url must be an absolute http(s) URL")
    return urlunsplit((parsed.scheme, parsed.netloc, "", "", ""))


def issue_onboarding_token(
    db: Session, *, base_url: str, now: datetime | None = None
) -> IssuedOnboardingToken:
    issued_at = now or datetime.now()
    raw_token = new_invite_token()
    row = ClinicOnboardingToken(
        onboarding_token_id=new_id("obt"),
        token_hash=hash_token(raw_token),
        created_at=issued_at,
        expires_at=issued_at + ONBOARDING_TOKEN_TTL,
        used_at=None,
        clinic_id=None,
    )
    db.add(row)
    db.commit()
    return IssuedOnboardingToken(
        onboarding_token_id=row.onboarding_token_id,
        setup_link=f"{_setup_origin(base_url)}/setup#token={quote(raw_token)}",
        expires_at=row.expires_at,
    )
