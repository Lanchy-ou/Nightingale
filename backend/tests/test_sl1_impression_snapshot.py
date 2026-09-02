from __future__ import annotations

from datetime import datetime
import json

from sqlalchemy import select

from app.glance_projection import rebuild_glance_projections
from app.models import GlanceProjection, RankingDecision, RankingRun
from seed import fixture


def test_impression_captures_complete_candidate_set_and_v1_snapshot(db_session):
    as_of = datetime(2026, 9, 2, 12, 0)
    rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=as_of)
    db_session.flush()
    run = db_session.scalar(
        select(RankingRun).where(
            RankingRun.patient_id == fixture.PATIENT_ID,
            RankingRun.viewer_role == "clinician",
        ).order_by(RankingRun.evaluated_at.desc(), RankingRun.run_id.desc())
    )
    decisions = db_session.scalars(
        select(RankingDecision).where(RankingDecision.run_id == run.run_id)
    ).all()
    projections = db_session.scalars(
        select(GlanceProjection).where(
            GlanceProjection.patient_id == fixture.PATIENT_ID,
            GlanceProjection.viewer_role == "clinician",
        )
    ).all()
    assert len(decisions) == len(projections)
    assert all(row.factor_snapshot["schema_version"] == "attention-feature-v1" for row in decisions)
    assert any(row.eligible and not row.surfaced_base for row in decisions)
    assert any(not row.eligible for row in decisions)
    serialized = json.dumps([row.factor_snapshot for row in decisions], sort_keys=True)
    for sentinel in (
        "Headaches changed from weekly to near-daily",
        "Morning nausea persists",
        "Complete the blood test",
    ):
        assert sentinel not in serialized


def test_identical_as_of_reuses_the_same_impression_fingerprint(db_session):
    as_of = datetime(2026, 9, 2, 12, 0)
    rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=as_of)
    first = db_session.scalars(
        select(RankingRun).where(RankingRun.patient_id == fixture.PATIENT_ID)
    ).all()
    fingerprints = {(row.viewer_role, row.state_fingerprint) for row in first}
    rebuild_glance_projections(db_session, fixture.PATIENT_ID, as_of=as_of)
    second = db_session.scalars(
        select(RankingRun).where(RankingRun.patient_id == fixture.PATIENT_ID)
    ).all()
    assert {(row.viewer_role, row.state_fingerprint) for row in second} == fingerprints
    assert len(second) == len(first)
