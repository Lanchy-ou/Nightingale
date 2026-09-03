from __future__ import annotations

import pytest
from types import SimpleNamespace

from app.observed_feedback import (
    ObservedFeedbackContractError,
    dataset_from_pairs_for_mechanism_test,
    train_observed_feedback_model,
    validate_observed_feedback_artifact,
    shadow_rank_observed_decisions,
)
from app.pairwise_ranking import canonical_artifact_bytes
from app.sl2_dataset import load_sl2_dataset


def test_unverified_evidence_cannot_emit_model():
    frozen = load_sl2_dataset()
    dataset = dataset_from_pairs_for_mechanism_test(
        [pair for pair in frozen.pairs if pair.viewer_role == "clinician"],
        viewer_role="clinician",
    )
    with pytest.raises(ObservedFeedbackContractError, match="evidence classification"):
        train_observed_feedback_model(
            dataset,
            viewer_role="clinician",
            evidence_classification="unverified_application_feedback",
        )


def test_synthetic_mechanism_training_is_reproducible_and_shadow_only():
    frozen = load_sl2_dataset()
    dataset = dataset_from_pairs_for_mechanism_test(
        [pair for pair in frozen.pairs if pair.viewer_role == "clinician"],
        viewer_role="clinician",
    )
    first = train_observed_feedback_model(
        dataset,
        viewer_role="clinician",
        evidence_classification="synthetic_mechanism",
    )
    second = train_observed_feedback_model(
        dataset,
        viewer_role="clinician",
        evidence_classification="synthetic_mechanism",
    )
    assert canonical_artifact_bytes(first) == canonical_artifact_bytes(second)
    assert validate_observed_feedback_artifact(first, expected_role="clinician") is None
    assert first["serving_mode"] == "base_only"
    assert first["shadow_only"] is True
    assert first["real_clinician_validation"] == "NOT_RUN"
    assert first["evaluation"]["test_strict_pair_accuracy"] >= 0.8


def test_observed_artifact_runs_only_as_band_preserving_shadow_and_fails_closed():
    frozen = load_sl2_dataset()
    dataset = dataset_from_pairs_for_mechanism_test(
        [pair for pair in frozen.pairs if pair.viewer_role == "clinician"],
        viewer_role="clinician",
    )
    artifact = train_observed_feedback_model(
        dataset,
        viewer_role="clinician",
        evidence_classification="synthetic_mechanism",
    )
    scenario = next(
        row
        for row in frozen.scenarios
        if row.viewer_role == "clinician" and row.split == "test"
    )
    decisions = [
        SimpleNamespace(
            decision_id=item.candidate_independence_key,
            eligible=True,
            priority_band=item.priority_band,
            factor_snapshot=item.attention_snapshot,
            base_score=10 - item.base_position,
            base_rank=item.base_position,
        )
        for item in scenario.items
    ]
    result = shadow_rank_observed_decisions(
        decisions,
        artifact,
        viewer_role="clinician",
        expected_scope_sha256=dataset.scope_sha256,
    )
    assert result.fallback_reason is None
    assert set(result.ranks) == {row.decision_id for row in decisions}
    assert all(
        result.priority_bands[row.decision_id] == row.priority_band
        for row in decisions
    )

    corrupted = {**artifact, "artifact_sha256": "0" * 64}
    fallback = shadow_rank_observed_decisions(
        decisions,
        corrupted,
        viewer_role="clinician",
        expected_scope_sha256=dataset.scope_sha256,
    )
    assert fallback.fallback_reason == "artifact_hash_mismatch"
    assert fallback.ranks == {
        row.decision_id: row.base_rank for row in decisions
    }

    wrong_scope = shadow_rank_observed_decisions(
        decisions,
        artifact,
        viewer_role="clinician",
        expected_scope_sha256="0" * 64,
    )
    assert wrong_scope.fallback_reason == "model_scope_mismatch"
