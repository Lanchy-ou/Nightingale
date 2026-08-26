"""D1 required tests: session-authenticated routing + RBAC scope.

Proves the M3 RBAC matrix still holds when identity comes from a real login
session (not demo headers): patient isolation, cross-clinic 404 uniformity,
admin read-only, and the patient ingest path under session identity.
"""
from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Artifact
from seed import fixture

DEMO_PASSWORD = fixture.DEMO_PASSWORD


def _login_client(email: str) -> TestClient:
    client = TestClient(app)
    r = client.post(
        "/api/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    assert r.status_code == 200, r.text
    return client


def _clinician() -> TestClient:
    return _login_client(fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID])


def _patient() -> TestClient:
    return _login_client(fixture.DEMO_EMAILS[fixture.USER_PATIENT_ID])


def _admin() -> TestClient:
    return _login_client(fixture.DEMO_EMAILS[fixture.USER_ADMIN_ID])


# --- patient session isolation ----------------------------------------------
def test_patient_session_cannot_read_internal_comments():
    c = _patient()
    r = c.get(f"/api/events/{fixture.EVT_DOC_0821}/comments")
    assert r.status_code == 403


def test_patient_session_sees_only_patient_instruction_artifacts():
    c = _patient()
    r = c.get(f"/api/events/{fixture.EVT_DOC_0821}/artifacts")
    assert r.status_code == 200
    assert {a["artifact_type"] for a in r.json()} == {"patient_instruction"}


def test_patient_session_cannot_read_raw_ai_notes_or_glance():
    c = _patient()
    assert c.get(f"/api/patients/{fixture.PATIENT_ID}/glance").status_code == 403
    assert (
        c.get("/api/highlights/hl_headache_worsening/provenance").status_code == 403
    )
    # Raw AI-scribed summary is hidden behind the artifact allowlist.
    r = c.get(f"/api/events/{fixture.EVT_DOC_0821}/artifacts")
    types = {a["artifact_type"] for a in r.json()}
    assert "ai_doctor_consult_summary" not in types
    assert "transcript" not in types


def test_patient_session_can_read_own_patient_view_only():
    c = _patient()
    assert (
        c.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view").status_code == 200
    )
    assert (
        c.get(f"/api/patients/{fixture.PATIENT_B_ID}/patient-view").status_code == 404
    )


def test_patient_session_cannot_read_other_patient_same_clinic():
    c = _patient()
    assert c.get(f"/api/patients/{fixture.PATIENT_B_ID}").status_code == 404


def test_patient_session_ingest_uses_session_identity(db_session):
    c = _patient()
    r = c.post(
        f"/api/patients/{fixture.PATIENT_ID}/sessions",
        json={
            "session_id": "d1-scope-check",
            "event_type": "patient_followup",
            "started_at": "2026-08-26T15:00:00",
            "content": {
                "messages": [
                    {"id": "m1", "speaker": "patient", "text": "Feeling better today."}
                ]
            },
        },
    )
    assert r.status_code == 200, r.text
    raw = db_session.scalars(
        select(Artifact).where(Artifact.artifact_type == "raw_conversation")
    ).all()
    new_raw = next(a for a in raw if a.event_id.startswith("evt_"))
    assert new_raw.author_id == fixture.USER_PATIENT_ID  # session user, not header


# --- cross-clinic uniformity -------------------------------------------------
def test_cross_clinic_session_still_uniform_404():
    c = _login_client(fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_B_ID])
    cross = c.get(f"/api/patients/{fixture.PATIENT_ID}")
    absent = c.get("/api/patients/pat_does_not_exist")
    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json()
    # Own-clinic directory returns only own-clinic rows (none seeded).
    own = c.get("/api/patients")
    assert own.status_code == 200
    assert own.json() == []


def test_cross_clinic_glance_and_artifacts_uniform_404():
    c = _login_client(fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_B_ID])
    assert (
        c.get(f"/api/patients/{fixture.PATIENT_ID}/glance").status_code == 404
    )
    assert (
        c.get(f"/api/events/{fixture.EVT_DOC_0821}/artifacts").status_code == 404
    )


# --- role routing through sessions ------------------------------------------
def test_clinician_session_reaches_clinic_shell_data():
    c = _clinician()
    directory = c.get("/api/patients")
    assert directory.status_code == 200
    ids = {p["patient_id"] for p in directory.json()}
    assert ids == {fixture.PATIENT_ID, fixture.PATIENT_B_ID}
    assert c.get(f"/api/patients/{fixture.PATIENT_ID}/glance").status_code == 200
    # Clinician can create clinician notes, not staff notes (unchanged matrix).
    ok = c.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "clinician_note", "content": {"plan": "d1 check"}},
    )
    assert ok.status_code == 200
    forbidden = c.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "staff_note", "content": {"note": "x"}},
    )
    assert forbidden.status_code == 403


def test_admin_session_is_readonly_for_notes_but_manages_invites():
    c = _admin()
    note = c.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "clinician_note", "content": {"plan": "x"}},
    )
    assert note.status_code == 403
    invite = c.post(
        "/api/auth/invites", json={"email": "route@demo.clinic", "role": "staff"}
    )
    assert invite.status_code == 200
    assert c.get("/api/auth/invites").status_code == 200


def test_staff_session_matrix_unchanged():
    c = _login_client(fixture.DEMO_EMAILS[fixture.USER_STAFF_ID])
    ok = c.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "staff_note", "content": {"note": "d1 check"}},
    )
    assert ok.status_code == 200
    forbidden = c.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "clinician_note", "content": {"plan": "x"}},
    )
    assert forbidden.status_code == 403
    assert (
        c.post(
            "/api/auth/invites",
            json={"email": "sneaky@demo.clinic", "role": "staff"},
        ).status_code
        == 403
    )


def test_anonymous_product_requests_401_without_demo_headers(monkeypatch):
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)
    c = TestClient(app)
    for path in (
        "/api/patients",
        f"/api/patients/{fixture.PATIENT_ID}",
        f"/api/patients/{fixture.PATIENT_ID}/glance",
        f"/api/patients/{fixture.PATIENT_ID}/patient-view",
        f"/api/events/{fixture.EVT_DOC_0821}/artifacts",
        "/api/auth/session",
    ):
        assert c.get(path).status_code == 401, path


def test_403_never_switches_identity():
    # A patient getting 403 on a clinical endpoint must not gain any access by
    # retrying with different state — each request resolves the same session.
    c = _patient()
    for _ in range(2):
        assert c.get(f"/api/patients/{fixture.PATIENT_ID}/glance").status_code == 403
    assert c.get("/api/auth/session").json()["role"] == "patient"
