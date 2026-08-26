"""M5: longitudinal scoring — repeated_mentions, recency, unresolved_task."""
from __future__ import annotations

from sqlalchemy import select

from app.highlights import extract_text, locate_span
from app.models import Artifact, Highlight
from seed import fixture
from seed.highlights import group_repeated_entity_keys


def _hl(db, hid: str) -> Highlight:
    return db.get(Highlight, hid)


def test_repeated_mentions_blood_test_both_sides(db_session):
    pending = _hl(db_session, "hl_blood_test_pending")
    review = _hl(db_session, "hl_blood_test_review")
    assert pending.feature_flags["repeated_mentions"] is True
    assert review.feature_flags["repeated_mentions"] is True
    # both sides recomputed: recency 2 + repeated_mentions 1
    assert pending.importance_score == 3
    assert review.importance_score == 3


def test_repeated_mentions_headache_frequency_across_events(db_session):
    once = _hl(db_session, "hl_headache_once_weekly")
    feb = _hl(db_session, "hl_headache_frequency_feb")
    worsening = _hl(db_session, "hl_headache_worsening")
    for h in (once, feb, worsening):
        assert h.feature_flags["repeated_mentions"] is True
    # historical ones stay low-score; the current worsening item gets the boost
    assert once.importance_score == 1  # repeated_mentions only
    assert worsening.importance_score == 6  # recency 2 + symptom_change 3 + repeated 1


def test_group_repeated_requires_two_distinct_events():
    assert group_repeated_entity_keys([("task:x", "e1"), ("task:x", "e2")]) == {"task:x"}
    assert group_repeated_entity_keys([("task:x", "e1")]) == set()
    # same event twice does NOT trigger repeated_mentions
    assert group_repeated_entity_keys([("task:x", "e1"), ("task:x", "e1")]) == set()


def test_recency_computed_from_as_of(db_session):
    recent = {
        "hl_headache_worsening",  # 08-20
        "hl_bp_elevated",  # 08-21
        "hl_blood_test_pending",  # 08-21
        "hl_followup_scheduled",  # 08-21
        "hl_nausea_persists",  # 08-24
        "hl_blood_test_review",  # 08-26
    }
    old = {"hl_headache_once_weekly", "hl_headache_frequency_feb", "hl_medication_existing"}
    for hid in recent:
        assert _hl(db_session, hid).feature_flags["recency"] is True, hid
    for hid in old:
        assert _hl(db_session, hid).feature_flags["recency"] is False, hid


def test_all_seed_highlights_unresolved_task_false(db_session):
    for h in db_session.scalars(select(Highlight)).all():
        assert h.feature_flags["unresolved_task"] is False


def test_seed_highlight_provenance_resolves(db_session):
    for h in db_session.scalars(select(Highlight)).all():
        src = db_session.get(Artifact, h.source_artifact_id)
        assert src is not None, h.highlight_id
        quote = extract_text(src.content, h.source_span)
        assert quote is not None, h.highlight_id
        assert locate_span(src.content, quote) is not None, h.highlight_id


def test_glance_prioritizes_current_episode(clinician_client):
    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    assert r.status_code == 200
    hs = r.json()["highlights"]
    assert len(hs) == 5
    scores = [h["importance_score"] for h in hs]
    assert scores == sorted(scores, reverse=True)
    # current-episode high-value items occupy the top; historical low-value items truncated
    top_ids = {h["highlight_id"] for h in hs}
    assert "hl_headache_worsening" in top_ids
    assert "hl_medication_existing" not in top_ids
    assert "hl_headache_once_weekly" not in top_ids
