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
    fixture.ART_MAYA_PRE_SUMMARY,
    fixture.ART_MAYA_DOCTOR_SUMMARY,
    fixture.ART_DANIEL_LATEST_SUMMARY,
    fixture.ART_LEAH_PRE_SUMMARY,
}


def test_all_candidates_become_highlights(db_session):
    highlights = db_session.scalars(select(Highlight)).all()
    # All canonical candidates have exact source quotes and become highlights.
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
        assert h.source_artifact_version == 1
        assert len(h.source_quote_sha256) == 64


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
    expected = sum(
        candidate["artifact_id"] in AI_SUMMARY_IDS
        for candidate in fixture.HIGHLIGHT_CANDIDATES
    )
    assert len(ai_highlights) == expected == 10
    for h in ai_highlights:
        derived = db_session.get(Artifact, h.artifact_id)
        assert derived.author_role == "system"
        src = db_session.get(Artifact, h.source_artifact_id)
        assert extract_text(src.content, h.source_span) is not None


def test_provenance_stays_bound_to_original_version_after_source_edit(
    clinician_client,
):
    before = clinician_client.get(
        "/api/highlights/hl_medication_existing/provenance"
    )
    assert before.status_code == 200
    assert before.json()["quote"] == "Start propranolol 20 mg daily"
    assert before.json()["binding_status"] == "current"

    edited = clinician_client.patch(
        f"/api/artifacts/{fixture.ART_HIST_2026_NOTE}",
        json={
            "content": {"assessment": "No known allergies recorded."},
            "expected_version": 1,
        },
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["version"] == 2

    after = clinician_client.get(
        "/api/highlights/hl_medication_existing/provenance"
    )
    assert after.status_code == 200
    body = after.json()
    assert body["quote"] == "Start propranolol 20 mg daily"
    assert body["source_artifact"]["version"] == 1
    assert body["source_changed"] is True
    assert body["bound_source_version"] == 1
    assert body["current_source_version"] == 2
    assert body["binding_status"] == "historical"


def test_provenance_hash_mismatch_fails_closed(
    clinician_client, db_session
):
    highlight = db_session.get(Highlight, "hl_medication_existing")
    highlight.source_quote_sha256 = "0" * 64
    db_session.commit()

    response = clinician_client.get(
        "/api/highlights/hl_medication_existing/provenance"
    )
    assert response.status_code == 200
    assert response.json()["quote"] is None
    assert response.json()["binding_status"] == "hash_mismatch"
