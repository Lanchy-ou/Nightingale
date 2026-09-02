from __future__ import annotations

from app.pairwise_ranking import shadow_rank_decisions
from app.models import RankingDecision, RankingRun
from sqlalchemy import select
from seed import fixture


def test_sl2_shadow_changes_only_eligible_unprotected_items_within_band(db_session):
    run = db_session.scalar(
        select(RankingRun)
        .where(
            RankingRun.patient_id == fixture.PATIENT_ID,
            RankingRun.viewer_role == "clinician",
        )
        .order_by(RankingRun.evaluated_at.desc(), RankingRun.run_id.desc())
    )
    decisions = db_session.scalars(
        select(RankingDecision).where(RankingDecision.run_id == run.run_id)
    ).all()
    result = shadow_rank_decisions(decisions, viewer_role="clinician")
    assert result.fallback_reason is None
    assert set(result.ranks) == {
        row.decision_id for row in decisions if row.eligible
    }
    assert all(
        result.priority_bands[row.decision_id] == row.priority_band
        for row in decisions
    )
    for row in decisions:
        if not row.eligible or (row.factor_snapshot or {}).get("hard_protected"):
            assert result.scores.get(row.decision_id, row.base_score) == row.base_score


def test_artifact_hash_mismatch_falls_back_atomically(db_session):
    run = db_session.scalar(select(RankingRun).where(RankingRun.viewer_role == "staff"))
    decisions = db_session.scalars(
        select(RankingDecision).where(RankingDecision.run_id == run.run_id)
    ).all()
    result = shadow_rank_decisions(
        decisions,
        viewer_role="staff",
        artifact_override={"artifact_sha256": "0" * 64},
    )
    assert result.fallback_reason == "artifact_hash_mismatch"
    assert all(result.scores[row.decision_id] == row.base_score for row in decisions if row.eligible)
