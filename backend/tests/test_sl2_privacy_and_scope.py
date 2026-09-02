from __future__ import annotations

import json

import pytest

from app.sl2_dataset import DatasetContractError, compile_pair, load_sl2_dataset


def test_dataset_and_artifacts_are_content_free():
    dataset = load_sl2_dataset()
    serialized = json.dumps(dataset.raw_documents, sort_keys=True).lower()
    for forbidden in (
        "patient_name",
        "task_title",
        "source_quote",
        "comment",
        "provider_payload",
        "password",
        "api_key",
    ):
        assert forbidden not in serialized


def test_cross_role_cross_band_and_invalid_binding_pairs_fail_closed():
    dataset = load_sl2_dataset()
    left = dataset.scenarios[0].items[0]
    right = dataset.scenarios[-1].items[1]
    with pytest.raises(DatasetContractError):
        compile_pair(left, right, scenario=dataset.scenarios[0])
    changed = right.copy_with(
        viewer_role=left.viewer_role,
        priority_band=left.priority_band,
        source_binding_status="hash_mismatch",
    )
    with pytest.raises(DatasetContractError):
        compile_pair(left, changed, scenario=dataset.scenarios[0])
