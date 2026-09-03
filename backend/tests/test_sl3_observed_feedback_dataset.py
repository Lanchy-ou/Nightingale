from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timedelta

from sqlalchemy import select

from app.models import LearningSignal, RankingDecision, RankingRun
from app.observed_feedback import compile_observed_feedback_dataset
from seed import fixture


def _label(db_session, decision: RankingDecision, actor_id: str, grade: int, offset: int):
    db_session.add(
        LearningSignal(
            signal_id=f"lsg_sl3_{decision.decision_id}_{actor_id}_{offset}",
            decision_id=decision.decision_id,
            clinic_id=fixture.CLINIC_ID,
            actor_id=actor_id,
            actor_role="clinician",
            signal_type="outcome_label",
            reason_code="attention_label_v1",
            feedback_key=decision.feedback_key,
            signal_value=grade,
            eligible_for_shadow=False,
            ineligibility_reason="evaluation_label_only",
            independence_key=(decision.factor_snapshot or {}).get(
                "independence_key", f"decision:{decision.decision_id}"
            ),
            policy_version="sl2-pairwise-linear-v1",
            supersedes_signal_id=None,
            created_at=datetime(2026, 9, 3, 9, 0) + timedelta(seconds=offset),
        )
    )


def _pairable_decisions(db_session) -> list[RankingDecision]:
    runs = db_session.scalars(
        select(RankingRun)
        .where(
            RankingRun.clinic_id == fixture.CLINIC_ID,
            RankingRun.viewer_role == "clinician",
        )
        .order_by(RankingRun.evaluated_at.desc(), RankingRun.run_id.desc())
    ).all()
    for run in runs:
        eligible = list(
            db_session.scalars(
                select(RankingDecision).where(
                    RankingDecision.run_id == run.run_id,
                    RankingDecision.eligible.is_(True),
                )
            ).all()
        )
        eligible = [
            row
            for row in eligible
            if not (row.factor_snapshot or {}).get("hard_protected")
            and not (row.factor_snapshot or {}).get("negative_protected")
        ]
        if not eligible:
            continue
        band = Counter(row.priority_band for row in eligible).most_common(1)[0][0]
        decisions = [row for row in eligible if row.priority_band == band]
        if len(decisions) >= 2:
            return decisions[:2]
    raise AssertionError("seed must expose two pairable clinician decisions")


def test_compiler_automatically_builds_content_free_same_context_pair(db_session):
    decisions = _pairable_decisions(db_session)
    _label(db_session, decisions[0], fixture.USER_CLINICIAN_ID, 3, 1)
    _label(db_session, decisions[1], fixture.USER_CLINICIAN_ID, 1, 2)
    db_session.flush()

    dataset = compile_observed_feedback_dataset(
        db_session, clinic_id=fixture.CLINIC_ID, viewer_role="clinician"
    )

    assert len(dataset.pairs) == 1
    assert dataset.pairs[0].label_kind == "strict"
    assert len(dataset.pairs[0].left_vector) == 18
    serialized = json.dumps(dataset.to_document(), sort_keys=True)
    for forbidden in (
        fixture.CLINIC_ID,
        fixture.PATIENT_ID,
        fixture.USER_CLINICIAN_ID,
        decisions[0].decision_id,
        decisions[0].highlight_id,
        "Blood pressure",
    ):
        assert forbidden not in serialized


def test_compilation_is_deterministic_and_clinic_scoped(db_session):
    first = compile_observed_feedback_dataset(
        db_session, clinic_id=fixture.CLINIC_ID, viewer_role="clinician"
    )
    second = compile_observed_feedback_dataset(
        db_session, clinic_id=fixture.CLINIC_ID, viewer_role="clinician"
    )
    assert first.to_document() == second.to_document()
    assert first.manifest_sha256 == second.manifest_sha256


def test_cross_band_labels_never_become_training_pair(db_session):
    decisions = _pairable_decisions(db_session)
    decisions[1].priority_band = decisions[0].priority_band + 1
    _label(db_session, decisions[0], fixture.USER_CLINICIAN_ID, 3, 1)
    _label(db_session, decisions[1], fixture.USER_CLINICIAN_ID, 1, 2)
    db_session.flush()
    dataset = compile_observed_feedback_dataset(
        db_session, clinic_id=fixture.CLINIC_ID, viewer_role="clinician"
    )
    assert dataset.pairs == ()
    assert dataset.excluded_counts["unpaired_label"] == 2


def test_wrong_role_protected_and_invalid_source_labels_fail_closed(db_session):
    decisions = _pairable_decisions(db_session)
    protected = dict(decisions[0].factor_snapshot or {})
    protected["hard_protected"] = True
    decisions[0].factor_snapshot = protected
    decisions[1].source_binding_status = "hash_mismatch"
    _label(db_session, decisions[0], fixture.USER_CLINICIAN_ID, 3, 1)
    _label(db_session, decisions[1], fixture.USER_CLINICIAN_ID, 1, 2)
    _label(db_session, decisions[1], fixture.USER_STAFF_ID, 2, 3)
    db_session.flush()
    dataset = compile_observed_feedback_dataset(
        db_session, clinic_id=fixture.CLINIC_ID, viewer_role="clinician"
    )
    assert dataset.pairs == ()
    assert dataset.excluded_counts["hard_protected"] == 1
    assert dataset.excluded_counts["source_binding_invalid"] == 1
    assert dataset.excluded_counts["actor_scope_or_role_mismatch"] == 1
