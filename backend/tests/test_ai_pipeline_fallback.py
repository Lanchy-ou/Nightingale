"""M4: pipeline fallback triggers + raw preservation (fixture-independent)."""
from __future__ import annotations

from datetime import datetime

from app.ai_pipeline import persist_derived, run_pipeline
from app.extraction import AISummaryResult, Candidate
from app.llm_client import (
    InvalidOutputError,
    ProviderProtocolError,
    ProviderUnavailableError,
)
from app.models import Artifact, Event


def _mk_source(db, event_type="doctor_consult", content=None, patient_id="pat_001"):
    evt = Event(
        event_id="evt_test_fb",
        patient_id=patient_id,
        clinic_id="clinic_001",
        event_type=event_type,
        started_at=datetime(2026, 8, 26, 10, 0),
        ended_at=datetime(2026, 8, 26, 10, 30),
        created_at=datetime(2026, 8, 26, 10, 31),
    )
    art = Artifact(
        artifact_id="art_test_fb",
        event_id="evt_test_fb",
        artifact_type="transcript",
        author_role="system",
        author_id=None,
        content=content
        or {"segments": [{"index": 1, "speaker": "doctor", "text": "Your headache is worse and BP is elevated."}]},
        created_at=datetime(2026, 8, 26, 10, 32),
        version=1,
        provenance_pointer=None,
    )
    db.add(evt)
    db.add(art)
    db.commit()
    return db.get(Event, "evt_test_fb"), db.get(Artifact, "art_test_fb")


class _FailingClient:
    def __init__(self, exc):
        self._exc = exc

    def summarize(self, redacted, flow_type):
        raise self._exc


class _FixedClient:
    def __init__(self, result):
        self._result = result

    def summarize(self, redacted, flow_type):
        return self._result


def test_provider_missing_falls_back(db_session):
    evt, art = _mk_source(db_session)
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FailingClient(ProviderUnavailableError("no key")), "deepseek",
    )
    assert out.method == "deterministic_fallback"
    assert out.degraded is True
    assert out.fallback_reason == "provider_missing"
    assert out.summary_content["summary"]


def test_provider_error_falls_back(db_session):
    evt, art = _mk_source(db_session)
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FailingClient(ProviderProtocolError("blocked")), "deepseek",
    )
    assert out.fallback_reason == "provider_error"


def test_invalid_output_falls_back(db_session):
    evt, art = _mk_source(db_session)
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FailingClient(InvalidOutputError("schema invalid")), "deepseek",
    )
    assert out.fallback_reason == "invalid_output"


def test_placeholder_error_falls_back(db_session):
    evt, art = _mk_source(db_session)
    bad = AISummaryResult(summary="saw [NAME_99] unresolved", candidates=[])
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FixedClient(bad), "mock",
    )
    assert out.fallback_reason == "placeholder_error"


def test_placeholder_error_in_candidate_field_falls_back(db_session):
    evt, art = _mk_source(db_session)
    bad = AISummaryResult(
        summary="ok",
        candidates=[
            Candidate(
                text="Saw [NAME_99]",
                quote="Your headache is worse and BP is elevated.",
                risk_reason="risk",
                entity_type="risk",
            )
        ],
    )
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FixedClient(bad), "mock",
    )
    assert out.fallback_reason == "placeholder_error"


def test_anchor_drop_rate_falls_back(db_session):
    evt, art = _mk_source(db_session)
    bad = AISummaryResult(
        summary="ok",
        candidates=[
            Candidate(text="a", quote="not in source 1", risk_reason="r", entity_type="risk"),
            Candidate(text="b", quote="not in source 2", risk_reason="r", entity_type="risk"),
            Candidate(text="c", quote="not in source 3", risk_reason="r", entity_type="risk"),
        ],
    )
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FixedClient(bad), "mock",
    )
    assert out.fallback_reason == "anchor_drop_rate"


def test_unsupported_source_allows_zero_highlights(db_session):
    evt, art = _mk_source(
        db_session,
        content={"segments": [{"index": 1, "speaker": "doctor", "text": "Everything looks normal."}]},
    )
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FailingClient(ProviderUnavailableError("no key")), "deepseek",
    )
    assert out.degraded is True
    assert out.candidates == []  # no fabricated candidates
    # raw artifact content is untouched by the pipeline
    assert art.content["segments"][0]["text"] == "Everything looks normal."


def test_derived_write_failure_rolls_back_and_preserves_raw(db_session, monkeypatch):
    evt, art = _mk_source(db_session)
    out = run_pipeline(
        db_session, evt, art, "ai_doctor_consult_summary", datetime(2026, 8, 26, 12, 0),
        _FailingClient(ProviderUnavailableError("no key")), "deepseek",
    )
    real_commit = db_session.commit

    def fail_after_flush():
        db_session.flush()
        raise RuntimeError("simulated derived commit failure")

    monkeypatch.setattr(db_session, "commit", fail_after_flush)
    import pytest

    with pytest.raises(RuntimeError, match="simulated derived commit failure"):
        persist_derived(
            db_session,
            evt,
            art,
            "ai_doctor_consult_summary",
            out,
            "usr_clinician_01",
            "clinician",
            None,
            None,
        )

    monkeypatch.setattr(db_session, "commit", real_commit)
    from app.api.sources import _derive_summary_id

    assert db_session.get(Artifact, art.artifact_id) is not None
    assert db_session.get(
        Artifact, _derive_summary_id(art.artifact_id, "ai_doctor_consult_summary")
    ) is None
