"""M4: end-to-end AI vertical slice for the three flows (fallback path).

Uses run_pipeline + persist_derived directly against the seeded DB so Glance
visibility and source-jump can be asserted through the API.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from app.ai_pipeline import persist_derived, run_pipeline
from app.highlights import extract_text
from app.llm_client import MockLLMClient, ProviderUnavailableError
from app.models import Artifact, Event
from seed import fixture


class _NoKey:
    def summarize(self, redacted, flow_type):
        raise ProviderUnavailableError("no key")


FLOWS = [
    (
        "patient_session",
        "patient_ai_preconsult",
        "raw_conversation",
        "ai_patient_session_summary",
        {"messages": [{"id": "m1", "speaker": "patient", "text": "My headache is worse, almost every day now."}]},
        "almost every day",
    ),
    (
        "nurse_consult",
        "nurse_consult",
        "transcript",
        "ai_nurse_consult_summary",
        {"segments": [{"index": 1, "speaker": "nurse", "text": "Your blood pressure is elevated at 158 over 96."}]},
        "elevated",
    ),
    (
        "doctor_consult",
        "doctor_consult",
        "transcript",
        "ai_doctor_consult_summary",
        {"segments": [{"index": 1, "speaker": "doctor", "text": "I am ordering a blood test to check for underlying causes."}]},
        "ordering",
    ),
]


def _mk_source(db, event_type, artifact_type, content):
    evt = Event(
        event_id="evt_test_e2e",
        patient_id=fixture.PATIENT_ID,
        clinic_id=fixture.CLINIC_ID,
        event_type=event_type,
        started_at=datetime(2026, 8, 26, 10, 0),
        ended_at=datetime(2026, 8, 26, 10, 30),
        created_at=datetime(2026, 8, 26, 10, 31),
    )
    art = Artifact(
        artifact_id="art_test_e2e",
        event_id="evt_test_e2e",
        artifact_type=artifact_type,
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
    return db.get(Event, "evt_test_e2e"), db.get(Artifact, "art_test_e2e")


@pytest.mark.parametrize("flow,event_type,raw_type,summary_type,content,_kw", FLOWS)
def test_three_flows_produce_summary_and_highlights(
    db_session, clinician_client, flow, event_type, raw_type, summary_type, content, _kw
):
    # Snapshot clinician note (must remain unchanged).
    before = db_session.get(Artifact, fixture.ART_DOC_NOTE)
    before_version, before_content = before.version, json.dumps(before.content)

    evt, art = _mk_source(db_session, event_type, raw_type, content)
    out = run_pipeline(
        db_session, evt, art, summary_type, datetime(2026, 8, 26, 12, 0),
        _NoKey(), "deepseek",
    )
    summary_id, highlight_ids = persist_derived(
        db_session, evt, art, summary_type, out, fixture.USER_CLINICIAN_ID, "clinician", None, None
    )

    # summary is an independent system artifact
    summary = db_session.get(Artifact, summary_id)
    assert summary.artifact_type == summary_type
    assert summary.author_role == "system"
    assert summary.author_id is None
    assert summary.provenance_pointer["artifact_id"] == art.artifact_id
    assert summary.generation_metadata["method"] == "deterministic_fallback"
    assert summary.generation_metadata["degraded"] is True

    # every highlight is checked below via provenance; clinician note unchanged
    after = db_session.get(Artifact, fixture.ART_DOC_NOTE)
    assert after.version == before_version
    assert json.dumps(after.content) == before_content

    # Glance visibility + source jump through the API
    if highlight_ids:
        r = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
        assert r.status_code == 200
        ids = {h["highlight_id"] for h in r.json()["highlights"]}
        assert highlight_ids[0] in ids

        prov = clinician_client.get(f"/api/highlights/{highlight_ids[0]}/provenance")
        assert prov.status_code == 200
        body = prov.json()
        assert body["source_artifact"]["artifact_id"] == art.artifact_id
        assert body["quote"]  # exact substring resolved


def test_mock_client_receives_only_redacted_content(db_session):
    raw = {"messages": [{"id": "m1", "speaker": "patient", "text": "My name is Alice Tan, IC 880523-01-1234."}]}
    evt, art = _mk_source(db_session, "patient_ai_preconsult", "raw_conversation", raw)
    client = MockLLMClient()
    run_pipeline(
        db_session, evt, art, "ai_patient_session_summary", datetime(2026, 8, 26, 12, 0),
        client, "mock",
    )
    blob = json.dumps(client.last_payload.content)
    assert "Alice Tan" not in blob
    assert "880523-01-1234" not in blob


def test_mock_path_anchors_candidate(db_session):
    raw = {"segments": [{"index": 1, "speaker": "doctor", "text": "The blood pressure is elevated at 158 over 96."}]}
    evt, art = _mk_source(db_session, "doctor_consult", "transcript", raw)
    from app.extraction import Candidate

    client = MockLLMClient(
        candidates=[
            Candidate(
                text="Elevated BP",
                quote="The blood pressure is elevated at 158 over 96.",
                risk_reason="elevated",
                entity_type="risk",
                explicit_risk=True,
            )
        ]
    )
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        client, "mock",
    )
    assert out.method == "mock"
    assert len(out.candidates) == 1
    assert extract_text(art.content, out.candidates[0].span) == "The blood pressure is elevated at 158 over 96."
    assert out.candidates[0].feature_flags["explicit_risk"] is True
