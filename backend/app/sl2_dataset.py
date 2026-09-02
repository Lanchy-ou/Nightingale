"""Frozen synthetic SL2 dataset and feature-contract compiler.

Only workflow/state metadata is accepted.  Clinical text, identifiers and
serving/ranking outputs are never model features.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, replace
import hashlib
import json
import math
from pathlib import Path
from typing import Any


FEATURE_NAMES = (
    "due_known",
    "due_proximity_7d",
    "overdue_age_7d",
    "waiting_age_7d",
    "workflow_blocking_known",
    "workflow_blocking_value",
    "open_downstream_action_count_cap3",
    "requires_action_from_viewer",
    "requires_decision_from_viewer",
    "upstream_verification_known",
    "upstream_verified",
    "upstream_corrected",
    "upstream_unable_to_verify",
    "patient_reported_done_pending_verification",
    "attention_kind_care_task",
    "attention_kind_patient_report_review",
    "attention_kind_clinician_priority_review",
    "attention_kind_artifact_highlight",
)
FEATURE_SCHEMA_VERSION = "attention-feature-v1"
TRANSFORM_VERSION = "sl2-transform-v1"
LABEL_SCHEMA_VERSION = "sl2-gold-order-v1"
DATASET_VERSION = "sl2-synthetic-workflow-v1"
SECONDS_7D = 604800.0

ALLOWED_REASON_CODES = frozenset(
    {
        "explicit_downstream_blocker_first",
        "closer_due_first_when_other_context_equal",
        "longer_wait_first_when_no_due",
        "explicit_decision_before_equivalent_execution",
        "reported_done_verification_before_routine_open_task",
        "updated_upstream_verification_before_unchanged_context",
        "more_open_downstream_obligations_first",
        "equivalent_workflow_state_tie",
    }
)

DATASET_SNAPSHOT_FIELDS = frozenset(
    {
        "schema_version",
        "due_known",
        "time_to_due_seconds",
        "age_seconds",
        "workflow_blocking_known",
        "workflow_blocking",
        "open_downstream_action_count",
        "requires_action_from_viewer",
        "requires_decision_from_viewer",
        "upstream_verification_known",
        "upstream_verification_outcome",
        "patient_reported_done_pending_verification",
        "attention_kind",
        "active_frontier",
        "eligible",
        "hard_protected",
        "source_binding_status",
    }
)

FORBIDDEN_FEATURE_FIELDS = frozenset(
    {
        "clinic_id",
        "patient_id",
        "user_id",
        "candidate_id",
        "workflow_id",
        "event_id",
        "independence_key",
        "workflow_group_key",
        "text",
        "normalized_text",
        "task_title",
        "diagnosis",
        "symptom_name",
        "embedding",
        "provider_output",
        "provider_payload",
        "source_quote",
        "note",
        "comment",
        "source_authority",
        "clinician_identity",
        "specialty",
        "exclusion_reason",
        "priority_band",
        "explicit_risk",
        "clinician_confirmed",
        "needs_review",
        "base_score",
        "base_rank",
        "shadow_score",
        "displayed_position",
        "gold_rank",
        "future_action",
        "click",
        "dwell_time",
        "created_at",
        "due_at",
    }
)

LIVE_SNAPSHOT_METADATA_FIELDS = frozenset(
    {
        "source_kind",
        "source_id",
        "candidate_id",
        "clinic_id",
        "patient_id",
        "event_id",
        "workflow_id",
        "workflow_root_event_id",
        "workflow_group_key",
        "independence_key",
        "workflow_node_type",
        "workflow_node_id",
        "viewer_role",
        "status",
        "terminal",
        "unresolved",
        "rejected",
        "pinned",
        "needs_review",
        "conflict_unresolved",
        "attention_class",
        "task_kind",
        "task_assigned_role",
        "task_status",
        "review_outcome",
        "review_status",
        "time_sensitivity",
        "workflow_status",
        "superseded",
        "responsible_role_known",
        "responsible_role",
        "assigned_to_viewer_role",
        "waiting_for_other_role",
        "role_route_known",
        "assigned_user_id",
        "due_at",
        "overdue",
        "escalated",
        "workflow_link_known",
        "inbound_relation_types",
        "outbound_relation_types",
        "blocking_predecessor_count",
        "parent_context_known",
        "exact_span_available",
        "source_authority",
        "protection_reasons",
        "base_importance_score",
        "decay_adjustment",
        "adaptive_adjustment",
        "final_score",
        "score",
        "priority_band",
        "priority_reasons",
        "exclusion_reason",
        "created_at",
        "feature_class_registry",
        "negative_protected",
        "sl2_model_score",
        "shadow_fallback_reason",
        "shadow_artifact_version",
    }
)


class DatasetContractError(ValueError):
    pass


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_json_bytes(value)).hexdigest()


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _finite_number(value: object, field: str) -> float:
    if not _is_number(value):
        raise DatasetContractError(f"{field} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise DatasetContractError(f"{field} must be finite")
    return result


def _bool(value: object, field: str) -> float:
    if not isinstance(value, bool):
        raise DatasetContractError(f"{field} must be boolean")
    return 1.0 if value else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def transform_snapshot(
    snapshot: dict[str, Any], *, strict_dataset: bool = False
) -> tuple[float, ...]:
    if not isinstance(snapshot, dict):
        raise DatasetContractError("feature snapshot must be an object")
    if snapshot.get("schema_version") != FEATURE_SCHEMA_VERSION:
        raise DatasetContractError("feature schema version mismatch")
    if strict_dataset:
        unknown = set(snapshot) - DATASET_SNAPSHOT_FIELDS
        if unknown:
            raise DatasetContractError(f"unregistered dataset feature fields: {sorted(unknown)}")
        missing = DATASET_SNAPSHOT_FIELDS - set(snapshot)
        if missing:
            raise DatasetContractError(f"missing dataset feature fields: {sorted(missing)}")
    else:
        unknown = set(snapshot) - DATASET_SNAPSHOT_FIELDS - LIVE_SNAPSHOT_METADATA_FIELDS
        if unknown:
            raise DatasetContractError(f"unknown live snapshot fields: {sorted(unknown)}")

    due_known = _bool(snapshot.get("due_known"), "due_known")
    time_to_due = snapshot.get("time_to_due_seconds")
    if due_known:
        time_value = _finite_number(time_to_due, "time_to_due_seconds")
        due_proximity = _clamp(1.0 - max(time_value, 0.0) / SECONDS_7D)
        overdue_age = _clamp(max(-time_value, 0.0) / SECONDS_7D)
    else:
        if time_to_due is not None:
            raise DatasetContractError("unknown due time must be null")
        due_proximity = 0.0
        overdue_age = 0.0
    waiting_age = _clamp(_finite_number(snapshot.get("age_seconds"), "age_seconds") / SECONDS_7D)
    blocking_known = _bool(
        snapshot.get("workflow_blocking_known"), "workflow_blocking_known"
    )
    blocking_raw = snapshot.get("workflow_blocking")
    if blocking_known:
        blocking_value = _bool(blocking_raw, "workflow_blocking")
    else:
        if blocking_raw not in (None, False):
            raise DatasetContractError(
                "unknown workflow blocking value must be null or false"
            )
        blocking_value = 0.0
    downstream = _finite_number(
        snapshot.get("open_downstream_action_count"),
        "open_downstream_action_count",
    )
    if downstream < 0:
        raise DatasetContractError("open downstream action count cannot be negative")
    downstream_cap = min(downstream, 3.0) / 3.0
    upstream_known = _bool(
        snapshot.get("upstream_verification_known"), "upstream_verification_known"
    )
    outcome = snapshot.get("upstream_verification_outcome")
    if not upstream_known and outcome is not None:
        raise DatasetContractError("unknown upstream verification outcome must be null")
    if upstream_known and outcome not in {"verified", "corrected", "unable_to_verify"}:
        raise DatasetContractError("unsupported upstream verification outcome")
    kind = snapshot.get("attention_kind")
    kinds = (
        "care_task",
        "patient_report_review",
        "clinician_priority_review",
        "artifact_highlight",
    )
    if kind not in kinds:
        raise DatasetContractError("unsupported attention kind")
    values = (
        due_known,
        due_proximity,
        overdue_age,
        waiting_age,
        blocking_known,
        blocking_value,
        downstream_cap,
        _bool(snapshot.get("requires_action_from_viewer"), "requires_action_from_viewer"),
        _bool(snapshot.get("requires_decision_from_viewer"), "requires_decision_from_viewer"),
        upstream_known,
        1.0 if outcome == "verified" else 0.0,
        1.0 if outcome == "corrected" else 0.0,
        1.0 if outcome == "unable_to_verify" else 0.0,
        _bool(
            snapshot.get("patient_reported_done_pending_verification"),
            "patient_reported_done_pending_verification",
        ),
        *(1.0 if kind == expected else 0.0 for expected in kinds),
    )
    if len(values) != len(FEATURE_NAMES) or not all(math.isfinite(value) for value in values):
        raise DatasetContractError("invalid transformed feature vector")
    return tuple(values)


@dataclass(frozen=True)
class SL2Item:
    scenario_group_id: str
    snapshot_id: str
    split: str
    viewer_role: str
    priority_band: int
    candidate_independence_key: str
    gold_rank_group: int
    base_position: int
    feature_schema_hash: str
    source_binding_status: str
    attention_snapshot: dict[str, Any]

    def copy_with(self, **changes: Any) -> "SL2Item":
        return replace(self, **changes)


@dataclass(frozen=True)
class SL2Pair:
    scenario_group_id: str
    snapshot_id: str
    split: str
    viewer_role: str
    priority_band: int
    reason_code: str
    label_kind: str
    left_key: str
    right_key: str
    left_vector: tuple[float, ...]
    right_vector: tuple[float, ...]
    preferred_side: str | None


@dataclass(frozen=True)
class SL2Scenario:
    scenario_group_id: str
    snapshot_id: str
    split: str
    viewer_role: str
    priority_band: int
    reason_code: str
    narrative_variant: str
    counterfactual_group: str | None
    feature_schema_hash: str
    items: tuple[SL2Item, ...]
    strict_pairs: tuple[SL2Pair, ...]
    tie_pairs: tuple[SL2Pair, ...]


@dataclass(frozen=True)
class SL2Dataset:
    scenarios: tuple[SL2Scenario, ...]
    pairs: tuple[SL2Pair, ...]
    feature_schema_sha256: str
    dataset_manifest_sha256: str
    gold_order_sha256: str
    raw_documents: tuple[dict[str, Any], ...]

    def pairs_for(self, *, split: str, viewer_role: str, strict_only: bool = False) -> list[SL2Pair]:
        return [
            pair
            for pair in self.pairs
            if pair.split == split
            and pair.viewer_role == viewer_role
            and (not strict_only or pair.label_kind == "strict")
        ]

    def scenarios_for(self, *, split: str, viewer_role: str) -> list[SL2Scenario]:
        return [
            scenario
            for scenario in self.scenarios
            if scenario.split == split and scenario.viewer_role == viewer_role
        ]

    def counterfactual_pairs(self, viewer_role: str) -> list[tuple[SL2Scenario, SL2Scenario]]:
        grouped: dict[str, list[SL2Scenario]] = defaultdict(list)
        for scenario in self.scenarios:
            if scenario.viewer_role == viewer_role and scenario.counterfactual_group:
                grouped[scenario.counterfactual_group].append(scenario)
        return [
            (rows[0], rows[1])
            for rows in grouped.values()
            if len(rows) == 2
        ]


def compile_pair(left: SL2Item, right: SL2Item, *, scenario: SL2Scenario) -> SL2Pair:
    if left.scenario_group_id != scenario.scenario_group_id or right.scenario_group_id != scenario.scenario_group_id:
        raise DatasetContractError("pair crosses scenario group")
    if left.snapshot_id != right.snapshot_id or left.snapshot_id != scenario.snapshot_id:
        raise DatasetContractError("pair crosses snapshot")
    if left.viewer_role != right.viewer_role or left.viewer_role != scenario.viewer_role:
        raise DatasetContractError("pair crosses role")
    if left.split != right.split or left.split != scenario.split:
        raise DatasetContractError("pair crosses dataset split")
    if left.priority_band != right.priority_band or left.priority_band != scenario.priority_band:
        raise DatasetContractError("pair crosses deterministic priority band")
    if left.candidate_independence_key == right.candidate_independence_key:
        raise DatasetContractError("pair candidates are not independent")
    for item in (left, right):
        snapshot = item.attention_snapshot
        if not snapshot.get("eligible") or not snapshot.get("active_frontier"):
            raise DatasetContractError("pair contains ineligible or inactive candidate")
        if snapshot.get("hard_protected"):
            raise DatasetContractError("hard-protected candidate cannot train")
        if item.source_binding_status not in {"current", "not_applicable"}:
            raise DatasetContractError("pair contains invalid source binding")
        if item.feature_schema_hash != scenario.feature_schema_hash:
            raise DatasetContractError("pair feature schema hash mismatch")
    ordered = sorted((left, right), key=lambda item: item.candidate_independence_key)
    left_item, right_item = ordered
    if left.gold_rank_group == right.gold_rank_group:
        label_kind = "tie"
        preferred_side = None
    else:
        label_kind = "strict"
        preferred = left if left.gold_rank_group < right.gold_rank_group else right
        preferred_side = (
            "left"
            if preferred.candidate_independence_key == left_item.candidate_independence_key
            else "right"
        )
    return SL2Pair(
        scenario_group_id=scenario.scenario_group_id,
        snapshot_id=scenario.snapshot_id,
        split=scenario.split,
        viewer_role=scenario.viewer_role,
        priority_band=scenario.priority_band,
        reason_code=scenario.reason_code,
        label_kind=label_kind,
        left_key=left_item.candidate_independence_key,
        right_key=right_item.candidate_independence_key,
        left_vector=transform_snapshot(left_item.attention_snapshot, strict_dataset=True),
        right_vector=transform_snapshot(right_item.attention_snapshot, strict_dataset=True),
        preferred_side=preferred_side,
    )


def _compile_scenario(base: dict[str, Any], expected_feature_hash: str) -> SL2Scenario:
    required = {
        "label_schema",
        "scenario_group_id",
        "snapshot_id",
        "split",
        "viewer_role",
        "priority_band",
        "reason_code",
        "narrative_variant",
        "counterfactual_group",
        "feature_schema_hash",
        "items",
    }
    if set(base) != required:
        raise DatasetContractError("scenario fields do not match frozen contract")
    if base["label_schema"] != LABEL_SCHEMA_VERSION:
        raise DatasetContractError("label schema mismatch")
    if base["split"] not in {"train", "validation", "test"}:
        raise DatasetContractError("invalid split")
    if base["viewer_role"] not in {"staff", "clinician"}:
        raise DatasetContractError("invalid viewer role")
    if base["reason_code"] not in ALLOWED_REASON_CODES:
        raise DatasetContractError("invalid label reason")
    if base["feature_schema_hash"] != expected_feature_hash:
        raise DatasetContractError("scenario feature schema hash mismatch")
    items: list[SL2Item] = []
    for row in base["items"]:
        if set(row) != {
            "candidate_independence_key",
            "gold_rank_group",
            "base_position",
            "feature_schema_hash",
            "attention_snapshot",
        }:
            raise DatasetContractError("label item fields do not match frozen contract")
        snapshot = row["attention_snapshot"]
        transform_snapshot(snapshot, strict_dataset=True)
        items.append(
            SL2Item(
                scenario_group_id=base["scenario_group_id"],
                snapshot_id=base["snapshot_id"],
                split=base["split"],
                viewer_role=base["viewer_role"],
                priority_band=int(base["priority_band"]),
                candidate_independence_key=row["candidate_independence_key"],
                gold_rank_group=int(row["gold_rank_group"]),
                base_position=int(row["base_position"]),
                feature_schema_hash=row["feature_schema_hash"],
                source_binding_status=snapshot["source_binding_status"],
                attention_snapshot=snapshot,
            )
        )
    if len(items) != 5 or sorted(item.gold_rank_group for item in items) != [1, 2, 3, 4, 4]:
        raise DatasetContractError("each scenario must contain ranks 1,2,3,4,4")
    if sorted(item.base_position for item in items) != [1, 2, 3, 4, 5]:
        raise DatasetContractError("base positions must be a permutation of 1..5")
    shell = SL2Scenario(
        scenario_group_id=base["scenario_group_id"],
        snapshot_id=base["snapshot_id"],
        split=base["split"],
        viewer_role=base["viewer_role"],
        priority_band=int(base["priority_band"]),
        reason_code=base["reason_code"],
        narrative_variant=base["narrative_variant"],
        counterfactual_group=base["counterfactual_group"],
        feature_schema_hash=base["feature_schema_hash"],
        items=tuple(items),
        strict_pairs=(),
        tie_pairs=(),
    )
    by_group: dict[int, list[SL2Item]] = defaultdict(list)
    for item in items:
        by_group[item.gold_rank_group].append(item)
    representatives = [
        sorted(by_group[group], key=lambda item: item.candidate_independence_key)[0]
        for group in sorted(by_group)
    ]
    strict = [
        compile_pair(representatives[left], representatives[right], scenario=shell)
        for left in range(len(representatives))
        for right in range(left + 1, len(representatives))
    ]
    ties = [
        compile_pair(rows[0], rows[1], scenario=shell)
        for rows in by_group.values()
        if len(rows) == 2
    ]
    if len(strict) != 6 or len(ties) != 1:
        raise DatasetContractError("each scenario must compile to six strict and one tie pair")
    return replace(shell, strict_pairs=tuple(strict), tie_pairs=tuple(ties))


def load_sl2_dataset(root: Path | None = None) -> SL2Dataset:
    eval_root = root or (Path(__file__).resolve().parent.parent / "evals" / "sl2")
    feature = json.loads((eval_root / "feature_schema_v1.json").read_text(encoding="utf-8"))
    manifest = json.loads((eval_root / "dataset_manifest_v1.json").read_text(encoding="utf-8"))
    gold = json.loads((eval_root / "gold_order_v1.json").read_text(encoding="utf-8"))
    if tuple(feature.get("ordered_feature_names", ())) != FEATURE_NAMES:
        raise DatasetContractError("ordered feature schema mismatch")
    if feature.get("feature_schema_version") != FEATURE_SCHEMA_VERSION or feature.get(
        "transform_version"
    ) != TRANSFORM_VERSION:
        raise DatasetContractError("feature schema version mismatch")
    feature_hash = canonical_sha256(feature)
    gold_hash = canonical_sha256(gold)
    if manifest.get("dataset_version") != DATASET_VERSION:
        raise DatasetContractError("dataset version mismatch")
    if manifest.get("feature_schema_sha256") != feature_hash:
        raise DatasetContractError("feature schema hash mismatch")
    if manifest.get("gold_order_sha256") != gold_hash:
        raise DatasetContractError("gold order hash mismatch")
    if gold.get("feature_schema_sha256") != feature_hash:
        raise DatasetContractError("gold feature schema hash mismatch")
    scenarios = tuple(
        _compile_scenario(row, feature_hash) for row in gold.get("scenarios", [])
    )
    if len(scenarios) != 30 or manifest.get("scenario_count") != 30:
        raise DatasetContractError("SL2 requires exactly 30 scenario groups")
    ids = [scenario.scenario_group_id for scenario in scenarios]
    if len(set(ids)) != len(ids):
        raise DatasetContractError("duplicate scenario group id")
    declared = {
        (row["scenario_group_id"], row["viewer_role"], row["split"])
        for row in manifest.get("scenarios", [])
    }
    actual = {
        (row.scenario_group_id, row.viewer_role, row.split) for row in scenarios
    }
    if declared != actual:
        raise DatasetContractError("manifest scenario ownership mismatch")
    group_counts = Counter((row.viewer_role, row.split) for row in scenarios)
    expected_groups = {
        ("staff", "train"): 9,
        ("staff", "validation"): 3,
        ("staff", "test"): 3,
        ("clinician", "train"): 9,
        ("clinician", "validation"): 3,
        ("clinician", "test"): 3,
    }
    if group_counts != expected_groups:
        raise DatasetContractError("frozen group split counts do not match")
    pairs = tuple(
        pair
        for scenario in scenarios
        for pair in (*scenario.strict_pairs, *scenario.tie_pairs)
    )
    pair_counts = Counter((pair.split, pair.label_kind) for pair in pairs)
    if pair_counts != {
        ("train", "strict"): 108,
        ("train", "tie"): 18,
        ("validation", "strict"): 36,
        ("validation", "tie"): 6,
        ("test", "strict"): 36,
        ("test", "tie"): 6,
    }:
        raise DatasetContractError("frozen pair counts do not match")
    return SL2Dataset(
        scenarios=scenarios,
        pairs=pairs,
        feature_schema_sha256=feature_hash,
        dataset_manifest_sha256=canonical_sha256(manifest),
        gold_order_sha256=gold_hash,
        raw_documents=(feature, manifest, gold),
    )
