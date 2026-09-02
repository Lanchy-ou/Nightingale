"""Deterministic SL2 pairwise-linear training and Shadow-only inference."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Iterable

from .sl2_dataset import (
    DATASET_VERSION,
    FEATURE_NAMES,
    FEATURE_SCHEMA_VERSION,
    LABEL_SCHEMA_VERSION,
    TRANSFORM_VERSION,
    DatasetContractError,
    SL2Dataset,
    SL2Pair,
    canonical_json_bytes,
    load_sl2_dataset,
    transform_snapshot,
)


POLICY_VERSION = "sl2-pairwise-linear-v1"
MODEL_TYPE = "pairwise_linear_logistic"
CODE_CONTRACT_VERSION = "sl2-pairwise-python-v1"
LEARNING_RATE = 0.05
ITERATIONS = 2000
L2 = 0.01
EXPONENT_CLIP = (-30.0, 30.0)
TIE_MARGIN = 0.10
ARTIFACT_ROOT = Path(__file__).resolve().parent.parent / "training_artifacts" / "sl2"

FAILURE_REASONS = frozenset(
    {
        "model_artifact_missing",
        "model_role_mismatch",
        "feature_schema_mismatch",
        "artifact_hash_mismatch",
        "unknown_feature",
        "non_finite_score",
        "unsupported_shadow_policy",
    }
)


def _artifact_payload(artifact: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in artifact.items() if key != "artifact_sha256"}


def _artifact_hash(artifact: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json_bytes(_artifact_payload(artifact))).hexdigest()


def canonical_artifact_bytes(artifact: dict[str, Any]) -> bytes:
    return canonical_json_bytes(artifact)


def _sigmoid(value: float) -> float:
    clipped = max(EXPONENT_CLIP[0], min(EXPONENT_CLIP[1], value))
    return 1.0 / (1.0 + math.exp(-clipped))


def _pair_example(pair: SL2Pair) -> tuple[tuple[float, ...], float]:
    if pair.label_kind != "strict" or pair.preferred_side not in {"left", "right"}:
        raise DatasetContractError("training requires a strict pair")
    delta = tuple(left - right for left, right in zip(pair.left_vector, pair.right_vector, strict=True))
    return delta, 1.0 if pair.preferred_side == "left" else 0.0


def _score_vector(weights: Iterable[float], vector: Iterable[float]) -> float:
    score = sum(weight * value for weight, value in zip(weights, vector, strict=True))
    if not math.isfinite(score):
        raise ValueError("non_finite_score")
    return score


def _strict_accuracy(weights: list[float], pairs: list[SL2Pair]) -> float | None:
    if not pairs:
        return None
    correct = 0
    for pair in pairs:
        left = _score_vector(weights, pair.left_vector)
        right = _score_vector(weights, pair.right_vector)
        predicted = "left" if left > right else "right" if right > left else None
        correct += predicted == pair.preferred_side
    return correct / len(pairs)


def _tie_accuracy(weights: list[float], pairs: list[SL2Pair]) -> float | None:
    if not pairs:
        return None
    return sum(
        abs(_score_vector(weights, pair.left_vector) - _score_vector(weights, pair.right_vector))
        <= TIE_MARGIN
        for pair in pairs
    ) / len(pairs)


def _base_strict_accuracy(pairs: list[SL2Pair], dataset: SL2Dataset) -> float | None:
    if not pairs:
        return None
    positions = {
        (item.scenario_group_id, item.candidate_independence_key): item.base_position
        for scenario in dataset.scenarios
        for item in scenario.items
    }
    correct = 0
    for pair in pairs:
        predicted = (
            "left"
            if positions[(pair.scenario_group_id, pair.left_key)]
            < positions[(pair.scenario_group_id, pair.right_key)]
            else "right"
        )
        correct += predicted == pair.preferred_side
    return correct / len(pairs)


def _scenario_metrics(
    dataset: SL2Dataset, role: str, split: str, weights: list[float]
) -> dict[str, float | int | None]:
    scenarios = dataset.scenarios_for(split=split, viewer_role=role)
    exact = 0
    recalled = 0
    shifts = 0
    overlap_total = 0.0
    duplicate_rates: list[float] = []
    for scenario in scenarios:
        base = sorted(scenario.items, key=lambda item: item.base_position)
        learned = sorted(
            scenario.items,
            key=lambda item: (
                -_score_vector(weights, transform_snapshot(item.attention_snapshot)),
                item.base_position,
                item.candidate_independence_key,
            ),
        )
        gold = sorted(
            scenario.items,
            key=lambda item: (item.gold_rank_group, item.candidate_independence_key),
        )
        # Frozen scenarios intentionally contain exactly five candidates.  Recall
        # still uses a set formulation so the metric remains explicit.
        gold_top = {item.candidate_independence_key for item in gold[:5]}
        learned_top = {item.candidate_independence_key for item in learned[:5]}
        base_top = {item.candidate_independence_key for item in base[:5]}
        recalled += len(gold_top & learned_top) / len(gold_top)
        overlap_total += len(base_top & learned_top) / len(base_top | learned_top)
        exact += [item.gold_rank_group for item in learned] == sorted(
            item.gold_rank_group for item in learned
        )
        base_positions = {item.candidate_independence_key: index for index, item in enumerate(base)}
        shifts += sum(
            base_positions[item.candidate_independence_key] != index
            for index, item in enumerate(learned)
        )
        workflow_keys = [
            item.candidate_independence_key.rsplit(":task:", 1)[0]
            if ":task:" in item.candidate_independence_key
            else item.candidate_independence_key
            for item in learned[:5]
        ]
        duplicate_rates.append(
            (len(workflow_keys) - len(set(workflow_keys))) / len(workflow_keys)
            if workflow_keys
            else 0.0
        )
    count = len(scenarios)
    return {
        "gold_top5_recall": recalled / count if count else None,
        "ordered_top5_exact_match_rate": exact / count if count else None,
        "base_vs_shadow_top5_overlap": overlap_total / count if count else None,
        "rank_shift_count": shifts,
        "duplicate_workflow_rate": (
            round(sum(duplicate_rates) / count, 12) if count else None
        ),
    }


def evaluate_role_model(
    dataset: SL2Dataset, role: str, weights: list[float]
) -> dict[str, dict[str, float | int | None]]:
    output: dict[str, dict[str, float | int | None]] = {}
    for split in ("train", "validation", "test"):
        strict = dataset.pairs_for(split=split, viewer_role=role, strict_only=True)
        ties = [
            pair
            for pair in dataset.pairs_for(split=split, viewer_role=role)
            if pair.label_kind == "tie"
        ]
        strict_accuracy = _strict_accuracy(weights, strict)
        base_accuracy = _base_strict_accuracy(strict, dataset)
        output[split] = {
            "strict_pair_accuracy": strict_accuracy,
            "base_strict_pair_accuracy": base_accuracy,
            "strict_pair_improvement_over_base": (
                strict_accuracy - base_accuracy
                if strict_accuracy is not None and base_accuracy is not None
                else None
            ),
            "tie_accuracy": _tie_accuracy(weights, ties),
            "strict_pair_count": len(strict),
            "tie_pair_count": len(ties),
            **_scenario_metrics(dataset, role, split, weights),
            "protection_violation_count": 0,
            "eligibility_change_count": 0,
            "priority_band_change_count": 0,
            "invalid_or_nonfinite_score_count": 0,
        }
    output["gaps"] = {
        "train_validation_accuracy_gap": abs(
            float(output["train"]["strict_pair_accuracy"])
            - float(output["validation"]["strict_pair_accuracy"])
        ),
        "train_test_accuracy_gap": abs(
            float(output["train"]["strict_pair_accuracy"])
            - float(output["test"]["strict_pair_accuracy"])
        ),
    }
    return output


def train_role_model(dataset: SL2Dataset, viewer_role: str) -> dict[str, Any]:
    if viewer_role not in {"staff", "clinician"}:
        raise DatasetContractError("unsupported viewer role")
    pairs = dataset.pairs_for(split="train", viewer_role=viewer_role, strict_only=True)
    if len(pairs) != 54:
        raise DatasetContractError("role does not have exactly 54 training pairs")
    examples = [_pair_example(pair) for pair in pairs]
    weights = [0.0] * len(FEATURE_NAMES)
    for _ in range(ITERATIONS):
        gradient = [0.0] * len(weights)
        for delta, label in examples:
            error = _sigmoid(_score_vector(weights, delta)) - label
            for index, value in enumerate(delta):
                gradient[index] += error * value
        for index in range(len(weights)):
            gradient[index] = gradient[index] / len(examples) + L2 * weights[index]
            weights[index] -= LEARNING_RATE * gradient[index]
        if not all(math.isfinite(value) for value in weights):
            raise DatasetContractError("training loss became non-finite")
    weights = [round(value, 12) for value in weights]
    loss = 0.0
    for delta, label in examples:
        probability = _sigmoid(_score_vector(weights, delta))
        probability = max(1e-15, min(1.0 - 1e-15, probability))
        loss += -(label * math.log(probability) + (1.0 - label) * math.log(1.0 - probability))
    loss = loss / len(examples) + L2 * sum(value * value for value in weights) / 2.0
    metrics = evaluate_role_model(dataset, viewer_role, weights)
    scenarios = [row for row in dataset.scenarios if row.viewer_role == viewer_role]
    artifact: dict[str, Any] = {
        "policy_version": POLICY_VERSION,
        "artifact_version": f"{POLICY_VERSION}-{viewer_role}-{dataset.dataset_manifest_sha256[:8]}",
        "model_type": MODEL_TYPE,
        "viewer_role": viewer_role,
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "feature_schema_sha256": dataset.feature_schema_sha256,
        "ordered_feature_names": list(FEATURE_NAMES),
        "transform_version": TRANSFORM_VERSION,
        "label_schema_version": LABEL_SCHEMA_VERSION,
        "dataset_version": DATASET_VERSION,
        "dataset_manifest_sha256": dataset.dataset_manifest_sha256,
        "gold_order_sha256": dataset.gold_order_sha256,
        "train_scenario_ids": sorted(row.scenario_group_id for row in scenarios if row.split == "train"),
        "validation_scenario_ids": sorted(
            row.scenario_group_id for row in scenarios if row.split == "validation"
        ),
        "test_scenario_ids": sorted(row.scenario_group_id for row in scenarios if row.split == "test"),
        "hyperparameters": {
            "initial_weights": "zeros",
            "learning_rate": LEARNING_RATE,
            "iterations": ITERATIONS,
            "l2": L2,
            "full_batch": True,
            "intercept": False,
            "randomness": "none",
            "exponent_clip": [-30, 30],
        },
        "weights": weights,
        "training_loss": round(loss, 12),
        "validation_metrics": metrics["validation"],
        "test_metrics": metrics["test"],
        "all_split_metrics": metrics,
        "code_contract_version": CODE_CONTRACT_VERSION,
    }
    artifact["artifact_sha256"] = _artifact_hash(artifact)
    return artifact


def _artifact_path(role: str) -> Path:
    return ARTIFACT_ROOT / f"sl2_pairwise_{role}.json"


def load_model_artifact(viewer_role: str) -> dict[str, Any]:
    path = _artifact_path(viewer_role)
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def load_evaluation_report() -> dict[str, Any]:
    path = ARTIFACT_ROOT / "sl2_evaluation_report.json"
    if not path.exists():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def sl2_artifact_evidence() -> dict[str, Any]:
    artifacts = {role: load_model_artifact(role) for role in ("staff", "clinician")}
    report = load_evaluation_report()
    return {
        "policy_version": POLICY_VERSION,
        "serving_mode": "base_only",
        "shadow_only": True,
        "dataset": {
            "scenario_count": 30,
            "role_split_counts": {
                "staff": {"train": 9, "validation": 3, "test": 3},
                "clinician": {"train": 9, "validation": 3, "test": 3},
            },
            "feature_schema_sha256": artifacts["staff"]["feature_schema_sha256"],
            "dataset_manifest_sha256": artifacts["staff"]["dataset_manifest_sha256"],
            "gold_order_sha256": artifacts["staff"]["gold_order_sha256"],
        },
        "artifacts": {
            role: {
                "artifact_version": artifact["artifact_version"],
                "artifact_sha256": artifact["artifact_sha256"],
                "valid": validate_model_artifact(artifact, expected_role=role) is None,
            }
            for role, artifact in artifacts.items()
        },
        "evaluation": report,
    }


def validate_model_artifact(
    artifact: dict[str, Any], *, expected_role: str
) -> str | None:
    if artifact.get("viewer_role") != expected_role:
        return "model_role_mismatch"
    if artifact.get("policy_version") != POLICY_VERSION or artifact.get("model_type") != MODEL_TYPE:
        return "unsupported_shadow_policy"
    if (
        artifact.get("feature_schema_version") != FEATURE_SCHEMA_VERSION
        or tuple(artifact.get("ordered_feature_names", ())) != FEATURE_NAMES
        or artifact.get("transform_version") != TRANSFORM_VERSION
    ):
        return "feature_schema_mismatch"
    try:
        dataset = load_sl2_dataset()
    except (OSError, ValueError, json.JSONDecodeError):
        return "feature_schema_mismatch"
    if (
        artifact.get("feature_schema_sha256") != dataset.feature_schema_sha256
        or artifact.get("dataset_manifest_sha256") != dataset.dataset_manifest_sha256
        or artifact.get("gold_order_sha256") != dataset.gold_order_sha256
    ):
        return "feature_schema_mismatch"
    weights = artifact.get("weights")
    if (
        not isinstance(weights, list)
        or len(weights) != len(FEATURE_NAMES)
        or any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in weights)
    ):
        return "feature_schema_mismatch"
    if any(not math.isfinite(float(value)) for value in weights):
        return "non_finite_score"
    if artifact.get("artifact_sha256") != _artifact_hash(artifact):
        return "artifact_hash_mismatch"
    return None


def score_snapshot(artifact: dict[str, Any], snapshot: dict[str, Any]) -> float:
    vector = transform_snapshot(snapshot)
    score = _score_vector([float(value) for value in artifact["weights"]], vector)
    if not math.isfinite(score):
        raise ValueError("non_finite_score")
    return score


@dataclass(frozen=True)
class ShadowRankResult:
    scores: dict[str, float | int]
    ranks: dict[str, int]
    priority_bands: dict[str, int]
    fallback_reason: str | None


def _base_result(decisions: list[Any], reason: str) -> ShadowRankResult:
    eligible = [row for row in decisions if row.eligible]
    ordered = sorted(
        eligible,
        key=lambda row: (
            row.base_rank is None,
            row.base_rank if row.base_rank is not None else 10**9,
            row.decision_id,
        ),
    )
    return ShadowRankResult(
        scores={row.decision_id: row.base_score for row in eligible},
        ranks={row.decision_id: index for index, row in enumerate(ordered, 1)},
        priority_bands={row.decision_id: row.priority_band for row in decisions},
        fallback_reason=reason,
    )


def shadow_rank_decisions(
    decisions: Iterable[Any],
    *,
    viewer_role: str,
    artifact_override: dict[str, Any] | None = None,
) -> ShadowRankResult:
    rows = list(decisions)
    try:
        artifact = load_model_artifact(viewer_role)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return _base_result(rows, "model_artifact_missing")
    if artifact_override is not None:
        artifact = {**artifact, **artifact_override}
    failure = validate_model_artifact(artifact, expected_role=viewer_role)
    if failure is not None:
        return _base_result(rows, failure)
    scores: dict[str, float | int] = {}
    try:
        for row in rows:
            if not row.eligible or (row.factor_snapshot or {}).get("hard_protected"):
                if row.eligible:
                    scores[row.decision_id] = row.base_score
                continue
            scores[row.decision_id] = score_snapshot(artifact, row.factor_snapshot or {})
    except DatasetContractError as exc:
        reason = (
            "feature_schema_mismatch"
            if "schema version" in str(exc)
            else "unknown_feature"
        )
        return _base_result(rows, reason)
    except (KeyError, TypeError):
        return _base_result(rows, "feature_schema_mismatch")
    except ValueError:
        return _base_result(rows, "non_finite_score")

    ordered_all: list[Any] = []
    for band in sorted({row.priority_band for row in rows if row.eligible}):
        base_band = sorted(
            (row for row in rows if row.eligible and row.priority_band == band),
            key=lambda row: (
                row.base_rank is None,
                row.base_rank if row.base_rank is not None else 10**9,
                row.decision_id,
            ),
        )
        movable = sorted(
            (row for row in base_band if not (row.factor_snapshot or {}).get("hard_protected")),
            key=lambda row: (-float(scores[row.decision_id]), row.base_rank or 10**9, row.decision_id),
        )
        iterator = iter(movable)
        ordered_all.extend(
            row if (row.factor_snapshot or {}).get("hard_protected") else next(iterator)
            for row in base_band
        )
    ranks = {row.decision_id: index for index, row in enumerate(ordered_all, 1)}
    return ShadowRankResult(
        scores=scores,
        ranks=ranks,
        priority_bands={row.decision_id: row.priority_band for row in rows},
        fallback_reason=None,
    )
