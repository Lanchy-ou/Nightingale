from __future__ import annotations

from app.pairwise_ranking import load_model_artifact, score_snapshot
from app.sl2_dataset import load_sl2_dataset, transform_snapshot


def test_counterfactual_narrative_variants_preserve_features_labels_and_scores():
    dataset = load_sl2_dataset()
    artifact = load_model_artifact("staff")
    pairs = dataset.counterfactual_pairs("staff")
    assert pairs
    for left, right in pairs:
        assert left.narrative_variant != right.narrative_variant
        assert [item.gold_rank_group for item in left.items] == [
            item.gold_rank_group for item in right.items
        ]
        for left_item, right_item in zip(left.items, right.items, strict=True):
            assert transform_snapshot(left_item.attention_snapshot) == transform_snapshot(
                right_item.attention_snapshot
            )
            assert score_snapshot(artifact, left_item.attention_snapshot) == score_snapshot(
                artifact, right_item.attention_snapshot
            )


def test_pair_orientation_and_identifier_reversal_do_not_change_gold_truth():
    dataset = load_sl2_dataset()
    strict = [pair for pair in dataset.pairs if pair.label_kind == "strict"]
    assert {pair.preferred_side for pair in strict} == {"left", "right"}
    assert all(pair.left_key < pair.right_key for pair in strict)
