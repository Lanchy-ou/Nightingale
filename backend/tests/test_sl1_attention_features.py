from __future__ import annotations

from datetime import datetime

from app.attention_items import FEATURE_SCHEMA_VERSION, build_attention_items
from seed import fixture


def test_attention_feature_v1_is_complete_content_free_and_explicit_about_missingness(
    db_session,
):
    items = build_attention_items(
        db_session,
        patient_id=fixture.PATIENT_ID,
        viewer_role="clinician",
        as_of=datetime(2026, 9, 2, 12, 0),
    )
    assert items
    snapshots = [item.factor_snapshot() for item in items]
    assert {snapshot["schema_version"] for snapshot in snapshots} == {
        FEATURE_SCHEMA_VERSION
    }
    required = {
        "candidate_id",
        "source_kind",
        "source_id",
        "clinic_id",
        "patient_id",
        "event_id",
        "workflow_id",
        "workflow_root_event_id",
        "workflow_group_key",
        "independence_key",
        "viewer_role",
        "attention_kind",
        "due_known",
        "due_at",
        "overdue",
        "role_route_known",
        "workflow_link_known",
        "source_binding_status",
        "exact_span_available",
        "hard_protected",
        "protection_reasons",
        "base_importance_score",
        "decay_adjustment",
        "adaptive_adjustment",
        "final_score",
    }
    assert all(required <= set(snapshot) for snapshot in snapshots)
    assert all(
        not ({"text", "quote", "title", "description", "content", "comment"} & set(snapshot))
        for snapshot in snapshots
    )
    unknown_due = next(snapshot for snapshot in snapshots if snapshot["due_known"] is False)
    assert unknown_due["due_at"] is None
    assert unknown_due["overdue"] is None
    assert unknown_due["time_to_due_seconds"] is None


def test_task_level_candidate_does_not_pretend_to_have_an_exact_span(db_session):
    items = build_attention_items(
        db_session,
        patient_id=fixture.PATIENT_TASK_ID,
        viewer_role="staff",
        as_of=datetime(2026, 9, 2, 12, 0),
    )
    task_item = next(item for item in items if item.source_kind == "task")
    snapshot = task_item.factor_snapshot()
    assert snapshot["source_binding_status"] in {"current", "not_applicable"}
    if snapshot["source_binding_status"] == "not_applicable":
        assert snapshot["exact_span_available"] is False
