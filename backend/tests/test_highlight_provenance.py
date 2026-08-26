"""Required test: every highlight has a provenance_pointer that resolves hop by
hop to a real event/artifact/span, including AI-scribed highlights."""
from __future__ import annotations

from sqlalchemy import select

from app.highlights import extract_text, locate_span
from app.models import Artifact, Event, Highlight
from seed import fixture

AI_SUMMARY_IDS = {
    fixture.ART_PRE_SUMMARY,
    fixture.ART_NURSE_SUMMARY,
    fixture.ART_DOC_SUMMARY,
    fixture.ART_FU_SUMMARY,
}


def test_all_candidates_become_highlights(db_session):
    highlights = db_session.scalars(select(Highlight)).all()
    # 6 candidates, all quotes must match their source => 6 highlights.
    assert len(highlights) == len(fixture.HIGHLIGHT_CANDIDATES)


def test_every_highlight_has_complete_provenance_pointer(db_session):
    for h in db_session.scalars(select(Highlight)).all():
        assert h.event_id
        assert h.artifact_id
        assert h.source_artifact_id
        assert h.source_span
        assert h.source_span.get("kind") in {
            "segment",
            "message",
            "paragraph",
            "timestamp_range",
            "section",
        }
        assert "index" in h.source_span


def test_provenance_resolves_hop_by_hop(db_session):
    for h in db_session.scalars(select(Highlight)).all():
        assert db_session.get(Event, h.event_id) is not None, f"dangling event {h.event_id}"
        assert db_session.get(Artifact, h.artifact_id) is not None, f"dangling artifact {h.artifact_id}"
        assert db_session.get(Artifact, h.source_artifact_id) is not None, f"dangling source {h.source_artifact_id}"


def test_span_resolves_to_real_source_substring(db_session):
    for h in db_session.scalars(select(Highlight)).all():
        src = db_session.get(Artifact, h.source_artifact_id)
        quote = extract_text(src.content, h.source_span)
        assert quote is not None, f"{h.highlight_id}: span does not resolve"
        # The resolved quote must actually exist inside the source content.
        assert locate_span(src.content, quote) is not None, f"{h.highlight_id}: quote not in source"


def test_ai_scribed_highlights_satisfy_same_rules(db_session):
    ai_highlights = [
        h
        for h in db_session.scalars(select(Highlight)).all()
        if h.artifact_id in AI_SUMMARY_IDS
    ]
    assert len(ai_highlights) == 5  # 5 of 6 highlights derive from an AI summary
    for h in ai_highlights:
        derived = db_session.get(Artifact, h.artifact_id)
        assert derived.author_role == "system"
        src = db_session.get(Artifact, h.source_artifact_id)
        assert extract_text(src.content, h.source_span) is not None
