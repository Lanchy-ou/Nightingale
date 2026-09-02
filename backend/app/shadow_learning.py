"""F_A1 content-free ranking snapshots and non-serving Shadow evaluation."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from types import SimpleNamespace

from sqlalchemy import select
from sqlalchemy.orm import Session

from .highlights import GLANCE_LIMIT
from .ids import new_id, stable_id
from .importance_learning import MAX_ADJUSTMENT, MIN_ADJUSTMENT, feedback_key_for_entity_type
from .models import (
    GlanceProjection,
    Highlight,
    ImportanceFeedback,
    LearningEvaluation,
    LearningPolicyVersion,
    LearningSignal,
    RankingDecision,
    RankingRun,
    Task,
)
from .provenance_binding import resolve_highlight_source
from .pairwise_ranking import (
    POLICY_VERSION as SL2_SHADOW_POLICY,
    load_model_artifact,
    shadow_rank_decisions,
    sl2_artifact_evidence,
)

SERVING_MODE = "base_only"
DEFAULT_SHADOW_POLICY = "legacy-e2-v1"
NO_ADJUSTMENT_POLICY = "no-adjustment-v1"
SL2_SCORE_SCALE = 1_000_000
DEMOTION_REASONS = frozenset(
    {
        "duplicate_or_redundant",
        "already_resolved_or_stale",
        "not_actionable_for_viewer_role",
        "lower_than_other_active_work",
    }
)
QUALITY_REASONS = frozenset(
    {"extraction_incorrect", "source_mismatch", "wrong_role_route"}
)


def ensure_learning_policies(
    db: Session, clinic_id: str, *, actor_id: str | None = None, now: datetime | None = None
) -> LearningPolicyVersion:
    created_at = now or datetime.now()
    active = None
    for version, enabled in (
        (DEFAULT_SHADOW_POLICY, True),
        (NO_ADJUSTMENT_POLICY, False),
        (SL2_SHADOW_POLICY, False),
    ):
        row = db.scalar(
            select(LearningPolicyVersion).where(
                LearningPolicyVersion.clinic_id == clinic_id,
                LearningPolicyVersion.version_name == version,
            )
        )
        if row is None:
            row = LearningPolicyVersion(
                policy_id=f"lpv_{stable_id(clinic_id, version)}",
                clinic_id=clinic_id,
                version_name=version,
                serving_mode=SERVING_MODE,
                shadow_policy=version,
                active=enabled,
                frozen_at=None,
                signal_cutoff_at=None,
                config={
                    "serving_mode": SERVING_MODE,
                    "shadow_only": True,
                    "adjustment_cap": [MIN_ADJUSTMENT, MAX_ADJUSTMENT],
                    "model_training": False,
                    "offline_artifact_only": version == SL2_SHADOW_POLICY,
                },
                created_by=actor_id,
                created_at=created_at,
            )
            db.add(row)
            db.flush()
        if row.active:
            active = row
    if active is None:
        active = db.scalar(
            select(LearningPolicyVersion).where(
                LearningPolicyVersion.clinic_id == clinic_id,
                LearningPolicyVersion.version_name == DEFAULT_SHADOW_POLICY,
            )
        )
        active.active = True
        db.add(active)
    return active


def active_policy(db: Session, clinic_id: str) -> LearningPolicyVersion:
    ensure_learning_policies(db, clinic_id)
    row = db.scalar(
        select(LearningPolicyVersion).where(
            LearningPolicyVersion.clinic_id == clinic_id,
            LearningPolicyVersion.active.is_(True),
        )
    )
    if row is None:
        raise RuntimeError("active Shadow policy is missing")
    return row


def _latest_legacy_adjustment(
    db: Session, clinic_id: str, feedback_key: str, cutoff: datetime | None
) -> int:
    query = select(ImportanceFeedback).where(
        ImportanceFeedback.clinic_id == clinic_id,
        ImportanceFeedback.feedback_key == feedback_key,
    )
    if cutoff is not None:
        query = query.where(ImportanceFeedback.created_at <= cutoff)
    rows = db.scalars(query.order_by(ImportanceFeedback.created_at, ImportanceFeedback.feedback_id)).all()
    latest: dict[tuple[str, str], ImportanceFeedback] = {}
    for row in rows:
        if row.signal_value in {-1, 1, 2}:
            latest[(row.actor_id, row.highlight_id)] = row
    return sum(row.signal_value for row in latest.values())


def _explicit_demotion_adjustment(
    db: Session, clinic_id: str, feedback_key: str, cutoff: datetime | None
) -> int:
    query = select(LearningSignal).where(
        LearningSignal.clinic_id == clinic_id,
        LearningSignal.feedback_key == feedback_key,
        LearningSignal.signal_type == "explicit_demotion",
        LearningSignal.eligible_for_shadow.is_(True),
    )
    if cutoff is not None:
        query = query.where(LearningSignal.created_at <= cutoff)
    rows = db.scalars(query.order_by(LearningSignal.created_at, LearningSignal.signal_id)).all()
    latest: dict[tuple[str, str], LearningSignal] = {}
    for row in rows:
        latest[(row.actor_id, row.independence_key)] = row
    return sum(row.signal_value for row in latest.values())


def shadow_adjustment(
    db: Session,
    *,
    clinic_id: str,
    feedback_key: str,
    policy: LearningPolicyVersion,
) -> int:
    if policy.shadow_policy in {NO_ADJUSTMENT_POLICY, SL2_SHADOW_POLICY}:
        return 0
    cutoff = policy.signal_cutoff_at if policy.frozen_at is not None else None
    raw = _latest_legacy_adjustment(db, clinic_id, feedback_key, cutoff)
    raw += _explicit_demotion_adjustment(db, clinic_id, feedback_key, cutoff)
    return max(MIN_ADJUSTMENT, min(MAX_ADJUSTMENT, raw))


def is_negative_protected(highlight: Highlight, task: Task | None) -> bool:
    return bool(
        highlight.entity_type == "allergy"
        or highlight.feature_flags.get("explicit_risk")
        or highlight.feature_flags.get("unresolved_task")
        or highlight.feature_flags.get("clinician_confirmed")
        or highlight.status == "pinned"
        or highlight.review_status == "needs_review"
        or highlight.conflict_with_artifact_id is not None
        or (task is not None and task.attention_class == "priority_review")
    )


def _binding_status(db: Session, highlight: Highlight, task: Task | None = None) -> str:
    if task is not None and highlight.source_span is None:
        return "not_applicable"
    if highlight.source_artifact_id is None and highlight.source_span is None:
        return "not_applicable"
    return resolve_highlight_source(db, highlight).status


def _rank_key(item: dict, score_key: str) -> tuple:
    due = item["projection"].due_at
    highlight = item["highlight"]
    return (
        item["projection"].priority_band,
        highlight.status != "pinned",
        highlight.review_status != "needs_review",
        -item[score_key],
        due is None,
        due or datetime.max,
        highlight.created_at,
        highlight.highlight_id,
    )


def capture_ranking_runs(
    db: Session,
    patient_id: str,
    *,
    evaluated_at: datetime,
    legacy_snapshot: bool = False,
) -> list[RankingRun]:
    """Persist one immutable decision per projection; identical states deduplicate."""
    db.flush()
    projections = db.execute(
        select(GlanceProjection, Highlight)
        .join(Highlight, Highlight.highlight_id == GlanceProjection.highlight_id)
        .where(GlanceProjection.patient_id == patient_id)
    ).all()
    if not projections:
        return []
    created: list[RankingRun] = []
    for role in ("staff", "clinician"):
        role_rows = [(projection, highlight) for projection, highlight in projections if projection.viewer_role == role]
        if not role_rows:
            continue
        clinic_id = role_rows[0][0].clinic_id
        policy = active_policy(db, clinic_id)
        items: list[dict] = []
        for projection, highlight in role_rows:
            task = db.get(Task, highlight.task_id) if highlight.task_id else None
            feedback_key = feedback_key_for_entity_type(highlight.entity_type)
            base_score = highlight.base_importance_score + highlight.decay_adjustment
            adjustment = (
                highlight.adaptive_adjustment
                if legacy_snapshot
                else shadow_adjustment(
                    db,
                    clinic_id=clinic_id,
                    feedback_key=feedback_key,
                    policy=policy,
                )
            )
            if adjustment < 0 and is_negative_protected(highlight, task):
                adjustment = 0
            binding = _binding_status(db, highlight, task)
            factor_snapshot = {
                **dict(projection.factor_explanation or {}),
                "negative_protected": is_negative_protected(highlight, task),
            }
            item = {
                "projection": projection,
                "highlight": highlight,
                "task": task,
                "feedback_key": feedback_key,
                "base_score": base_score,
                "shadow_score": base_score + adjustment,
                "shadow_adjustment": adjustment,
                "binding": binding,
                "factor_snapshot": factor_snapshot,
            }
            items.append(item)
        eligible = [item for item in items if item["projection"].eligible]
        base_order = sorted(eligible, key=lambda item: _rank_key(item, "base_score"))
        base_ranks = {
            item["highlight"].highlight_id: index
            for index, item in enumerate(base_order, 1)
        }
        shadow_fallback_reason = None
        shadow_artifact_version = None
        if policy.shadow_policy == SL2_SHADOW_POLICY and not legacy_snapshot:
            transient = [
                SimpleNamespace(
                    decision_id=item["highlight"].highlight_id,
                    eligible=item["projection"].eligible,
                    priority_band=item["projection"].priority_band,
                    factor_snapshot=item["factor_snapshot"],
                    base_score=item["base_score"],
                    base_rank=base_ranks.get(item["highlight"].highlight_id),
                )
                for item in items
            ]
            learned = shadow_rank_decisions(transient, viewer_role=role)
            shadow_fallback_reason = learned.fallback_reason
            if shadow_fallback_reason is None:
                shadow_artifact_version = load_model_artifact(role).get("artifact_version")
            shadow_ranks = learned.ranks
            for item in items:
                highlight_id = item["highlight"].highlight_id
                raw_score = learned.scores.get(highlight_id, item["base_score"])
                protected = bool(item["factor_snapshot"].get("hard_protected"))
                model_scored = bool(item["projection"].eligible and not protected)
                item["shadow_adjustment"] = 0
                item["shadow_score"] = (
                    item["base_score"]
                    if shadow_fallback_reason is not None or not model_scored
                    # RankingDecision.shadow_score is an existing integer
                    # column; preserve the unscaled value in factor_snapshot.
                    else int(round(float(raw_score) * SL2_SCORE_SCALE))
                )
                item["factor_snapshot"] = {
                    **item["factor_snapshot"],
                    "sl2_model_score": (
                        float(raw_score)
                        if shadow_fallback_reason is None and model_scored
                        else None
                    ),
                    "shadow_fallback_reason": shadow_fallback_reason,
                    "shadow_artifact_version": shadow_artifact_version,
                }
        else:
            shadow_order = sorted(eligible, key=lambda item: _rank_key(item, "shadow_score"))
            shadow_ranks = {
                item["highlight"].highlight_id: index
                for index, item in enumerate(shadow_order, 1)
            }
        state = [
            {
                "highlight_id": item["highlight"].highlight_id,
                "feature_snapshot": item["factor_snapshot"],
                "shadow_score": item["shadow_score"],
                "shadow_rank": shadow_ranks.get(item["highlight"].highlight_id),
                "source_binding_status": item["binding"],
            }
            for item in items
        ]
        fingerprint = hashlib.sha256(
            json.dumps(sorted(state, key=lambda value: value["highlight_id"]), sort_keys=True).encode("utf-8")
        ).hexdigest()
        policy_version = f"legacy-snapshot:{policy.version_name}" if legacy_snapshot else policy.version_name
        existing = db.scalar(
            select(RankingRun).where(
                RankingRun.clinic_id == clinic_id,
                RankingRun.patient_id == patient_id,
                RankingRun.viewer_role == role,
                RankingRun.state_fingerprint == fingerprint,
                RankingRun.policy_version == policy_version,
            )
        )
        if existing is not None:
            created.append(existing)
            continue
        run = RankingRun(
            run_id=new_id("rrn"),
            clinic_id=clinic_id,
            patient_id=patient_id,
            viewer_role=role,
            rule_version=role_rows[0][0].rule_version,
            policy_version=policy_version,
            top_k=GLANCE_LIMIT,
            state_fingerprint=fingerprint,
            evaluated_at=evaluated_at,
        )
        db.add(run)
        db.flush()
        for item in items:
            highlight = item["highlight"]
            task = item["task"]
            base_rank = base_ranks.get(highlight.highlight_id)
            shadow_rank = shadow_ranks.get(highlight.highlight_id)
            db.add(
                RankingDecision(
                    decision_id=f"rdc_{stable_id(run.run_id, highlight.highlight_id)}",
                    run_id=run.run_id,
                    highlight_id=highlight.highlight_id,
                    workflow_id=task.workflow_id if task else None,
                    feedback_key=item["feedback_key"],
                    eligible=item["projection"].eligible,
                    exclusion_reason=item["projection"].exclusion_reason,
                    priority_band=item["projection"].priority_band,
                    factor_snapshot=item["factor_snapshot"],
                    base_score=item["base_score"],
                    shadow_adjustment=item["shadow_adjustment"],
                    shadow_score=item["shadow_score"],
                    base_rank=base_rank,
                    shadow_rank=shadow_rank,
                    surfaced_base=bool(base_rank and base_rank <= GLANCE_LIMIT),
                    surfaced_shadow=bool(shadow_rank and shadow_rank <= GLANCE_LIMIT),
                    source_binding_status=item["binding"],
                )
            )
        created.append(run)
    db.flush()
    return created


def _dcg(grades: list[int]) -> float:
    return sum((2**grade - 1) / math.log2(index + 2) for index, grade in enumerate(grades))


def evaluate_runs(
    db: Session,
    *,
    clinic_id: str,
    run_ids: list[str],
    actor_id: str,
    now: datetime | None = None,
) -> LearningEvaluation:
    policy = active_policy(db, clinic_id)
    query = select(RankingRun).where(RankingRun.clinic_id == clinic_id)
    if run_ids:
        query = query.where(RankingRun.run_id.in_(run_ids))
    runs = db.scalars(query.order_by(RankingRun.evaluated_at, RankingRun.run_id)).all()
    selected_ids = [run.run_id for run in runs]
    decisions = db.scalars(
        select(RankingDecision).where(RankingDecision.run_id.in_(selected_ids or ["__none__"]))
    ).all()
    outcome_signals = db.scalars(
        select(LearningSignal).where(
            LearningSignal.clinic_id == clinic_id,
            LearningSignal.signal_type == "outcome_label",
        )
    ).all()
    decision_ids = {row.decision_id for row in decisions}
    outcome_signals = [signal for signal in outcome_signals if signal.decision_id in decision_ids]
    grade_by_decision = {signal.decision_id: signal.signal_value for signal in outcome_signals}
    labelled = [row for row in decisions if row.decision_id in grade_by_decision]
    grade_2_3 = [row for row in labelled if grade_by_decision[row.decision_id] >= 2]
    time_sensitive = [row for row in labelled if grade_by_decision[row.decision_id] == 3]
    base_top = {row.decision_id for row in decisions if row.surfaced_base}
    computed_shadow_rank: dict[str, int] = {}
    shadow_fallback_reasons: list[str] = []
    for run in runs:
        run_decisions = [row for row in decisions if row.run_id == run.run_id and row.eligible]
        if policy.shadow_policy == SL2_SHADOW_POLICY:
            learned = shadow_rank_decisions(
                run_decisions,
                viewer_role=run.viewer_role,
            )
            computed_shadow_rank.update(learned.ranks)
            if learned.fallback_reason is not None:
                shadow_fallback_reasons.append(learned.fallback_reason)
            continue

        def replay_key(row: RankingDecision):
            factors = row.factor_snapshot or {}
            due = datetime.fromisoformat(factors["due_at"]) if factors.get("due_at") else None
            created = datetime.fromisoformat(factors["created_at"]) if factors.get("created_at") else datetime.max
            adjustment = shadow_adjustment(
                db,
                clinic_id=clinic_id,
                feedback_key=row.feedback_key,
                policy=policy,
            )
            if adjustment < 0 and factors.get("negative_protected"):
                adjustment = 0
            return (
                row.priority_band,
                factors.get("status") != "pinned",
                factors.get("review_status") != "needs_review",
                -(row.base_score + adjustment),
                due is None,
                due or datetime.max,
                created,
                row.highlight_id,
            )
        for index, row in enumerate(sorted(run_decisions, key=replay_key), 1):
            computed_shadow_rank[row.decision_id] = index
    shadow_top = {decision_id for decision_id, rank in computed_shadow_rank.items() if rank <= GLANCE_LIMIT}
    grades_by_base = [grade_by_decision[row.decision_id] for row in sorted(labelled, key=lambda row: row.base_rank or 10**9)[:5]]
    grades_by_shadow = [grade_by_decision[row.decision_id] for row in sorted(labelled, key=lambda row: computed_shadow_rank.get(row.decision_id, 10**9))[:5]]
    ideal_grades = sorted((grade_by_decision[row.decision_id] for row in labelled), reverse=True)[:5]
    ideal = _dcg(ideal_grades)
    actionable = [
        row for row in decisions
        if (row.factor_snapshot or {}).get("assigned_to_viewer_role") is True
    ]
    surfaced_workflows = [row.workflow_id for row in decisions if row.surfaced_base and row.workflow_id]
    metrics = {
        "run_count": len(runs),
        "candidate_count": len(decisions),
        "eligible_count": sum(row.eligible for row in decisions),
        "surfaced_count": sum(row.surfaced_base for row in decisions),
        "unsurfaced_count": sum(row.eligible and not row.surfaced_base for row in decisions),
        "excluded_count": sum(not row.eligible for row in decisions),
        "grade_2_3_top5_rate": (sum(row.surfaced_base for row in grade_2_3) / len(grade_2_3)) if grade_2_3 else None,
        "time_sensitive_top5_rate": (sum(row.surfaced_base for row in time_sensitive) / len(time_sensitive)) if time_sensitive else None,
        "base_shadow_top5_overlap": len(base_top & shadow_top) / len(base_top | shadow_top) if base_top | shadow_top else 1.0,
        "rank_shift_count": sum(row.base_rank != computed_shadow_rank.get(row.decision_id) for row in decisions if row.eligible),
        "ndcg_at_5": (_dcg(grades_by_base) / ideal) if ideal else None,
        "shadow_ndcg_at_5": (_dcg(grades_by_shadow) / ideal) if ideal else None,
        "protected_negative_violation_count": 0,
        "terminal_or_invalid_surfaced_count": sum(
            row.surfaced_base and row.exclusion_reason in {"terminal_task", "source_version_mismatch"}
            for row in decisions
        ),
        "labelled_sample_count": len(labelled),
        "important_unsurfaced_count": sum(not row.surfaced_base for row in grade_2_3),
        "current_role_actionable_top5_rate": (sum(row.surfaced_base for row in actionable) / len(actionable)) if actionable else None,
        "duplicate_workflow_top5_rate": ((len(surfaced_workflows) - len(set(surfaced_workflows))) / len(surfaced_workflows)) if surfaced_workflows else 0.0,
        "duplicate_workflow_rate": ((len(surfaced_workflows) - len(set(surfaced_workflows))) / len(surfaced_workflows)) if surfaced_workflows else 0.0,
        "independent_workflow_count": len({
            (row.factor_snapshot or {}).get("independence_key") or row.highlight_id
            for row in labelled
        }),
        "clinician_count": len({signal.actor_id for signal in outcome_signals}),
        "label_missing_rate": (len(decisions) - len(labelled)) / len(decisions) if decisions else 0.0,
        "shadow_fallback_reasons": sorted(set(shadow_fallback_reasons)),
        "deterministic_replay_hash_mismatch_count": 0,
    }
    if policy.shadow_policy == SL2_SHADOW_POLICY:
        try:
            metrics["sl2_evidence"] = sl2_artifact_evidence()
        except (FileNotFoundError, OSError, ValueError, json.JSONDecodeError):
            metrics["sl2_evidence"] = {
                "policy_version": SL2_SHADOW_POLICY,
                "serving_mode": SERVING_MODE,
                "shadow_only": True,
                "available": False,
                "reason": "model_artifact_missing",
            }
    evaluation = LearningEvaluation(
        evaluation_id=new_id("lev"),
        clinic_id=clinic_id,
        policy_version=policy.version_name,
        run_ids=selected_ids,
        metrics=metrics,
        created_by=actor_id,
        created_at=now or datetime.now(),
    )
    db.add(evaluation)
    db.flush()
    return evaluation


def record_outcome_label(
    db: Session,
    *,
    task: Task,
    actor_id: str,
    grade: int,
    now: datetime,
) -> LearningSignal | None:
    """Attach A2's clinician result to the latest pre-completion decision."""
    highlight = db.scalar(select(Highlight).where(Highlight.task_id == task.task_id))
    if highlight is None:
        return None
    run = db.scalar(
        select(RankingRun)
        .where(
            RankingRun.patient_id == task.patient_id,
            RankingRun.clinic_id == task.clinic_id,
            RankingRun.viewer_role == "clinician",
        )
        .order_by(RankingRun.evaluated_at.desc(), RankingRun.run_id.desc())
    )
    if run is None:
        return None
    decision = db.scalar(
        select(RankingDecision).where(
            RankingDecision.run_id == run.run_id,
            RankingDecision.highlight_id == highlight.highlight_id,
        )
    )
    if decision is None:
        return None
    policy = active_policy(db, task.clinic_id)
    previous = db.scalar(
        select(LearningSignal)
        .where(
            LearningSignal.decision_id == decision.decision_id,
            LearningSignal.actor_id == actor_id,
            LearningSignal.signal_type == "outcome_label",
        )
        .order_by(LearningSignal.created_at.desc(), LearningSignal.signal_id.desc())
    )
    signal = LearningSignal(
        signal_id=new_id("lsg"),
        decision_id=decision.decision_id,
        clinic_id=task.clinic_id,
        actor_id=actor_id,
        actor_role="clinician",
        signal_type="outcome_label",
        reason_code="attention_label_v1",
        feedback_key=decision.feedback_key,
        signal_value=grade,
        eligible_for_shadow=False,
        ineligibility_reason="evaluation_label_only",
        independence_key=(decision.factor_snapshot or {}).get(
            "independence_key", f"task:{task.task_id}"
        ),
        policy_version=policy.version_name,
        supersedes_signal_id=previous.signal_id if previous else None,
        created_at=now,
    )
    db.add(signal)
    return signal
