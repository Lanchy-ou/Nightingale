from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.main import app
from app.onboarding import issue_onboarding_token


def _token() -> str:
    with SessionLocal() as db:
        issued = issue_onboarding_token(db, base_url="http://localhost:5173")
    return parse_qs(urlparse(issued.setup_link).fragment)["token"][0]


def _onboard(client: TestClient, *, suffix: str) -> dict:
    response = client.post(
        "/api/onboarding/complete",
        json={
            "token": _token(),
            "clinic_name": f"Journey Clinic {suffix}",
            "admin_name": f"Admin {suffix}",
            "email": f"admin-{suffix}@journey.example",
            "password": "journey-password-123",
        },
    )
    assert response.status_code == 201, response.text
    assert client.get("/api/auth/session").status_code == 401
    login = client.post(
        "/api/auth/login",
        json={
            "email": f"admin-{suffix}@journey.example",
            "password": "journey-password-123",
        },
    )
    assert login.status_code == 200, login.text
    return response.json()


def test_new_clinic_admin_import_invite_settings_and_cross_clinic_isolation():
    with TestClient(app) as clinic_a, TestClient(app) as clinic_b:
        first = _onboard(clinic_a, suffix="a")
        preview = clinic_a.post(
            "/api/admin/patient-imports/preview?source_system=legacy",
            content="external_patient_id,name\nP-900,Journey Patient\n",
            headers={"Content-Type": "text/csv"},
        )
        assert preview.status_code == 200, preview.text
        committed = clinic_a.post(
            f"/api/admin/patient-imports/{preview.json()['batch_id']}/commit"
        )
        assert committed.status_code == 200
        patient_id = committed.json()["rows"][0]["patient_id"]
        invite = clinic_a.post(
            "/api/auth/invites",
            json={
                "email": "patient@journey.example",
                "role": "patient",
                "patient_id": patient_id,
            },
        )
        assert invite.status_code == 200, invite.text
        settings = clinic_a.get("/api/admin/clinic-settings").json()
        changed = clinic_a.patch(
            "/api/admin/clinic-settings",
            json={
                "expected_version": settings["version"],
                "ai_mode": "local",
                "voice_mode": "disabled",
            },
        )
        assert changed.status_code == 200

        second = _onboard(clinic_b, suffix="b")
        assert first["clinic_id"] != second["clinic_id"]
        cross = clinic_b.post(
            f"/api/admin/patient-imports/{preview.json()['batch_id']}/commit"
        )
        missing = clinic_b.post(
            "/api/admin/patient-imports/pib_missing/commit"
        )
        assert cross.status_code == missing.status_code == 404
        assert cross.json() == missing.json()
        clinic_b_settings = clinic_b.get("/api/admin/clinic-settings").json()
        assert clinic_b_settings["ai"]["selected_mode"] == "inherit"
        assert clinic_b_settings["voice"]["selected_mode"] == "inherit"
