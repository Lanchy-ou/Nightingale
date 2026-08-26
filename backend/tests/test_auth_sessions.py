"""D1 required tests: login, session cookie contract, logout/expiry/revoke,
disabled accounts, DB-role authority, demo-header gating and secret hygiene.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.api.auth as auth_api
from app.auth_security import SESSION_COOKIE_NAME
from app.main import app
from app.models import AuditLog, AuthSession, User, UserCredential
from seed import fixture

DEMO_PASSWORD = fixture.DEMO_PASSWORD


def _login(
    client: TestClient, email: str, password: str = DEMO_PASSWORD
) -> tuple[int, dict]:
    r = client.post("/api/auth/login", json={"email": email, "password": password})
    return r.status_code, (r.json() if r.status_code == 200 else r.json())


def _cookie_value(client: TestClient) -> str:
    return client.cookies.get(SESSION_COOKIE_NAME)


# --- login + cookie contract -------------------------------------------------
def test_login_issues_http_only_cookie_with_correct_flags():
    client = TestClient(app)
    status, body = _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    assert status == 200
    assert body["role"] == "clinician"
    assert body["user_id"] == fixture.USER_CLINICIAN_ID
    assert body["authenticated"] is True

    set_cookie = client.cookies  # httpx jar holds it
    token = set_cookie.get(SESSION_COOKIE_NAME)
    assert token and len(token) >= 43  # token_urlsafe(32)

    # Raw header flags contract (dev config: no Secure; only after HTTPS).
    login_headers = client.post(
        "/api/auth/login",
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": DEMO_PASSWORD,
        },
    ).headers.get_list("set-cookie")
    cookie_header = next(h for h in login_headers if h.startswith(SESSION_COOKIE_NAME))
    assert "HttpOnly" in cookie_header
    assert "SameSite=Lax" in cookie_header
    assert "Path=/" in cookie_header
    assert "Secure" not in cookie_header


def test_login_errors_are_uniform_and_leak_nothing():
    client = TestClient(app)
    unknown = client.post(
        "/api/auth/login", json={"email": "ghost@demo.clinic", "password": "x" * 9}
    )
    wrong_pw = client.post(
        "/api/auth/login",
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": "wrong-password-1",
        },
    )
    assert unknown.status_code == wrong_pw.status_code == 401
    assert unknown.json() == wrong_pw.json()


def test_login_always_runs_one_password_verification(monkeypatch, db_session):
    calls: list[str] = []

    def record_verification(password: str, password_hash: str) -> bool:
        calls.append(password_hash)
        return False

    monkeypatch.setattr(auth_api, "verify_password", record_verification)
    client = TestClient(app)

    unknown = client.post(
        "/api/auth/login",
        json={"email": "ghost@demo.clinic", "password": "wrong-password-1"},
    )
    assert unknown.status_code == 401
    assert len(calls) == 1
    assert calls[0] == auth_api.DUMMY_PASSWORD_HASH

    calls.clear()
    credential = db_session.get(UserCredential, fixture.USER_CLINICIAN_ID)
    credential.disabled_at = datetime.now()
    db_session.commit()
    disabled = client.post(
        "/api/auth/login",
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": "wrong-password-1",
        },
    )
    assert disabled.status_code == 401
    assert len(calls) == 1
    assert calls[0] == auth_api.DUMMY_PASSWORD_HASH


def test_auth_validation_errors_never_reflect_passwords_or_internal_paths():
    client = TestClient(app)
    short_secret = "s3cr3t"
    register = client.post(
        "/api/auth/register",
        json={
            "token": "held-invite-token",
            "password": short_secret,
            "name": "Test User",
        },
    )
    assert register.status_code == 422
    assert short_secret not in register.text
    assert "app\\api\\auth.py" not in register.text
    assert "app/api/auth.py" not in register.text

    long_secret = "unique-password-prefix-" + "X" * 260
    login = client.post(
        "/api/auth/login",
        json={"email": "person@example.com", "password": long_secret},
    )
    assert login.status_code == 422
    assert "unique-password-prefix" not in login.text
    assert "app\\api\\auth.py" not in login.text
    assert "app/api/auth.py" not in login.text


def test_login_failure_is_audited_without_email_or_secrets(db_session):
    client = TestClient(app)
    client.post(
        "/api/auth/login",
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": "wrong-password-1",
        },
    )
    client.post(
        "/api/auth/login", json={"email": "ghost@demo.clinic", "password": "x" * 9}
    )
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "login_failure")
    ).all()
    assert len(rows) == 2
    for row in rows:
        assert "wrong-password-1" not in str(row.__dict__)
        assert "ghost@demo.clinic" not in str(row.__dict__)
        assert DEMO_PASSWORD not in str(row.__dict__)
    # known user failure carries actor metadata; unknown email carries none
    assert {r.actor_id for r in rows} == {fixture.USER_CLINICIAN_ID, None}


def test_session_token_is_only_stored_hashed(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    token = _cookie_value(client)
    rows = db_session.scalars(select(AuthSession)).all()
    assert len(rows) == 1
    assert rows[0].token_hash != token
    assert rows[0].token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_session_endpoint_restores_identity_after_refresh():
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_STAFF_ID])
    r = client.get("/api/auth/session")
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == fixture.USER_STAFF_ID
    assert body["role"] == "staff"
    assert body["clinic_id"] == fixture.CLINIC_ID
    assert body["authenticated"] is True


def test_anonymous_session_endpoint_401():
    assert TestClient(app).get("/api/auth/session").status_code == 401


# --- logout / revocation -----------------------------------------------------
def test_logout_revokes_session_and_clears_cookie(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    token = _cookie_value(client)
    assert client.get("/api/auth/session").status_code == 200

    r = client.post("/api/auth/logout")
    assert r.status_code == 200
    assert r.json() == {"status": "logged_out"}
    # Cookie cleared client-side and revoked server-side.
    assert client.cookies.get(SESSION_COOKIE_NAME) is None
    assert client.get("/api/auth/session").status_code == 401

    # Replaying the old token (e.g. a stolen copy) must stay dead.
    replay = TestClient(app)
    replay.cookies.set(SESSION_COOKIE_NAME, token)
    assert replay.get("/api/auth/session").status_code == 401

    row = db_session.scalars(select(AuthSession)).one()
    assert row.revoked_at is not None
    logout_audit = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "logout")
    ).all()
    assert len(logout_audit) == 1
    assert logout_audit[0].actor_id == fixture.USER_CLINICIAN_ID
    revoke_audit = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "session_revoked")
    ).all()
    assert len(revoke_audit) == 1
    assert revoke_audit[0].target_id == row.session_id
    assert revoke_audit[0].actor_id == fixture.USER_CLINICIAN_ID


def test_logout_revoke_and_audits_commit_atomically(monkeypatch, db_session):
    client = TestClient(app, raise_server_exceptions=False)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    token = _cookie_value(client)
    real_add_audit = auth_api.add_audit

    def fail_on_revoke(db, **kwargs):
        if kwargs["action"] == "session_revoked":
            raise RuntimeError("simulated audit failure")
        return real_add_audit(db, **kwargs)

    monkeypatch.setattr(auth_api, "add_audit", fail_on_revoke)
    assert client.post("/api/auth/logout").status_code == 500

    db_session.expire_all()
    row = db_session.scalars(select(AuthSession)).one()
    assert row.revoked_at is None
    actions = db_session.scalars(
        select(AuditLog.action).where(
            AuditLog.action.in_(("logout", "session_revoked"))
        )
    ).all()
    assert actions == []

    replay = TestClient(app)
    replay.cookies.set(SESSION_COOKIE_NAME, token)
    assert replay.get("/api/auth/session").status_code == 200


def test_second_logout_is_a_safe_noop():
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    assert client.post("/api/auth/logout").status_code == 200
    # No session now: require_auth rejects with 401 (revoke was atomic).
    assert client.post("/api/auth/logout").status_code == 401


def test_expired_session_is_rejected(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    row = db_session.scalars(select(AuthSession)).one()
    row.expires_at = datetime.now() - timedelta(seconds=1)
    db_session.commit()
    assert client.get("/api/auth/session").status_code == 401
    assert client.get(f"/api/patients/{fixture.PATIENT_ID}").status_code == 401


def test_revoked_session_is_rejected(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    row = db_session.scalars(select(AuthSession)).one()
    row.revoked_at = datetime.now()
    db_session.commit()
    assert client.get("/api/auth/session").status_code == 401


def test_disabled_account_blocks_login_and_existing_sessions(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    assert client.get("/api/auth/session").status_code == 200

    credential = db_session.get(UserCredential, fixture.USER_CLINICIAN_ID)
    credential.disabled_at = datetime.now()
    db_session.commit()

    # Existing session is dead immediately.
    assert client.get("/api/auth/session").status_code == 401
    # Login is rejected with the same uniform body as a wrong password.
    r = client.post(
        "/api/auth/login",
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": DEMO_PASSWORD,
        },
    )
    assert r.status_code == 401
    wrong = client.post(
        "/api/auth/login",
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": "wrong-password-1",
        },
    )
    assert r.json() == wrong.json()


# --- DB role authority / header escalation ----------------------------------
def test_db_role_change_applies_immediately_and_headers_cannot_escalate(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_STAFF_ID])
    assert client.get("/api/auth/session").json()["role"] == "staff"

    # Role changes in the DB take effect on the next request.
    user = db_session.get(User, fixture.USER_STAFF_ID)
    user.role = "clinician"
    db_session.commit()
    body = client.get("/api/auth/session").json()
    assert body["role"] == "clinician"

    # A stale X-Role header can never override or escalate the session user.
    r = client.get("/api/auth/session", headers={"X-Role": "staff"})
    assert r.status_code == 200
    assert r.json()["role"] == "clinician"

    # Demote to patient: session user loses clinical access immediately.
    user = db_session.get(User, fixture.USER_STAFF_ID)
    user.role = "patient"
    user.patient_id = fixture.PATIENT_B_ID
    db_session.commit()
    assert client.get("/api/auth/session").json()["role"] == "patient"
    # Own record is still hidden from glance (patients have no read_glance).
    assert client.get(f"/api/patients/{fixture.PATIENT_B_ID}/glance").status_code == 403
    # Other patients' records are scope-hidden (uniform 404).
    assert client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").status_code == 404


def test_session_user_patient_mapping_comes_from_db(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_PATIENT_ID])
    body = client.get("/api/auth/session").json()
    assert body["patient_id"] == fixture.PATIENT_ID
    assert client.get(f"/api/patients/{fixture.PATIENT_ID}").status_code == 200
    assert client.get(f"/api/patients/{fixture.PATIENT_B_ID}").status_code == 404


# --- demo header gating ------------------------------------------------------
def test_legacy_demo_headers_default_off(monkeypatch):
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)
    client = TestClient(app)
    r = client.get(
        f"/api/patients/{fixture.PATIENT_ID}",
        headers={"X-User-Id": fixture.USER_CLINICIAN_ID, "X-Role": "clinician"},
    )
    assert r.status_code == 401


def test_legacy_demo_headers_work_only_with_flag_and_never_elevate(client):
    # conftest enables NANTINGALE_DEMO_AUTH=true for the header fixtures.
    r = client.get(
        f"/api/patients/{fixture.PATIENT_ID}",
        headers={"X-User-Id": fixture.USER_PATIENT_ID, "X-Role": "clinician"},
    )
    assert r.status_code == 403  # mismatch rejected, never trusted


# --- secret hygiene across the whole audit trail -----------------------------
def test_no_password_or_tokens_anywhere_in_audit_or_identity_tables(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    session_token = _cookie_value(client)
    client.get("/api/auth/session")
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/login",
        json={"email": "ghost@demo.clinic", "password": "wrong-password-1"},
    )

    rows = db_session.scalars(select(AuditLog)).all()
    assert rows, "expected audit rows"
    for row in rows:
        blob = json.dumps({k: v for k, v in row.__dict__.items() if not k.startswith("_")}, default=str)
        assert DEMO_PASSWORD not in blob
        assert "wrong-password-1" not in blob
        assert session_token not in blob

    sessions = db_session.scalars(select(AuthSession)).all()
    for s in sessions:
        assert s.token_hash != session_token
        assert session_token not in json.dumps(s.__dict__, default=str)


def test_register_does_not_issue_a_session():
    client = TestClient(app)
    admin = TestClient(app)
    _login(admin, fixture.DEMO_EMAILS[fixture.USER_ADMIN_ID])
    r = admin.post(
        "/api/auth/invites",
        json={"email": "nosession@demo.clinic", "role": "staff"},
    )
    token = r.json()["invite_link"].split("token=", 1)[1]
    reg = client.post(
        "/api/auth/register",
        json={"token": token, "password": "strong-pass-1", "name": "No Session"},
    )
    assert reg.status_code == 201
    assert "set-cookie" not in reg.headers
    assert client.get("/api/auth/session").status_code == 401


def test_login_records_login_success_audit(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_ADMIN_ID])
    rows = db_session.scalars(
        select(AuditLog).where(AuditLog.action == "login_success")
    ).all()
    assert len(rows) == 1
    assert rows[0].actor_id == fixture.USER_ADMIN_ID
    assert rows[0].target_type == "session"


def test_last_seen_tracking_initialized(db_session):
    client = TestClient(app)
    _login(client, fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])
    row = db_session.scalars(select(AuthSession)).one()
    assert row.last_seen_at is not None
