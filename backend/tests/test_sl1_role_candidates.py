from __future__ import annotations

from datetime import datetime

from sqlalchemy import delete

from app.attention_items import build_attention_items
from app.models import WorkflowLink
from seed import fixture


def _by_task(db_session, patient_id: str, role: str):
    return {
        item.source_id: item
        for item in build_attention_items(
            db_session,
            patient_id=patient_id,
            viewer_role=role,
            as_of=datetime(2026, 9, 2, 12, 0),
        )
        if item.source_kind == "task"
    }


def test_clinician_created_nurse_task_routes_only_to_nurse_queue(db_session):
    staff = _by_task(db_session, fixture.PATIENT_TASK_ID, "staff")
    clinician = _by_task(db_session, fixture.PATIENT_TASK_ID, "clinician")
    staff_item = staff[fixture.TASK_MAYA_LAB_REVIEW]
    clinician_item = clinician[fixture.TASK_MAYA_LAB_REVIEW]
    assert staff_item.eligible is True
    assert staff_item.assigned_to_viewer_role is True
    assert clinician_item.eligible is False
    assert clinician_item.exclusion_reason == "other_role_queue"


def test_non_task_highlight_with_unknown_route_is_auditable_for_both_roles(db_session):
    for role in ("staff", "clinician"):
        items = build_attention_items(
            db_session,
            patient_id=fixture.PATIENT_ID,
            viewer_role=role,
            as_of=datetime(2026, 9, 2, 12, 0),
        )
        generic = next(item for item in items if item.source_kind == "highlight")
        assert generic.role_route_known is False
        assert generic.responsible_role is None


def test_missing_explicit_workflow_link_is_recorded_as_an_exclusion(db_session):
    db_session.execute(
        delete(WorkflowLink).where(WorkflowLink.to_id == fixture.TASK_MAYA_LAB_REVIEW)
    )
    item = _by_task(db_session, fixture.PATIENT_TASK_ID, "staff")[
        fixture.TASK_MAYA_LAB_REVIEW
    ]
    assert item.eligible is False
    assert item.exclusion_reason == "workflow_link_incomplete"
