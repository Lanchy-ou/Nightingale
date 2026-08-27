"""D1 identity security primitives.

Everything here is real, not decorative:
- passwords are hashed with Argon2id (argon2-cffi, default parameters);
- invite and session tokens are 256-bit `secrets.token_urlsafe` values;
- only SHA-256 hashes of tokens are ever persisted;
- session cookies are HttpOnly + SameSite=Lax (+ Secure once HTTPS is deployed).

No module may log a raw password, invite token or session token.
"""
from __future__ import annotations

import hashlib
import os
import secrets
from datetime import datetime, timedelta

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

SESSION_COOKIE_NAME = "nantingale_session"

# Argon2id is the library default (type=ID, t=3, m=64 MiB, p=4).
_password_hasher = PasswordHasher()


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


# Login must perform one Argon2 verification even when the email is unknown or
# the credential is disabled. This process-local dummy hash prevents account
# enumeration through the otherwise large Argon2 timing difference.
DUMMY_PASSWORD_HASH = hash_password(secrets.token_urlsafe(32))


def new_invite_token() -> str:
    """256-bit one-time invite token (>= the required 128 bits)."""
    return secrets.token_urlsafe(32)


def new_session_token() -> str:
    """256-bit opaque bearer token for the session cookie."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def normalize_email(email: str) -> str:
    return email.strip().lower()


def is_plausible_email(email: str) -> bool:
    local, sep, domain = email.partition("@")
    return bool(sep and local and "." in domain)


def session_ttl() -> timedelta:
    hours = float(os.environ.get("NANTINGALE_SESSION_TTL_HOURS", "12"))
    return timedelta(hours=hours)


def invite_ttl() -> timedelta:
    days = float(os.environ.get("NANTINGALE_INVITE_TTL_DAYS", "7"))
    return timedelta(days=days)


def secure_cookies() -> bool:
    # False until the deployment serves HTTPS; set NANTINGALE_SECURE_COOKIES=true
    # behind TLS. Documented in README as a deployment boundary, not a code gap.
    return os.environ.get("NANTINGALE_SECURE_COOKIES", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def last_seen_refresh_seconds() -> int:
    return int(os.environ.get("NANTINGALE_LAST_SEEN_REFRESH_SECONDS", "60"))


def session_cookie_value(token: str) -> str:
    """Cookie attributes per D1: HttpOnly, SameSite=Lax, Path=/, Secure when configured."""
    parts = [f"{SESSION_COOKIE_NAME}={token}", "Path=/", "HttpOnly", "SameSite=Lax"]
    if secure_cookies():
        parts.append("Secure")
    parts.append(f"Max-Age={int(session_ttl().total_seconds())}")
    return "; ".join(parts)


def cleared_session_cookie() -> str:
    parts = [
        f"{SESSION_COOKIE_NAME}=",
        "Path=/",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if secure_cookies():
        parts.append("Secure")
    parts.append("Max-Age=0")
    return "; ".join(parts)


def utc_now() -> datetime:
    # The rest of the codebase uses naive local datetimes for record-keeping;
    # keep the same convention so comparisons stay consistent.
    return datetime.now()
