"""Compile observed feedback and explicitly train a Shadow-only local artifact."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal  # noqa: E402
from app.observed_feedback import (  # noqa: E402
    ObservedFeedbackContractError,
    compile_observed_feedback_dataset,
    train_observed_feedback_model,
)
from app.sl2_dataset import canonical_json_bytes  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Compile content-free observed ranking feedback and train an "
            "offline Shadow-only pairwise model."
        )
    )
    parser.add_argument("--clinic-id", required=True)
    parser.add_argument("--viewer-role", required=True, choices=("staff", "clinician"))
    parser.add_argument(
        "--evidence-classification",
        required=True,
        choices=("synthetic_mechanism", "authorized_real_feedback"),
    )
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument(
        "--confirm-authorized-real-feedback",
        action="store_true",
        help=(
            "Required with authorized_real_feedback; confirms that local "
            "governance/consent approval exists outside this tool."
        ),
    )
    return parser


def main() -> int:
    args = _parser().parse_args()
    if (
        args.evidence_classification == "authorized_real_feedback"
        and not args.confirm_authorized_real_feedback
    ):
        print(
            "Refusing authorized_real_feedback without "
            "--confirm-authorized-real-feedback.",
            file=sys.stderr,
        )
        return 2
    with SessionLocal() as db:
        dataset = compile_observed_feedback_dataset(
            db,
            clinic_id=args.clinic_id,
            viewer_role=args.viewer_role,
        )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = args.output_dir / (
        f"observed_dataset_{args.viewer_role}_{dataset.manifest_sha256[:12]}.json"
    )
    dataset_path.write_bytes(canonical_json_bytes(dataset.to_document()) + b"\n")
    try:
        artifact = train_observed_feedback_model(
            dataset,
            viewer_role=args.viewer_role,
            evidence_classification=args.evidence_classification,
        )
    except ObservedFeedbackContractError as exc:
        print(
            json.dumps(
                {
                    "status": "training_blocked",
                    "dataset": str(dataset_path),
                    "readiness": dataset.readiness(),
                    "reason": str(exc),
                    "serving_mode": "base_only",
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    artifact_path = args.output_dir / (
        f"observed_model_{args.viewer_role}_{artifact['artifact_sha256'][:12]}.json"
    )
    artifact_path.write_bytes(canonical_json_bytes(artifact) + b"\n")
    print(
        json.dumps(
            {
                "status": "shadow_artifact_created",
                "dataset": str(dataset_path),
                "artifact": str(artifact_path),
                "evaluation": artifact["evaluation"],
                "serving_mode": "base_only",
                "real_clinician_validation": artifact[
                    "real_clinician_validation"
                ],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
