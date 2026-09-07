"""M4: bounded clinician-authority conflict + clinician-confirmed scoring."""
from __future__ import annotations

import json
from datetime import datetime

from app.ai_pipeline import persist_derived, run_pipeline
from app.extraction import Candidate
from app.llm_client import MockLLMClient
from app.models import Artifact, Event, Highlight
from seed import fixture


def _mk_source(db, content):
    evt = Event(
        event_id="evt_test_conf",
        patient_id=fixture.PATIENT_ID,
        clinic_id=fixture.CLINIC_ID,
        event_type="doctor_consult",
        started_at=datetime(2026, 8, 26, 10, 0),
        ended_at=datetime(2026, 8, 26, 10, 30),
        created_at=datetime(2026, 8, 26, 10, 31),
    )
    art = Artifact(
        artifact_id="art_test_conf",
        event_id="evt_test_conf",
        artifact_type="transcript",
        author_role="system",
        author_id=None,
        content=content,
        created_at=datetime(2026, 8, 26, 10, 32),
        version=1,
        provenance_pointer=None,
    )
    db.add(evt)
    db.add(art)
    db.commit()
    return db.get(Event, "evt_test_conf"), db.get(Artifact, "art_test_conf")


def test_medication_dose_conflict_needs_review(db_session, clinician_client):
    before = db_session.get(Artifact, fixture.ART_DOC_NOTE)
    before_version, before_content = before.version, json.dumps(before.content)

    raw = {"segments": [{"index": 1, "speaker": "doctor", "text": "Increase propranolol to 40 mg daily."}]}
    evt, art = _mk_source(db_session, raw)
    client = MockLLMClient(
        candidates=[
            Candidate(
                text="propranolol",
                quote="Increase propranolol to 40 mg daily.",
                risk_reason="dose change",
                entity_type="medication",
                assertion_value="40 mg",
            )
        ]
    )
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        client, "mock",
    )
    summary_id, highlight_ids = persist_derived(
        db_session, evt, art, "ai_doctor_consult_summary", out,
        fixture.USER_CLINICIAN_ID, "clinician", None, None,
    )

    assert len(highlight_ids) == 1
    hl = db_session.get(Highlight, highlight_ids[0])
    assert hl.review_status == "needs_review"
    # Most recent clinician note with the conflicting dose wins.
    assert hl.conflict_with_artifact_id == fixture.ART_REVIEW_NOTE
    assert "conflicts with clinician-authored record" in hl.risk_reason

    # clinician note is NOT modified / versioned
    after = db_session.get(Artifact, fixture.ART_DOC_NOTE)
    assert after.version == before_version
    assert json.dumps(after.content) == before_content

    # provenance returns the conflict artifact for UI jump
    prov = clinician_client.get(f"/api/highlights/{highlight_ids[0]}/provenance")
    assert prov.status_code == 200
    assert prov.json()["conflict_artifact"]["artifact_id"] == fixture.ART_REVIEW_NOTE


def test_matching_value_is_not_a_conflict(db_session):
    raw = {"segments": [{"index": 1, "speaker": "doctor", "text": "Continue propranolol 20 mg daily."}]}
    evt, art = _mk_source(db_session, raw)
    client = MockLLMClient(
        candidates=[
            Candidate(
                text="propranolol",
                quote="Continue propranolol 20 mg daily.",
                risk_reason="medication",
                entity_type="medication",
                assertion_value="20 mg",
            )
        ]
    )
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        client, "mock",
    )
    assert len(out.candidates) == 1
    assert out.candidates[0].review_status is None
    assert out.candidates[0].conflict_with_artifact_id is None


def test_clinician_accept_sets_confirmed_and_rescores(clinician_client, db_session):
    # This assertion concerns a recent concern; keep its event within the
    # window instead of depending on the frozen August seed remaining recent.
    db_session.get(Event, fixture.EVT_NURSE_0821).started_at = datetime.now()
    db_session.commit()
    r = clinician_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "accepted"})
    assert r.status_code == 200
    body = r.json()
    assert body["feature_flags"]["clinician_confirmed"] is True
    assert body["importance_score"] == 7  # recency 2 + explicit_risk 3 + clinician_confirmed 2


def test_staff_accept_does_not_set_confirmed(staff_client, db_session):
    db_session.get(Event, fixture.EVT_NURSE_0821).started_at = datetime.now()
    db_session.commit()
    r = staff_client.post("/api/highlights/hl_bp_elevated/status", json={"status": "accepted"})
    assert r.status_code == 200
    body = r.json()
    assert body["feature_flags"]["clinician_confirmed"] is False
    assert body["importance_score"] == 5  # recency 2 + explicit_risk 3, unchanged
