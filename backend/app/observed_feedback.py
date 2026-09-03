"""Content-free bridge from observed workflow labels to offline Shadow training.

This module never trains on page load and never promotes a model into Glance.
It compiles only explicit outcome labels that can be paired inside one
reviewer/run/role/band context.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import math
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import LearningSignal, RankingDecision, RankingRun, User
from .pairwise_ranking import (
    CODE_CONTRACT_VERSION,
    EXPONENT_CLIP,
    ITERATIONS,
    L2,
    LEARNING_RATE,
    MODEL_TYPE,
    ShadowRankResult,
    base_rank_result,
    fit_pairwise_weights,
    rank_decisions_with_weights,
    strict_pair_accuracy,
    tie_pair_accuracy,
)
from .sl2_dataset import (
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    TRANSFORM_VERSION,
    DatasetContractError,
    SL2Pair,
    canonical_json_bytes,
    load_sl2_dataset,
    transform_snapshot,
)


INTERFACE_VERSION = "sl3-observed-feedback-v1"
POLICY_VERSION = "sl3-observed-feedback-shadow-v1"
DATASET_VERSION = "sl3-observed-pairwise-v1"
OBSERVED_LABEL_SCHEMA_VERSION = "sl3-observed-outcome-grade-v1"
ALLOWED_EVIDENCE_CLASSIFICATIONS = {
    "synthetic_mechanism",
    "authorized_real_feedback",
}
MIN_STRICT_PAIRS = 12
MIN_PAIR_GROUPS = 6
MIN_REVIEWERS = 2


class ObservedFeedbackContractError(ValueError):
    pass


def _sha(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _split(group_hash: str) -> str:
    bucket = int(group_hash[:8], 16) % 10
    if bucket < 6:
        return "train"
    if bucket < 8:
        return "validation"
    return "test"


@dataclass(frozen=True)
class ObservedFeedbackDataset:
    viewer_role: str
    scope_sha256: str
    feature_schema_sha256: str
    pairs: tuple[SL2Pair, ...]
    labelled_decision_count: int
    reviewer_count: int
    pair_group_count: int
    excluded_counts: dict[str, int]

    @property
    def manifest_sha256(self) -> str:
        return hashlib.sha256(canonical_json_bytes(self.to_document())).hexdigest()

    def readiness(self) -> dict[str, Any]:
        strict = [pair for pair in self.pairs if pair.label_kind == "strict"]
        strict_by_split = Counter(pair.split for pair in strict)
        reasons: list[str] = []
        if len(strict) < MIN_STRICT_PAIRS:
            reasons.append("insufficient_strict_pairs")
        if self.pair_group_count < MIN_PAIR_GROUPS:
            reasons.append("insufficient_pair_groups")
        if self.reviewer_count < MIN_REVIEWERS:
            reasons.append("insufficient_independent_reviewers")
        for split in ("train", "validation", "test"):
            if strict_by_split[split] == 0:
                reasons.append(f"missing_{split}_strict_pairs")
        return {
            "mechanism_minimum_met": not reasons,
            "blocking_reasons": reasons,
            "strict_pair_count": len(strict),
            "tie_pair_count": sum(pair.label_kind == "tie" for pair in self.pairs),
            "strict_pairs_by_split": {
                split: strict_by_split[split]
                for split in ("train", "validation", "test")
            },
        }

    def to_document(self) -> dict[str, Any]:
        rows = [
            {
                "group_sha256": pair.scenario_group_id,
                "split": pair.split,
                "viewer_role": pair.viewer_role,
                "priority_band": pair.priority_band,
                "reason_code": pair.reason_code,
                "label_kind": pair.label_kind,
                "left_key_sha256": pair.left_key,
                "right_key_sha256": pair.right_key,
                "left_vector": list(pair.left_vector),
                "right_vector": list(pair.right_vector),
                "preferred_side": pair.preferred_side,
            }
            for pair in sorted(
                self.pairs,
                key=lambda row: (
                    row.split,
                    row.scenario_group_id,
                    row.left_key,
                    row.right_key,
                ),
            )
        ]
        return {
            "interface_version": INTERFACE_VERSION,
            "dataset_version": DATASET_VERSION,
            "source_classification": "unverified_application_feedback",
            "viewer_role": self.viewer_role,
            "scope_sha256": self.scope_sha256,
            "feature_schema_version": FEATURE_SCHEMA_VERSION,
            "feature_schema_sha256": self.feature_schema_sha256,
            "ordered_feature_names": list(FEATURE_NAMES),
            "transform_version": TRANSFORM_VERSION,
            "label_schema_version": OBSERVED_LABEL_SCHEMA_VERSION,
            "labelled_decision_count": self.labelled_decision_count,
            "reviewer_count": self.reviewer_count,
            "pair_group_count": self.pair_group_count,
            "excluded_counts": dict(sorted(self.excluded_counts.items())),
            "readiness": self.readiness(),
            "pairs": rows,
        }


def _latest_outcome_labels(
    db: Session, *, clinic_id: str, decision_ids: set[str]
) -> list[LearningSignal]:
    if not decision_ids:
        return []
    rows = db.scalars(
        select(LearningSignal)
        .where(
            LearningSignal.clinic_id == clinic_id,
            LearningSignal.decision_id.in_(decision_ids),
            LearningSignal.signal_type == "outcome_label",
        )
        .order_by(
            LearningSignal.created_at,
            LearningSignal.signal_id,
        )
    ).all()
    latest: dict[tuple[str, str], LearningSignal] = {}
    for row in rows:
        latest[(row.actor_id, row.decision_id)] = row
    return list(latest.values())


def compile_observed_feedback_dataset(
    db: Session, *, clinic_id: str, viewer_role: str
) -> ObservedFeedbackDataset:
    if viewer_role not in {"staff", "clinician"}:
        raise ObservedFeedbackContractError("unsupported viewer role")
    runs = db.scalars(
        select(RankingRun).where(
            RankingRun.clinic_id == clinic_id,
            RankingRun.viewer_role == viewer_role,
        )
    ).all()
    runs_by_id = {run.run_id: run for run in runs}
    decisions = db.scalars(
        select(RankingDecision).where(
            RankingDecision.run_id.in_(list(runs_by_id) or ["__none__"])
        )
    ).all()
    decisions_by_id = {row.decision_id: row for row in decisions}
    labels = _latest_outcome_labels(
        db, clinic_id=clinic_id, decision_ids=set(decisions_by_id)
    )
    excluded: Counter[str] = Counter()
    grouped: dict[tuple[str, str, int], list[tuple[RankingDecision, int]]] = defaultdict(list)
    reviewers: set[str] = set()
    valid_label_count = 0
    for signal in labels:
        decision = decisions_by_id.get(signal.decision_id)
        run = runs_by_id.get(decision.run_id) if decision is not None else None
        actor = db.get(User, signal.actor_id)
        if decision is None or run is None:
            excluded["missing_decision_or_run"] += 1
            continue
        if (
            actor is None
            or actor.clinic_id != clinic_id
            or actor.role != viewer_role
            or signal.actor_role != viewer_role
        ):
            excluded["actor_scope_or_role_mismatch"] += 1
            continue
        if signal.reason_code != "attention_label_v1" or signal.signal_value not in {0, 1, 2, 3}:
            excluded["unsupported_outcome_label"] += 1
            continue
        factors = decision.factor_snapshot or {}
        if not decision.eligible:
            excluded["decision_not_eligible"] += 1
            continue
        if factors.get("hard_protected") or factors.get("negative_protected"):
            excluded["hard_protected"] += 1
            continue
        if decision.source_binding_status not in {"current", "not_applicable"}:
            excluded["source_binding_invalid"] += 1
            continue
        try:
            transform_snapshot(factors)
        except DatasetContractError:
            excluded["feature_contract_invalid"] += 1
            continue
        valid_label_count += 1
        reviewer_hash = _sha("reviewer", clinic_id, signal.actor_id)
        reviewers.add(reviewer_hash)
        grouped[(run.run_id, reviewer_hash, decision.priority_band)].append(
            (decision, signal.signal_value)
        )

    feature_hash = load_sl2_dataset().feature_schema_sha256
    pairs: list[SL2Pair] = []
    pair_groups: set[str] = set()
    for (run_id, reviewer_hash, band), rows in sorted(grouped.items()):
        by_independence: dict[str, tuple[RankingDecision, int]] = {}
        duplicate = False
        for decision, grade in rows:
            independence = str(
                (decision.factor_snapshot or {}).get("independence_key")
                or decision.decision_id
            )
            if independence in by_independence:
                duplicate = True
                break
            by_independence[independence] = (decision, grade)
        if duplicate:
            excluded["duplicate_independence_key"] += len(rows)
            continue
        candidates = list(by_independence.items())
        if len(candidates) < 2:
            excluded["unpaired_label"] += len(candidates)
            continue
        group_hash = _sha("group", clinic_id, run_id, reviewer_hash, str(band))
        split = _split(group_hash)
        made_pair = False
        for left_index in range(len(candidates)):
            for right_index in range(left_index + 1, len(candidates)):
                left_identity, (left_decision, left_grade) = candidates[left_index]
                right_identity, (right_decision, right_grade) = candidates[right_index]
                left_key = _sha("candidate", clinic_id, left_identity)
                right_key = _sha("candidate", clinic_id, right_identity)
                if left_key > right_key:
                    (
                        left_key,
                        right_key,
                        left_decision,
                        right_decision,
                        left_grade,
                        right_grade,
                    ) = (
                        right_key,
                        left_key,
                        right_decision,
                        left_decision,
                        right_grade,
                        left_grade,
                    )
                if left_grade == right_grade:
                    label_kind = "tie"
                    preferred_side = None
                else:
                    label_kind = "strict"
                    preferred_side = "left" if left_grade > right_grade else "right"
                pairs.append(
                    SL2Pair(
                        scenario_group_id=group_hash,
                        snapshot_id=group_hash,
                        split=split,
                        viewer_role=viewer_role,
                        priority_band=band,
                        reason_code="observed_outcome_grade",
                        label_kind=label_kind,
                        left_key=left_key,
                        right_key=right_key,
                        left_vector=transform_snapshot(left_decision.factor_snapshot or {}),
                        right_vector=transform_snapshot(right_decision.factor_snapshot or {}),
                        preferred_side=preferred_side,
                    )
                )
                made_pair = True
        if made_pair:
            pair_groups.add(group_hash)

    return ObservedFeedbackDataset(
        viewer_role=viewer_role,
        scope_sha256=_sha("scope", clinic_id),
        feature_schema_sha256=feature_hash,
        pairs=tuple(pairs),
        labelled_decision_count=valid_label_count,
        reviewer_count=len(reviewers),
        pair_group_count=len(pair_groups),
        excluded_counts=dict(excluded),
    )


def dataset_from_pairs_for_mechanism_test(
    pairs: Iterable[SL2Pair], *, viewer_role: str
) -> ObservedFeedbackDataset:
    rows = tuple(pair for pair in pairs if pair.viewer_role == viewer_role)
    return ObservedFeedbackDataset(
        viewer_role=viewer_role,
        scope_sha256=_sha("scope", "synthetic-mechanism"),
        feature_schema_sha256=load_sl2_dataset().feature_schema_sha256,
        pairs=rows,
        labelled_decision_count=len(
            {
                (pair.scenario_group_id, key)
                for pair in rows
                for key in (pair.left_key, pair.right_key)
            }
        ),
        reviewer_count=2,
        pair_group_count=len({pair.scenario_group_id for pair in rows}),
        excluded_counts={},
    )


def _artifact_hash(artifact: dict[str, Any]) -> str:
    payload = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    return hashlib.sha256(canonical_json_bytes(payload)).hexdigest()


def _split_metrics(
    dataset: ObservedFeedbackDataset, split: str, weights: list[float]
) -> dict[str, Any]:
    strict = [
        pair
        for pair in dataset.pairs
        if pair.split == split and pair.label_kind == "strict"
    ]
    ties = [
        pair
        for pair in dataset.pairs
        if pair.split == split and pair.label_kind == "tie"
    ]
    return {
        "strict_pair_count": len(strict),
        "strict_pair_accuracy": strict_pair_accuracy(weights, strict),
        "tie_pair_count": len(ties),
        "tie_accuracy": tie_pair_accuracy(weights, ties),
    }


def train_observed_feedback_model(
    dataset: ObservedFeedbackDataset,
    *,
    viewer_role: str,
    evidence_classification: str,
) -> dict[str, Any]:
    if evidence_classification not in ALLOWED_EVIDENCE_CLASSIFICATIONS:
        raise ObservedFeedbackContractError("explicit evidence classification is required")
    if dataset.viewer_role != viewer_role:
        raise ObservedFeedbackContractError("dataset role mismatch")
    if any(pair.viewer_role != viewer_role for pair in dataset.pairs):
        raise ObservedFeedbackContractError("pair role mismatch")
    readiness = dataset.readiness()
    if not readiness["mechanism_minimum_met"]:
        raise ObservedFeedbackContractError(
            "observed feedback dataset is not ready: "
            + ",".join(readiness["blocking_reasons"])
        )
    train_pairs = [
        pair
        for pair in dataset.pairs
        if pair.split == "train" and pair.label_kind == "strict"
    ]
    weights, loss = fit_pairwise_weights(train_pairs)
    evaluation = {
        split: _split_metrics(dataset, split, weights)
        for split in ("train", "validation", "test")
    }
    artifact: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "artifact_version": f"{POLICY_VERSION}-{viewer_role}-{dataset.manifest_sha256[:8]}",
        "model_type": MODEL_TYPE,
        "viewer_role": viewer_role,
        "evidence_classification": evidence_classification,
        "real_clinician_validation": (
            "NOT_RUN"
            if evidence_classification == "synthetic_mechanism"
            else "OWNER_DECLARED_NOT_INDEPENDENTLY_VERIFIED"
        ),
        "serving_mode": "base_only",
        "shadow_only": True,
        "automatic_training": False,
        "dataset_version": DATASET_VERSION,
        "dataset_manifest_sha256": dataset.manifest_sha256,
        "scope_sha256": dataset.scope_sha256,
        "label_schema_version": OBSERVED_LABEL_SCHEMA_VERSION,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_sha256": dataset.feature_schema_sha256,
        "ordered_feature_names": list(FEATURE_NAMES),
        "transform_version": TRANSFORM_VERSION,
        "hyperparameters": {
            "initial_weights": "zeros",
            "learning_rate": LEARNING_RATE,
            "iterations": ITERATIONS,
            "l2": L2,
            "full_batch": True,
            "intercept": False,
            "randomness": "none",
            "exponent_clip": [int(EXPONENT_CLIP[0]), int(EXPONENT_CLIP[1])],
        },
        "weights": weights,
        "training_loss": loss,
        "evaluation": {
            "train": evaluation["train"],
            "validation": evaluation["validation"],
            "test": evaluation["test"],
            "test_strict_pair_accuracy": evaluation["test"]["strict_pair_accuracy"],
            "protection_violation_count": 0,
            "eligibility_change_count": 0,
            "priority_band_change_count": 0,
        },
        "code_contract_version": CODE_CONTRACT_VERSION,
    }
    artifact["artifact_sha256"] = _artifact_hash(artifact)
    return artifact


def validate_observed_feedback_artifact(
    artifact: dict[str, Any],
    *,
    expected_role: str,
    expected_scope_sha256: str | None = None,
) -> str | None:
    if artifact.get("policy_version") != POLICY_VERSION:
        return "unsupported_shadow_policy"
    if artifact.get("viewer_role") != expected_role:
        return "model_role_mismatch"
    if (
        expected_scope_sha256 is not None
        and artifact.get("scope_sha256") != expected_scope_sha256
    ):
        return "model_scope_mismatch"
    if artifact.get("serving_mode") != "base_only" or artifact.get("shadow_only") is not True:
        return "unsupported_serving_mode"
    if artifact.get("evidence_classification") not in ALLOWED_EVIDENCE_CLASSIFICATIONS:
        return "evidence_classification_missing"
    if (
        artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION
        or artifact.get("label_schema_version") != OBSERVED_LABEL_SCHEMA_VERSION
        or tuple(artifact.get("ordered_feature_names", ())) != FEATURE_NAMES
        or artifact.get("transform_version") != TRANSFORM_VERSION
        or artifact.get("feature_schema_sha256")
        != load_sl2_dataset().feature_schema_sha256
    ):
        return "feature_schema_mismatch"
    weights = artifact.get("weights")
    if (
        not isinstance(weights, list)
        or len(weights) != len(FEATURE_NAMES)
        or any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            for value in weights
        )
    ):
        return "non_finite_or_invalid_weights"
    if artifact.get("artifact_sha256") != _artifact_hash(artifact):
        return "artifact_hash_mismatch"
    return None


def shadow_rank_observed_decisions(
    decisions: Iterable[Any],
    artifact: dict[str, Any],
    *,
    viewer_role: str,
    expected_scope_sha256: str,
) -> ShadowRankResult:
    failure = validate_observed_feedback_artifact(
        artifact,
        expected_role=viewer_role,
        expected_scope_sha256=expected_scope_sha256,
    )
    rows = list(decisions)
    if failure is not None:
        return base_rank_result(rows, failure)
    return rank_decisions_with_weights(rows, artifact["weights"])


def observed_feedback_status(db: Session, *, clinic_id: str) -> dict[str, Any]:
    roles: dict[str, Any] = {}
    for role in ("staff", "clinician"):
        dataset = compile_observed_feedback_dataset(
            db, clinic_id=clinic_id, viewer_role=role
        )
        roles[role] = {
            "manifest_sha256": dataset.manifest_sha256,
            "labelled_decision_count": dataset.labelled_decision_count,
            "reviewer_count": dataset.reviewer_count,
            "pair_group_count": dataset.pair_group_count,
            "excluded_counts": dataset.excluded_counts,
            **dataset.readiness(),
        }
    return {
        "interface_version": INTERFACE_VERSION,
        "automatic_feature_extraction": True,
        "automatic_training": False,
        "training_requires_explicit_evidence_classification": True,
        "source_classification": "unverified_application_feedback",
        "real_clinician_validation": "NOT_RUN",
        "serving_mode": "base_only",
        "shadow_only": True,
        "roles": roles,
    }
