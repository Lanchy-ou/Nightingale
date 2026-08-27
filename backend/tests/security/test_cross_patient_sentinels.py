from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed import fixture


SENTINEL = "CROSS_PATIENT_INTERNAL_SENTINEL"


def _login(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post(
        "/api/auth/login",
        json={"email": email, "password": fixture.DEMO_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return client


def test_patient_session_cannot_cross_patient_or_reach_internal_collections():
    with _login(fixture.DEMO_EMAILS[fixture.USER_PATIENT_ID]) as patient:
        own = patient.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view")
        cross = patient.get(f"/api/patients/{fixture.PATIENT_B_ID}/patient-view")
        absent = patient.get("/api/patients/pat_absent/patient-view")
        internal = patient.get(f"/api/patients/{fixture.PATIENT_ID}/glance")

    assert own.status_code == 200
    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json()
    assert internal.status_code == 403
    assert SENTINEL not in own.text


def test_cross_clinic_clinician_gets_the_same_404_as_absent_patient():
    with _login(fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_B_ID]) as clinician:
        cross = clinician.get(f"/api/patients/{fixture.PATIENT_ID}")
        absent = clinician.get("/api/patients/pat_absent")

    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json()
