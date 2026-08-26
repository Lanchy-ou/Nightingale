"""M1 smoke test 2: every AI summary's provenance_pointer resolves to a real
event + artifact + span locator."""
from __future__ import annotations

from app.models import Artifact, Event
from seed import fixture

AI_SUMMARIES = [
    fixture.ART_PRE_SUMMARY,
    fixture.ART_NURSE_SUMMARY,
    fixture.ART_DOC_SUMMARY,
    fixture.ART_FU_SUMMARY,
]

VALID_KINDS = {"segment", "message", "paragraph", "timestamp_range", "section"}


def test_every_ai_summary_has_provenance(db_session):
    for aid in AI_SUMMARIES:
        a = db_session.get(Artifact, aid)
        assert a.provenance_pointer is not None, f"{aid} missing provenance_pointer"
        pp = a.provenance_pointer
        assert {"event_id", "artifact_id", "span"} <= set(pp)


def test_provenance_resolves_to_existing_event_and_artifact(db_session):
    for aid in AI_SUMMARIES:
        a = db_session.get(Artifact, aid)
        pp = a.provenance_pointer
        assert db_session.get(Event, pp["event_id"]) is not None
        src = db_session.get(Artifact, pp["artifact_id"])
        assert src is not None
        assert pp["span"]["kind"] in VALID_KINDS


def test_span_locator_resolves_within_source_artifact(db_session):
    for aid in AI_SUMMARIES:
        a = db_session.get(Artifact, aid)
        pp = a.provenance_pointer
        src = db_session.get(Artifact, pp["artifact_id"])
        span = pp["span"]
        if span["kind"] == "segment":
            segs = src.content.get("segments", [])
            assert any(s.get("index") == span["index"] for s in segs)
        elif span["kind"] == "message":
            msgs = src.content.get("messages", [])
            assert 1 <= span["index"] <= len(msgs)


def test_ai_summary_span_quotes_source_sentence(db_session):
    # The pre-consult summary points at msg_1, the canonical source sentence.
    a = db_session.get(Artifact, fixture.ART_PRE_SUMMARY)
    pp = a.provenance_pointer
    src = db_session.get(Artifact, pp["artifact_id"])
    msg = src.content["messages"][pp["span"]["index"] - 1]
    assert "once a week" in msg["text"] and "almost every day" in msg["text"]
