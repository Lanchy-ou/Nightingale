from __future__ import annotations

import math

import pytest

from app.sl2_dataset import (
    DatasetContractError,
    FEATURE_NAMES,
    load_sl2_dataset,
    transform_snapshot,
)


def test_transform_uses_frozen_order_and_only_finite_normalized_values():
    dataset = load_sl2_dataset()
    snapshot = dataset.scenarios[0].items[0].attention_snapshot
    vector = transform_snapshot(snapshot)
    assert len(vector) == len(FEATURE_NAMES) == 18
    assert all(math.isfinite(value) and 0.0 <= value <= 1.0 for value in vector)


@pytest.mark.parametrize(
    "field,value",
    [
        ("text", "patient words"),
        ("base_score", 99),
        ("priority_band", 1),
        ("clinic_id", "clinic_x"),
        ("embedding", [0.1]),
    ],
)
def test_forbidden_or_leakage_fields_fail_closed(field, value):
    dataset = load_sl2_dataset()
    snapshot = dict(dataset.scenarios[0].items[0].attention_snapshot)
    snapshot[field] = value
    with pytest.raises(DatasetContractError):
        transform_snapshot(snapshot, strict_dataset=True)


def test_unknown_live_snapshot_field_fails_closed():
    dataset = load_sl2_dataset()
    snapshot = dict(dataset.scenarios[0].items[0].attention_snapshot)
    snapshot["unregistered_runtime_signal"] = 1
    with pytest.raises(DatasetContractError):
        transform_snapshot(snapshot)
