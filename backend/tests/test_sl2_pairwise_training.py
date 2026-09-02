from __future__ import annotations

from app.pairwise_ranking import canonical_artifact_bytes, train_role_model
from app.sl2_dataset import load_sl2_dataset


def test_role_models_train_independently_with_frozen_optimizer():
    dataset = load_sl2_dataset()
    staff = train_role_model(dataset, "staff")
    clinician = train_role_model(dataset, "clinician")
    assert staff["viewer_role"] == "staff"
    assert clinician["viewer_role"] == "clinician"
    assert staff["hyperparameters"] == clinician["hyperparameters"] == {
        "initial_weights": "zeros",
        "learning_rate": 0.05,
        "iterations": 2000,
        "l2": 0.01,
        "full_batch": True,
        "intercept": False,
        "randomness": "none",
        "exponent_clip": [-30, 30],
    }


def test_training_is_byte_reproducible():
    dataset = load_sl2_dataset()
    first = train_role_model(dataset, "staff")
    second = train_role_model(dataset, "staff")
    assert canonical_artifact_bytes(first) == canonical_artifact_bytes(second)
    assert first["artifact_sha256"] == second["artifact_sha256"]


def test_frozen_evaluation_reports_workflow_concentration_without_reranking():
    dataset = load_sl2_dataset()
    artifact = train_role_model(dataset, "staff")
    assert artifact["test_metrics"]["duplicate_workflow_rate"] == 0.8
