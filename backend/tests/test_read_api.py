"""M1 smoke test 3: read-only endpoints return 200 with correct shape (M3: authorized)."""
from __future__ import annotations

from seed import fixture


def test_get_patient(clinician_client):
    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["patient_id"] == fixture.PATIENT_ID
    assert body["clinic_id"] == fixture.CLINIC_ID
    assert body["clinic_name"] == fixture.CLINIC_NAME


def test_get_patient_not_found_uses_error_envelope(clinician_client):
    r = clinician_client.get("/api/patients/does_not_exist")
    assert r.status_code == 404
    body = r.json()
    assert body["error"]["code"] == "not_found"
    assert "message" in body["error"]


def test_unauthenticated_gets_401(client):
    r = client.get(f"/api/patients/{fixture.PATIENT_ID}")
    assert r.status_code == 401


def test_list_events_sorted_by_started_at(clinician_client):
    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/events")
    assert r.status_code == 200
    events = r.json()
    assert len(events) == 6
    started = [e["started_at"] for e in events]
    assert started == sorted(started)
    doc = next(e for e in events if e["event_type"] == "doctor_consult")
    assert doc["artifact_count"] == 4


def test_list_artifacts_parallel_representations(clinician_client):
    r = clinician_client.get(f"/api/events/{fixture.EVT_DOC_0821}/artifacts")
    assert r.status_code == 200
    arts = r.json()
    types = {a["artifact_type"] for a in arts}
    assert {"transcript", "ai_doctor_consult_summary", "clinician_note", "patient_instruction"} <= types
    ai = next(a for a in arts if a["artifact_type"] == "ai_doctor_consult_summary")
    assert ai["author_role"] == "system"
    assert ai["provenance_pointer"]["artifact_id"] == fixture.ART_DOC_TRANSCRIPT


def test_list_artifacts_not_found_uses_error_envelope(clinician_client):
    r = clinician_client.get("/api/events/nope/artifacts")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_role_context_resolves_injected_headers(client):
    r = client.get(
        "/api/me",
        headers={"X-User-Id": fixture.USER_CLINICIAN_ID, "X-Role": "clinician"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["user_id"] == fixture.USER_CLINICIAN_ID
    assert body["role"] == "clinician"
    assert body["clinic_id"] == fixture.CLINIC_ID
    assert body["authenticated"] is True


def test_role_context_rejects_mismatched_x_role(client):
    # X-Role is never a privilege source; a mismatch with the DB role is rejected.
    r = client.get(
        "/api/me",
        headers={"X-User-Id": fixture.USER_PATIENT_ID, "X-Role": "staff"},
    )
    assert r.status_code == 403


def test_role_context_maps_patient_user_to_own_record(client):
    r = client.get("/api/me", headers={"X-User-Id": fixture.USER_PATIENT_ID})
    assert r.status_code == 200
    body = r.json()
    assert body["role"] == "patient"
    assert body["patient_id"] == fixture.PATIENT_ID


def test_role_context_unauthenticated_without_headers(client):
    r = client.get("/api/me")
    assert r.status_code == 200
    body = r.json()
    assert body["authenticated"] is False
    assert body["user_id"] is None and body["role"] is None
