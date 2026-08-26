"""Required test: server-side RBAC scope (assertions are the spec).

All assertions hit the API directly — never through the UI.
"""
from __future__ import annotations

from seed import fixture


# --- role boundaries on note writes --------------------------------------
def test_staff_cannot_create_clinician_note(staff_client):
    r = staff_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "clinician_note", "content": {"plan": "x"}},
    )
    assert r.status_code == 403


def test_clinician_cannot_create_staff_note(clinician_client):
    r = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "staff_note", "content": {"note": "x"}},
    )
    assert r.status_code == 403


def test_staff_can_create_staff_note(staff_client):
    r = staff_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "staff_note", "content": {"note": "hello"}},
    )
    assert r.status_code == 200
    assert r.json()["author_role"] == "staff"


def test_clinician_can_create_clinician_note(clinician_client):
    r = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "clinician_note", "content": {"plan": "hello"}},
    )
    assert r.status_code == 200
    assert r.json()["author_role"] == "clinician"


def test_admin_cannot_write_any_note(admin_client):
    r1 = admin_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "staff_note", "content": {"note": "x"}},
    )
    r2 = admin_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "clinician_note", "content": {"plan": "x"}},
    )
    assert r1.status_code == 403
    assert r2.status_code == 403


# --- privilege escalation / auth -----------------------------------------
def test_patient_with_clinician_header_cannot_escalate(client):
    r = client.get(
        f"/api/patients/{fixture.PATIENT_ID}",
        headers={"X-User-Id": fixture.USER_PATIENT_ID, "X-Role": "clinician"},
    )
    assert r.status_code == 403  # X-Role mismatch is rejected, never trusted


def test_unknown_user_gets_401(client):
    r = client.get(
        f"/api/patients/{fixture.PATIENT_ID}",
        headers={"X-User-Id": "usr_does_not_exist"},
    )
    assert r.status_code == 401


def test_missing_user_gets_401(client):
    r = client.get(f"/api/patients/{fixture.PATIENT_ID}")
    assert r.status_code == 401


# --- patient isolation -----------------------------------------------------
def test_patient_can_read_own_record(patient_client):
    r = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}")
    assert r.status_code == 200


def test_patient_cannot_read_other_patient_same_clinic(patient_client):
    r = patient_client.get(f"/api/patients/{fixture.PATIENT_B_ID}")
    assert r.status_code == 404  # hide existence


def test_patient_cannot_read_internal_comments(patient_client):
    r = patient_client.get(f"/api/events/{fixture.EVT_DOC_0821}/comments")
    assert r.status_code == 403


def test_patient_artifacts_only_patient_instruction(patient_client):
    r = patient_client.get(f"/api/events/{fixture.EVT_DOC_0821}/artifacts")
    assert r.status_code == 200
    types = {a["artifact_type"] for a in r.json()}
    assert types == {"patient_instruction"}  # no transcript / ai summary / clinician note


def test_patient_artifact_count_hides_internal(patient_client):
    r = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/events")
    assert r.status_code == 200
    doc = next(e for e in r.json() if e["event_type"] == "doctor_consult")
    assert doc["artifact_count"] == 1  # only patient_instruction, not 4


def test_patient_cannot_read_glance(patient_client):
    r = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    assert r.status_code == 403


def test_patient_cannot_read_provenance(patient_client):
    r = patient_client.get("/api/highlights/hl_headache_worsening/provenance")
    assert r.status_code == 403


def test_patient_cannot_change_highlight_status(patient_client):
    r = patient_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "accepted"})
    assert r.status_code == 403


# --- cross-clinic ---------------------------------------------------------
def test_cross_clinic_access_404(client):
    r = client.get(
        f"/api/patients/{fixture.PATIENT_ID}",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
    )
    assert r.status_code == 404


def test_absent_and_cross_clinic_resources_are_indistinguishable(client):
    headers = {"X-User-Id": fixture.USER_CLINICIAN_B_ID}
    unknown = client.get("/api/patients/pat_does_not_exist", headers=headers)
    cross = client.get(f"/api/patients/{fixture.PATIENT_ID}", headers=headers)
    assert unknown.status_code == cross.status_code == 404
    assert unknown.json() == cross.json()


def test_cross_clinic_artifact_type_cannot_be_probed(client):
    headers = {"X-User-Id": fixture.USER_CLINICIAN_B_ID}
    payload = {"content": {"x": "y"}, "expected_version": 1}
    unknown = client.patch("/api/artifacts/art_does_not_exist", headers=headers, json=payload)
    noneditable = client.patch(
        f"/api/artifacts/{fixture.ART_DOC_SUMMARY}", headers=headers, json=payload
    )
    editable = client.patch(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}", headers=headers, json=payload
    )
    assert unknown.status_code == noneditable.status_code == editable.status_code == 404
    assert unknown.json() == noneditable.json() == editable.json()
