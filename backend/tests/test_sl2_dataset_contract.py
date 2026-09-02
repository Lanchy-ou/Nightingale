from __future__ import annotations

from collections import Counter

from app.sl2_dataset import load_sl2_dataset


def test_frozen_dataset_has_exact_group_split_and_pair_counts():
    dataset = load_sl2_dataset()
    assert len(dataset.scenarios) == 30
    assert Counter((row.viewer_role, row.split) for row in dataset.scenarios) == {
        ("staff", "train"): 9,
        ("staff", "validation"): 3,
        ("staff", "test"): 3,
        ("clinician", "train"): 9,
        ("clinician", "validation"): 3,
        ("clinician", "test"): 3,
    }
    assert Counter((pair.split, pair.label_kind) for pair in dataset.pairs) == {
        ("train", "strict"): 108,
        ("train", "tie"): 18,
        ("validation", "strict"): 36,
        ("validation", "tie"): 6,
        ("test", "strict"): 36,
        ("test", "tie"): 6,
    }
    assert all(len(scenario.strict_pairs) == 6 for scenario in dataset.scenarios)
    assert all(len(scenario.tie_pairs) == 1 for scenario in dataset.scenarios)


def test_scenario_groups_never_cross_splits_or_roles():
    dataset = load_sl2_dataset()
    ownership: dict[str, set[tuple[str, str]]] = {}
    for pair in dataset.pairs:
        ownership.setdefault(pair.scenario_group_id, set()).add(
            (pair.viewer_role, pair.split)
        )
    assert all(len(values) == 1 for values in ownership.values())
