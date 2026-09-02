from __future__ import annotations

from app.pairwise_ranking import load_model_artifact, validate_model_artifact


def test_repository_artifacts_have_complete_lineage_and_valid_hashes():
    for role in ("staff", "clinician"):
        artifact = load_model_artifact(role)
        assert validate_model_artifact(artifact, expected_role=role) is None
        assert artifact["policy_version"] == "sl2-pairwise-linear-v1"
        assert artifact["model_type"] == "pairwise_linear_logistic"
        assert artifact["train_scenario_ids"]
        assert artifact["validation_scenario_ids"]
        assert artifact["test_scenario_ids"]
        assert len(artifact["weights"]) == 18
        assert len(artifact["artifact_sha256"]) == 64
