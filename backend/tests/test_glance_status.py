"""Glance API + highlight status interactions (M2 tests, M3-authorized)."""
from __future__ import annotations

import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, Highlight

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


@pytest.mark.parametrize("status", ["accepted", "pinned"])
def test_clinician_confirms_staff_review_without_duplicate_status_transition(
    staff_client, clinician_client, db_session, status,
):
    path = "/api/highlights/hl_bp_elevated/status"
    staff = staff_client.post(path, json={"status": status})
    assert staff.status_code == 200
    assert not staff.json()["feature_flags"]["clinician_confirmed"]

    clinician = clinician_client.post(path, json={"status": status})
    assert clinician.status_code == 200
    assert clinician.json()["feature_flags"]["clinician_confirmed"] is True
    assert len(clinician.json()["status_history"]) == 1
    audits = db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == "hl_bp_elevated", AuditLog.action == "highlight_status",
    )).all()
    assert {audit.actor_role for audit in audits} == {"staff", "clinician"}
    assert len(audits) == 2

    retry = clinician_client.post(path, json={"status": status})
    assert retry.status_code == 200
    assert retry.json()["feature_flags"]["clinician_confirmed"] is True
    assert len(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == "hl_bp_elevated", AuditLog.action == "highlight_status",
    )).all()) == 2

    staff_retry = staff_client.post(path, json={"status": status})
    assert staff_retry.json()["feature_flags"]["clinician_confirmed"] is True


@pytest.mark.parametrize("status", ["accepted", "pinned"])
def test_concurrent_clinician_confirmation_after_staff_is_audited_once(
    staff_client, db_session, status,
):
    path = "/api/highlights/hl_bp_elevated/status"
    assert staff_client.post(path, json={"status": status}).status_code == 200
    barrier = Barrier(2)

    def confirm():
        with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as client:
            barrier.wait()
            return client.post(path, json={"status": status}).status_code

    with ThreadPoolExecutor(max_workers=2) as pool:
        codes = sorted(pool.map(lambda _: confirm(), range(2)))
    assert codes[0] == 200
    assert codes[1] in (200, 409)
    db_session.expire_all()
    highlight = db_session.get(Highlight, "hl_bp_elevated")
    assert highlight.feature_flags["clinician_confirmed"] is True
    assert len(highlight.status_history) == 1
    audits = db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == highlight.highlight_id,
        AuditLog.action == "highlight_status", AuditLog.actor_role == "clinician",
    )).all()
    assert len(audits) == 1
