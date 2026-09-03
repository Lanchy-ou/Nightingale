from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.auth_security import hash_token
from app.db import SessionLocal
from app.main import app
from app.models import (
    AuditLog,
    AuthSession,
    Clinic,
    ClinicOnboardingToken,
    ClinicSettings,
    User,
    UserCredential,
)
from app.onboarding import issue_onboarding_token
from app.security import reset_rate_limits


def _raw_token(link: str) -> str:
    fragment = urlparse(link).fragment
    return parse_qs(fragment)["token"][0]


def _issue(db_session, *, now: datetime | None = None) -> tuple[str, ClinicOnboardingToken]:
    issued = issue_onboarding_token(
        db_session,
        base_url="http://localhost:5173",
        now=now,
    )
    token = _raw_token(issued.setup_link)
    row = db_session.scalar(
        select(ClinicOnboardingToken).where(
            ClinicOnboardingToken.token_hash == hash_token(token)
        )
    )
    assert row is not None
    return token, row


def _payload(token: str, *, email: str = "owner@new-clinic.example") -> dict:
    return {
        "token": token,
        "clinic_name": "Harbour Family Clinic",
        "admin_name": "Maya Tan",
        "email": email,
        "password": "safe-password-123",
    }


def test_onboarding_token_is_hashed_expiring_and_fragment_only(client, db_session):
    now = datetime(2026, 9, 2, 12, 0, 0)
    token, row = _issue(db_session, now=now)

    assert row.token_hash == hash_token(token)
    assert row.token_hash != token
    assert row.expires_at == now + timedelta(hours=24)
    assert token not in repr(row.__dict__)

    issued = issue_onboarding_token(
        db_session, base_url="https://nightingale.example/base/", now=now
    )
    parsed = urlparse(issued.setup_link)
    assert parsed.path == "/setup"
    assert parsed.query == ""
    assert parse_qs(parsed.fragment)["token"]


def test_preview_and_complete_create_atomic_clinic_admin_without_session(client, db_session):
    token, onboarding = _issue(db_session)

    preview = client.post("/api/onboarding/preview", json={"token": token})
    assert preview.status_code == 200
    assert preview.json()["status"] == "valid"

    completed = client.post("/api/onboarding/complete", json=_payload(token))
    assert completed.status_code == 201, completed.text
    body = completed.json()
    assert body["login_required"] is True
    assert body["email"] == "owner@new-clinic.example"

    db_session.expire_all()
    clinic = db_session.get(Clinic, body["clinic_id"])
    user = db_session.get(User, body["user_id"])
    credential = db_session.get(UserCredential, body["user_id"])
    settings = db_session.get(ClinicSettings, body["clinic_id"])
    onboarding = db_session.get(ClinicOnboardingToken, onboarding.onboarding_token_id)
    assert clinic.name == "Harbour Family Clinic"
    assert (user.role, user.clinic_id, user.patient_id) == (
        "admin",
        clinic.clinic_id,
        None,
    )
    assert credential.email_normalized == "owner@new-clinic.example"
    assert credential.password_hash != "safe-password-123"
    assert settings.ai_mode_override is None
    assert settings.voice_enabled_override is None
    assert onboarding.used_at is not None
    assert onboarding.clinic_id == clinic.clinic_id
    assert db_session.scalars(
        select(AuthSession).where(AuthSession.user_id == user.user_id)
    ).first() is None

    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.clinic_id == clinic.clinic_id)
    ).all()
    assert [row.action for row in audits] == ["clinic_onboarded"]
    audit_blob = repr([row.details for row in audits])
    assert token not in audit_blob
    assert "safe-password-123" not in audit_blob

    login = client.post(
        "/api/auth/login",
        json={"email": "owner@new-clinic.example", "password": "safe-password-123"},
    )
    assert login.status_code == 200
    assert login.json()["clinic_id"] == clinic.clinic_id
    assert login.json()["role"] == "admin"


def test_unknown_used_expired_and_duplicate_email_fail_closed(client, db_session):
    assert client.post(
        "/api/onboarding/preview", json={"token": "not-a-real-token"}
    ).status_code == 404

    expired_token, _ = _issue(
        db_session, now=datetime.now() - timedelta(hours=25)
    )
    expired_preview = client.post(
        "/api/onboarding/preview", json={"token": expired_token}
    )
    assert expired_preview.status_code == 200
    assert expired_preview.json()["status"] == "expired"
    assert client.post(
        "/api/onboarding/complete", json=_payload(expired_token)
    ).status_code == 410

    token, _ = _issue(db_session)
    first = client.post("/api/onboarding/complete", json=_payload(token))
    assert first.status_code == 201
    used_preview = client.post("/api/onboarding/preview", json={"token": token})
    assert used_preview.status_code == 200
    assert used_preview.json()["status"] == "used"
    assert client.post("/api/onboarding/complete", json=_payload(token)).status_code == 409

    duplicate_token, _ = _issue(db_session)
    duplicate = client.post(
        "/api/onboarding/complete",
        json=_payload(duplicate_token, email="admin@demo.clinic"),
    )
    assert duplicate.status_code == 409
    assert "admin@demo.clinic" not in duplicate.text


def test_concurrent_onboarding_token_consumption_has_one_winner(db_session):
    token, row = _issue(db_session)

    def submit(index: int):
        with TestClient(app) as contender:
            return contender.post(
                "/api/onboarding/complete",
                json=_payload(token, email=f"owner{index}@race.example"),
            ).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        statuses = list(pool.map(submit, (1, 2)))

    assert sorted(statuses) == [201, 409]
    with SessionLocal() as db:
        refreshed = db.get(ClinicOnboardingToken, row.onboarding_token_id)
        assert refreshed.used_at is not None
        assert db.query(Clinic).filter(Clinic.name == "Harbour Family Clinic").count() == 1


def test_onboarding_failure_rolls_back_everything(client, db_session, monkeypatch):
    token, row = _issue(db_session)

    def fail_audit(*_args, **_kwargs):
        raise RuntimeError("synthetic audit failure")

    monkeypatch.setattr("app.api.onboarding.add_audit", fail_audit)
    with pytest.raises(RuntimeError, match="synthetic audit failure"):
        client.post("/api/onboarding/complete", json=_payload(token))

    db_session.expire_all()
    assert db_session.get(ClinicOnboardingToken, row.onboarding_token_id).used_at is None
    assert db_session.scalar(
        select(UserCredential).where(
            UserCredential.email_normalized == "owner@new-clinic.example"
        )
    ) is None
    assert db_session.scalar(
        select(Clinic).where(Clinic.name == "Harbour Family Clinic")
    ) is None


def test_onboarding_uses_existing_csrf_and_rate_limit_boundary(monkeypatch):
    monkeypatch.setenv("NANTINGALE_SECURITY_MODE", "strict")
    monkeypatch.setenv("NANTINGALE_FRONTEND_ORIGIN", "https://nightingale.example")
    monkeypatch.setenv("NANTINGALE_AUTH_RATE_LIMIT", "2")
    monkeypatch.setenv("NANTINGALE_AUTH_RATE_WINDOW_SECONDS", "60")
    reset_rate_limits()
    with TestClient(app) as strict_client:
        no_origin = strict_client.post(
            "/api/onboarding/preview", json={"token": "unknown"}
        )
        assert no_origin.status_code == 403
        headers = {
            "Origin": "https://nightingale.example",
            "Sec-Fetch-Site": "same-origin",
        }
        assert strict_client.post(
            "/api/onboarding/preview", json={"token": "unknown"}, headers=headers
        ).status_code == 404
        assert strict_client.post(
            "/api/onboarding/preview", json={"token": "unknown"}, headers=headers
        ).status_code == 404
        blocked = strict_client.post(
            "/api/onboarding/preview", json={"token": "unknown"}, headers=headers
        )
        assert blocked.status_code == 429
        assert blocked.json()["error"]["code"] == "rate_limited"
