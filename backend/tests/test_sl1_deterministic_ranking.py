from __future__ import annotations

from datetime import datetime
from dataclasses import replace

from app.attention_items import build_attention_items, rank_attention_items
from seed import fixture


def test_ranking_replay_has_exact_stable_order_and_base_only_score(db_session):
    as_of = datetime(2026, 9, 2, 12, 0)
    first = rank_attention_items(
        build_attention_items(
            db_session,
            patient_id=fixture.PATIENT_DENSE_ID,
            viewer_role="clinician",
            as_of=as_of,
        )
    )
    second = rank_attention_items(
        build_attention_items(
            db_session,
            patient_id=fixture.PATIENT_DENSE_ID,
            viewer_role="clinician",
            as_of=as_of,
        )
    )
    assert [item.candidate_id for item in first] == [item.candidate_id for item in second]
    assert all(item.adaptive_adjustment == 0 for item in first)
    assert all(
        item.final_score == item.base_importance_score + item.decay_adjustment
        for item in first
    )


def test_rank_key_uses_stable_identifier_as_final_tie_break(db_session):
    items = build_attention_items(
        db_session,
        patient_id=fixture.PATIENT_DENSE_ID,
        viewer_role="clinician",
        as_of=datetime(2026, 9, 2, 12, 0),
    )
    ordered = rank_attention_items(items)
    keys = [item.rank_key() for item in ordered]
    assert keys == sorted(keys)


def test_exact_tie_uses_highlight_id_as_the_final_stable_tie_break(db_session):
    base = next(
        item
        for item in build_attention_items(
            db_session,
            patient_id=fixture.PATIENT_ID,
            viewer_role="clinician",
            as_of=datetime(2026, 9, 2, 12, 0),
        )
        if item.eligible
    )
    later = replace(
        base,
        candidate_id="att_tie_z",
        source_id="highlight_z",
        highlight_id="highlight_z",
        independence_key="highlight:highlight_z",
    )
    earlier = replace(
        base,
        candidate_id="att_tie_a",
        source_id="highlight_a",
        highlight_id="highlight_a",
        independence_key="highlight:highlight_a",
    )
    assert [item.highlight_id for item in rank_attention_items([later, earlier])] == [
        "highlight_a",
        "highlight_z",
    ]
