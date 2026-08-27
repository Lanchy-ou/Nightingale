"""D4 clinician-only scope gate for the Copilot endpoint."""
from fastapi.testclient import TestClient

from app.main import app
from seed import fixture

URL = f"/api/patients/{fixture.PATIENT_ID}/copilot/query"
BODY = {"category": "what_changed"}


def test_only_clinician_can_query_copilot(clinician_client, staff_client, patient_client, admin_client, client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    assert clinician_client.post(URL, json=BODY).status_code == 200
    assert staff_client.post(URL, json=BODY).status_code == 403
    assert patient_client.post(URL, json=BODY).status_code == 403
    assert admin_client.post(URL, json=BODY).status_code == 403
    assert client.post(URL, json=BODY).status_code == 401


def test_cross_clinic_and_absent_are_uniform_404(client):
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}) as other:
        cross = other.post(URL, json=BODY)
        absent = other.post("/api/patients/pat_absent/copilot/query", json=BODY)
    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json()
