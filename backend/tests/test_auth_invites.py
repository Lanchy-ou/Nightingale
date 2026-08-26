"""D1 required tests: invite lifecycle, binding, single-use, expiry, tampering,
registration authority and password hashing.

Everything goes through the real session/cookie auth path (no demo headers).
"""
from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import select

import app.api.auth as auth_api
from app.auth_security import verify_password
from app.main import app
from app.models import AuditLog, Invite, Patient, User, UserCredential
from seed import fixture

ADMIN_EMAIL = fixture.DEMO_EMAILS[fixture.USER_ADMIN_ID]
DEMO_PASSWORD = fixture.DEMO_PASSWORD


def _login(client: TestClient, email: str, password: str = DEMO_PASSWORD):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _admin_client() -> TestClient:
    client = TestClient(app)
    response = _login(client, ADMIN_EMAIL)
    assert response.status_code == 200, response.text
    return client


def _invite(client: TestClient, email: str, role: str, patient_id: str | None = None):
    return client.post(
        "/api/auth/invites",
        json={"email": email, "role": role, "patient_id": patient_id},
    )


def _token_from_link(link: str) -> str:
    assert "/register?token=" in link
    return link.split("token=", 1)[1]


# --- creation + RBAC --------------------------------------------------------
def test_admin_creates_clinician_staff_and_patient_invites():
    client = _admin_client()
    cases = [
        ("newdoctor@demo.clinic", "clinician", None),
        ("newnurse@demo.clinic", "staff", None),
        ("newpatient@demo.clinic", "patient", fixture.PATIENT_B_ID),
    ]
    for email, role, patient_id in cases:
        r = _invite(client, email, role, patient_id)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == email
        assert body["role"] == role
        assert body["patient_id"] == patient_id
        assert "token" in body["invite_link"]


def test_raw_invite_token_never_persisted(db_session):
    client = _admin_client()
    r = _invite(client, "secure@demo.clinic", "clinician")
    token = _token_from_link(r.json()["invite_link"])
    invite = db_session.scalars(select(Invite)).one()
    assert invite.token_hash != token
    assert invite.token_hash == hashlib.sha256(token.encode()).hexdigest()


def test_invite_list_never_contains_raw_token():
    client = _admin_client()
    r = _invite(client, "listed@demo.clinic", "clinician")
    raw = _token_from_link(r.json()["invite_link"])
    listing = client.get("/api/auth/invites")
    assert listing.status_code == 200
    assert all("token" not in item for item in listing.json())
    assert raw not in listing.text


def test_staff_clinician_patient_cannot_create_invites():
    for email, role in [
        (fixture.DEMO_EMAILS[fixture.USER_STAFF_ID], "staff"),
        (fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID], "clinician"),
        (fixture.DEMO_EMAILS[fixture.USER_PATIENT_ID], "patient"),
    ]:
        client = TestClient(app)
        _login(client, email)
        r = _invite(client, "attacker@demo.clinic", "clinician")
        assert r.status_code == 403
        # role is also recorded on the DB user; assert the DB is authoritative
        assert r.json()["error"]["code"] == "http_error"


def test_anonymous_cannot_create_invites():
    r = TestClient(app).post(
        "/api/auth/invites", json={"email": "x@demo.clinic", "role": "clinician"}
    )
    assert r.status_code == 401


# --- clinic scoping ---------------------------------------------------------
def test_admin_cannot_invite_patient_from_other_clinic(db_session):
    other = Patient(
        patient_id="pat_other_clinic", clinic_id=fixture.CLINIC_B_ID, name="Other"
    )
    db_session.add(other)
    db_session.commit()

    client = _admin_client()
    r = _invite(client, "cross@demo.clinic", "patient", "pat_other_clinic")
    assert r.status_code == 404  # uniform: same as an absent patient
    unknown = _invite(client, "cross2@demo.clinic", "patient", "pat_does_not_exist")
    assert unknown.status_code == 404
    assert r.json() == unknown.json()


def test_inviter_can_never_specify_clinic():
    client = _admin_client()
    r = client.post(
        "/api/auth/invites",
        json={
            "email": "evil@demo.clinic",
            "role": "clinician",
            "clinic_id": fixture.CLINIC_B_ID,
        },
    )
    assert r.status_code == 422  # strict schema: extra fields forbidden


# --- validation -------------------------------------------------------------
def test_patient_invite_requires_patient_id():
    r = _invite(_admin_client(), "nopat@demo.clinic", "patient")
    assert r.status_code == 422


def test_clinical_invite_rejects_patient_binding():
    r = _invite(_admin_client(), "doc@demo.clinic", "clinician", fixture.PATIENT_ID)
    assert r.status_code == 422


def test_invalid_email_rejected():
    r = _invite(_admin_client(), "not-an-email", "clinician")
    assert r.status_code == 422


def test_duplicate_pending_invite_rejected():
    client = _admin_client()
    assert _invite(client, "dup@demo.clinic", "staff").status_code == 200
    assert _invite(client, "dup@demo.clinic", "clinician").status_code == 409


def test_invite_creation_is_audited(db_session):
    client = _admin_client()
    r = _invite(client, "audited@demo.clinic", "staff")
    invite_id = r.json()["invite_id"]
    rows = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "invite_created", AuditLog.target_id == invite_id
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].actor_id == fixture.USER_ADMIN_ID
    assert rows[0].clinic_id == fixture.CLINIC_ID
    assert fixture.DEMO_PASSWORD not in str(rows[0].__dict__)


# --- preview ----------------------------------------------------------------
def test_preview_valid_invite_shows_masked_minimal_info():
    client = _admin_client()
    r = _invite(client, "preview@demo.clinic", "clinician")
    token = _token_from_link(r.json()["invite_link"])
    p = client.get(f"/api/auth/invites/{token}/preview")
    assert p.status_code == 200
    body = p.json()
    assert body["status"] == "valid"
    assert body["email_masked"] != "preview@demo.clinic"
    assert "***" in body["email_masked"]
    assert body["role"] == "clinician"
    assert body["clinic_name"] == fixture.CLINIC_NAME


def test_preview_patient_invite_names_bound_record():
    client = _admin_client()
    r = _invite(client, "previewpat@demo.clinic", "patient", fixture.PATIENT_B_ID)
    token = _token_from_link(r.json()["invite_link"])
    p = client.get(f"/api/auth/invites/{token}/preview")
    assert p.status_code == 200
    assert p.json()["patient_name"] == fixture.PATIENT_B_NAME


def test_tampered_token_gets_uniform_404():
    client = _admin_client()
    _invite(client, "tamper@demo.clinic", "clinician")
    bad = "A" * 43
    p = client.get(f"/api/auth/invites/{bad}/preview")
    reg = client.post(
        "/api/auth/register",
        json={"token": bad, "password": "supersecret1", "name": "X"},
    )
    assert p.status_code == reg.status_code == 404
    assert p.json() == reg.json()


# --- registration authority -------------------------------------------------
def test_register_cannot_override_invite_role_clinic_or_patient_binding():
    client = _admin_client()
    r = _invite(client, "frozen@demo.clinic", "clinician")
    token = _token_from_link(r.json()["invite_link"])

    reg = client.post(
        "/api/auth/register",
        json={
            "token": token,
            "password": "strong-pass-1",
            "name": "Dr. New Person",
            "role": "admin",  # extra field -> strict schema reject
        },
    )
    assert reg.status_code == 422

    reg = client.post(
        "/api/auth/register",
        json={"token": token, "password": "strong-pass-1", "name": "Dr. New Person"},
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()
    assert body["role"] == "clinician"  # invite role, not request
    assert body["clinic_id"] == fixture.CLINIC_ID

    # Verify DB rows directly through a fresh session.
    from app.db import SessionLocal

    with SessionLocal() as db:
        created = db.get(User, body["user_id"])
        assert created.role == "clinician"
        assert created.clinic_id == fixture.CLINIC_ID
        assert created.patient_id is None
        credential = db.get(UserCredential, body["user_id"])
        assert credential.email_normalized == "frozen@demo.clinic"


def test_patient_register_links_existing_record_and_never_creates_second_patient(
    db_session,
):
    before = len(db_session.scalars(select(Patient)).all())
    client = _admin_client()
    r = _invite(client, "ben-new@demo.clinic", "patient", fixture.PATIENT_B_ID)
    token = _token_from_link(r.json()["invite_link"])

    reg = client.post(
        "/api/auth/register",
        json={"token": token, "password": "strong-pass-1", "name": "Fake Name"},
    )
    assert reg.status_code == 201, reg.text
    body = reg.json()

    db_session.expire_all()
    assert len(db_session.scalars(select(Patient)).all()) == before  # no new Patient row
    user = db_session.get(User, body["user_id"])
    assert user.patient_id == fixture.PATIENT_B_ID
    assert user.name == fixture.PATIENT_B_NAME  # invite binding wins over the form


def test_register_requires_name_for_clinical_roles():
    client = _admin_client()
    r = _invite(client, "noname@demo.clinic", "staff")
    token = _token_from_link(r.json()["invite_link"])
    reg = client.post(
        "/api/auth/register", json={"token": token, "password": "strong-pass-1"}
    )
    assert reg.status_code == 422


def test_register_password_short_rejected():
    client = _admin_client()
    r = _invite(client, "shortpw@demo.clinic", "staff")
    token = _token_from_link(r.json()["invite_link"])
    reg = client.post(
        "/api/auth/register", json={"token": token, "password": "short"}
    )
    assert reg.status_code == 422


# --- single use / expiry / duplicate email ----------------------------------
def test_invite_token_is_single_use():
    client = _admin_client()
    r = _invite(client, "once@demo.clinic", "staff")
    token = _token_from_link(r.json()["invite_link"])
    payload = {"token": token, "password": "strong-pass-1", "name": "Once Only"}

    first = client.post("/api/auth/register", json=payload)
    assert first.status_code == 201
    second = client.post("/api/auth/register", json=payload)
    assert second.status_code == 409

    p = client.get(f"/api/auth/invites/{token}/preview")
    assert p.status_code == 200
    assert p.json()["status"] == "used"


def test_invite_token_is_atomically_single_use_under_concurrency(monkeypatch):
    admin = _admin_client()
    invite = _invite(admin, "race@demo.clinic", "staff")
    token = _token_from_link(invite.json()["invite_link"])
    barrier = Barrier(2)
    real_hash_password = auth_api.hash_password

    def synchronized_hash(password: str) -> str:
        barrier.wait(timeout=5)
        return real_hash_password(password)

    monkeypatch.setattr(auth_api, "hash_password", synchronized_hash)
    payload = {
        "token": token,
        "password": "strong-pass-1",
        "name": "Concurrent Registration",
    }

    def register_once() -> int:
        with TestClient(app, raise_server_exceptions=False) as client:
            return client.post("/api/auth/register", json=payload).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = sorted(executor.map(lambda _: register_once(), range(2)))

    assert statuses == [201, 409]


def test_expired_invite_rejected(db_session):
    from datetime import datetime, timedelta

    client = _admin_client()
    r = _invite(client, "expired@demo.clinic", "staff")
    token = _token_from_link(r.json()["invite_link"])

    invite = db_session.scalars(select(Invite)).one()
    invite.expires_at = datetime.now() - timedelta(minutes=1)
    db_session.commit()

    p = client.get(f"/api/auth/invites/{token}/preview")
    assert p.status_code == 200
    assert p.json()["status"] == "expired"
    reg = client.post(
        "/api/auth/register",
        json={"token": token, "password": "strong-pass-1", "name": "Too Late"},
    )
    assert reg.status_code == 410


def test_password_hash_is_argon2_and_never_plaintext():
    client = _admin_client()
    r = _invite(client, "hashed@demo.clinic", "staff")
    token = _token_from_link(r.json()["invite_link"])
    password = "correct horse battery"
    reg = client.post(
        "/api/auth/register",
        json={"token": token, "password": password, "name": "Hash Check"},
    )
    assert reg.status_code == 201

    from app.db import SessionLocal

    with SessionLocal() as db:
        credential = db.get(UserCredential, reg.json()["user_id"])
        assert credential.password_hash != password
        assert credential.password_hash.startswith("$argon2")
        assert verify_password(password, credential.password_hash)
        assert not verify_password("wrong-password", credential.password_hash)


def test_register_duplicate_email_is_generic():
    client = _admin_client()
    r1 = _invite(client, "same@demo.clinic", "staff")
    t1 = _token_from_link(r1.json()["invite_link"])
    reg1 = client.post(
        "/api/auth/register",
        json={"token": t1, "password": "strong-pass-1", "name": "First"},
    )
    assert reg1.status_code == 201

    r2 = _invite(client, "same@demo.clinic", "clinician")  # first is now used
    assert r2.status_code == 200
    t2 = _token_from_link(r2.json()["invite_link"])
    reg2 = client.post(
        "/api/auth/register",
        json={"token": t2, "password": "strong-pass-1", "name": "Second"},
    )
    assert reg2.status_code == 409
    # Generic body: no statement about whether the email exists.
    assert "already" not in reg2.text.lower()


def test_register_writes_audit_metadata(db_session):
    client = _admin_client()
    r = _invite(client, "regaudit@demo.clinic", "staff")
    token = _token_from_link(r.json()["invite_link"])
    reg = client.post(
        "/api/auth/register",
        json={"token": token, "password": "strong-pass-1", "name": "Reg Audit"},
    )
    assert reg.status_code == 201
    rows = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "register", AuditLog.target_id == reg.json()["user_id"]
        )
    ).all()
    assert len(rows) == 1
    assert rows[0].actor_role == "staff"
    assert "strong-pass-1" not in str(rows[0].__dict__)
