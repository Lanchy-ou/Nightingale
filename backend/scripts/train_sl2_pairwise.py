"""Generate the frozen, repository-local SL2 Shadow model artifacts."""
from __future__ import annotations

import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.pairwise_ranking import (  # noqa: E402
    ARTIFACT_ROOT,
    POLICY_VERSION,
    canonical_artifact_bytes,
    train_role_model,
)
from app.sl2_dataset import canonical_json_bytes, load_sl2_dataset  # noqa: E402


def _overall(role_artifacts: dict[str, dict]) -> dict:
    def mean(path: tuple[str, ...]) -> float:
        values = []
        for artifact in role_artifacts.values():
            value = artifact["all_split_metrics"]
            for key in path:
                value = value[key]
            values.append(float(value))
        return sum(values) / len(values)

    test_strict = mean(("test", "strict_pair_accuracy"))
    test_base = mean(("test", "base_strict_pair_accuracy"))
    checks = {
        "test_strict_pair_accuracy_overall": test_strict >= 0.85,
        "test_strict_pair_accuracy_staff": role_artifacts["staff"]["test_metrics"]["strict_pair_accuracy"] >= 0.80,
        "test_strict_pair_accuracy_clinician": role_artifacts["clinician"]["test_metrics"]["strict_pair_accuracy"] >= 0.80,
        "test_tie_accuracy_overall": mean(("test", "tie_accuracy")) >= 0.70,
        "test_gold_top5_recall_overall": mean(("test", "gold_top5_recall")) >= 0.80,
        "test_gold_top5_recall_staff": role_artifacts["staff"]["test_metrics"]["gold_top5_recall"] >= 0.75,
        "test_gold_top5_recall_clinician": role_artifacts["clinician"]["test_metrics"]["gold_top5_recall"] >= 0.75,
        "test_shadow_improvement_over_base": test_strict - test_base >= 0.10,
        "train_test_gap_staff": role_artifacts["staff"]["all_split_metrics"]["gaps"]["train_test_accuracy_gap"] <= 0.15,
        "train_test_gap_clinician": role_artifacts["clinician"]["all_split_metrics"]["gaps"]["train_test_accuracy_gap"] <= 0.15,
        "zero_safety_and_contract_violations": all(
            artifact["test_metrics"][field] == 0
            for artifact in role_artifacts.values()
            for field in (
                "protection_violation_count",
                "eligibility_change_count",
                "priority_band_change_count",
                "invalid_or_nonfinite_score_count",
            )
        ),
    }
    return {
        "policy_version": POLICY_VERSION,
        "serving_mode": "base_only",
        "shadow_only": True,
        "overall_test_metrics": {
            "strict_pair_accuracy": test_strict,
            "base_strict_pair_accuracy": test_base,
            "strict_pair_improvement_over_base": test_strict - test_base,
            "tie_accuracy": mean(("test", "tie_accuracy")),
            "gold_top5_recall": mean(("test", "gold_top5_recall")),
        },
        "role_metrics": {
            role: artifact["all_split_metrics"] for role, artifact in role_artifacts.items()
        },
        "threshold_checks": checks,
        "all_thresholds_pass": all(checks.values()),
        "deterministic_replay_hash_mismatch_count": 0,
    }


def main() -> int:
    dataset = load_sl2_dataset()
    artifacts: dict[str, dict] = {}
    for role in ("staff", "clinician"):
        first = train_role_model(dataset, role)
        second = train_role_model(dataset, role)
        if canonical_artifact_bytes(first) != canonical_artifact_bytes(second):
            raise RuntimeError(f"{role} artifact was not byte reproducible")
        artifacts[role] = first
    ARTIFACT_ROOT.mkdir(parents=True, exist_ok=True)
    for role, artifact in artifacts.items():
        (ARTIFACT_ROOT / f"sl2_pairwise_{role}.json").write_bytes(
            canonical_artifact_bytes(artifact) + b"\n"
        )
    report = _overall(artifacts)
    (ARTIFACT_ROOT / "sl2_evaluation_report.json").write_bytes(
        canonical_json_bytes(report) + b"\n"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_thresholds_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
