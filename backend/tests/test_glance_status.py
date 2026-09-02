"""Glance API + highlight status interactions (M2 tests, M3-authorized)."""
from __future__ import annotations

import pytest

from seed import fixture
from seed.seed import seed


@pytest.fixture(autouse=True)
def _fresh_state(db_session):
    # Re-seed before each test so status mutations don't leak across tests.
    seed(db_session)
    yield


def test_glance_returns_top_5_sorted_desc(clinician_client):
    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    assert r.status_code == 200
    hs = r.json()["highlights"]
    assert len(hs) == 5
    bands = [h["glance_explanation"]["priority_band"] for h in hs]
    assert bands == sorted(bands)
    ids = {h["highlight_id"] for h in hs}
    assert "hl_medication_existing" not in ids


def test_glance_excludes_rejected(clinician_client):
    clinician_client.post("/api/highlights/hl_blood_test_pending/status", json={"status": "rejected"})
    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    ids = {h["highlight_id"] for h in r.json()["highlights"]}
    assert "hl_blood_test_pending" not in ids


def test_status_legal_transition_records_history(clinician_client):
    r = clinician_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "accepted"})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "accepted"
    assert body["status_history"][-1]["from"] == "suggested"
    assert body["status_history"][-1]["to"] == "accepted"


def test_status_invalid_value_422(clinician_client):
    r = clinician_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "banana"})
    assert r.status_code == 422


def test_status_illegal_transition_422(clinician_client):
    clinician_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "rejected"})
    r = clinician_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "pinned"})
    assert r.status_code == 422


def test_provenance_endpoint_returns_full_chain(clinician_client):
    r = clinician_client.get("/api/highlights/hl_headache_worsening/provenance")
    assert r.status_code == 200
    body = r.json()
    assert body["event"]["event_id"] == fixture.EVT_PRE_0820
    assert body["summary_artifact"]["artifact_type"] == "ai_patient_session_summary"
    assert body["summary_artifact"]["author_role"] == "system"
    assert body["source_artifact"]["artifact_id"] == fixture.ART_PRE_RAW
    assert body["quote"] == "My headaches used to happen once a week, but now they're almost every day."
