from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import select

from app.models import CareWorkflow, Task, WorkflowLink
from app.db import engine, migrate_sl1_schema
from app.workflow_state import (
    WorkflowValidationError,
    attach_task_to_workflow,
    create_workflow_link,
    derive_task_workflow_state,
    ensure_task_workflow,
)
from seed import fixture


def _new_task(db_session, *, task_id: str, assigned_role: str, task_kind: str = "care_action"):
    source = db_session.get(Task, fixture.TASK_BLOOD_TEST)
    task = Task(
        task_id=task_id,
        patient_id=source.patient_id,
        clinic_id=source.clinic_id,
        event_id=source.event_id,
        source_artifact_id=None,
        source_span=None,
        title="Synthetic SL1 workflow probe",
        description="Metadata-only deterministic workflow probe.",
        task_kind=task_kind,
        workflow_id=None,
        attention_class="routine",
        creation_method="human",
        verification_outcome="not_required",
        routing_metadata={},
        assigned_role=assigned_role,
        assigned_user_id=None,
        patient_visible=False,
        status="open",
        due_at=None,
        created_by=fixture.USER_CLINICIAN_ID,
        created_at=datetime(2026, 9, 2, 11, 0),
        updated_at=datetime(2026, 9, 2, 11, 0),
    )
    db_session.add(task)
    db_session.flush()
    ensure_task_workflow(db_session, task)
    return task


def test_seeded_tasks_have_one_root_and_explicit_trigger_links(db_session):
    tasks = db_session.scalars(select(Task)).all()
    assert tasks
    for task in tasks:
        workflow = db_session.get(CareWorkflow, task.workflow_id)
        assert workflow is not None
        assert (workflow.clinic_id, workflow.patient_id) == (
            task.clinic_id,
            task.patient_id,
        )
        inbound = db_session.scalars(
            select(WorkflowLink).where(
                WorkflowLink.workflow_id == workflow.workflow_id,
                WorkflowLink.to_id == task.task_id,
            )
        ).all()
        assert inbound


def test_cycle_link_is_rejected_without_committing_an_edge(db_session):
    task = db_session.get(Task, fixture.TASK_BLOOD_TEST)
    workflow = db_session.get(CareWorkflow, task.workflow_id)
    second = _new_task(
        db_session, task_id="task_sl1_cycle_probe", assigned_role="staff"
    )
    attach_task_to_workflow(
        db_session,
        task=second,
        workflow=workflow,
        relation_from_task_id=task.task_id,
        relation_type="follow_up_for",
        created_by_role="clinician",
        created_by_user_id=fixture.USER_CLINICIAN_ID,
        created_at=datetime(2026, 9, 2, 12, 0),
    )
    with pytest.raises(WorkflowValidationError, match="cycle"):
        create_workflow_link(
            db_session,
            workflow=workflow,
            from_type="task",
            from_id=second.task_id,
            relation_type="depends_on",
            to_id=task.task_id,
            created_by_role="clinician",
            created_by_user_id=fixture.USER_CLINICIAN_ID,
            created_at=datetime(2026, 9, 2, 12, 0),
        )


def test_blocking_nonblocking_and_superseded_links_have_distinct_state(db_session):
    source = _new_task(
        db_session,
        task_id="task_sl1_nurse_review",
        assigned_role="staff",
        task_kind="patient_report_review",
    )
    workflow = db_session.get(CareWorkflow, source.workflow_id)
    blocked = _new_task(
        db_session, task_id="task_sl1_blocked", assigned_role="patient"
    )
    nonblocking = _new_task(
        db_session,
        task_id="task_sl1_nonblocking",
        assigned_role="clinician",
        task_kind="clinician_priority_review",
    )
    replacement = _new_task(
        db_session,
        task_id="task_sl1_replacement",
        assigned_role="clinician",
        task_kind="follow_up_action",
    )
    for task, relation in ((blocked, "depends_on"), (nonblocking, "verification_updates")):
        attach_task_to_workflow(
            db_session,
            task=task,
            workflow=workflow,
            relation_from_task_id=source.task_id,
            relation_type=relation,
            created_by_role="clinician",
            created_by_user_id=fixture.USER_CLINICIAN_ID,
            created_at=datetime(2026, 9, 2, 12, 0),
        )
    nonblocking_before_replacement = derive_task_workflow_state(
        db_session, nonblocking, as_of=datetime(2026, 9, 2, 12, 0)
    )
    assert nonblocking_before_replacement.active_frontier is True
    assert nonblocking_before_replacement.workflow_blocking is False
    attach_task_to_workflow(
        db_session,
        task=replacement,
        workflow=workflow,
        relation_from_task_id=nonblocking.task_id,
        relation_type="superseded_by",
        created_by_role="clinician",
        created_by_user_id=fixture.USER_CLINICIAN_ID,
        created_at=datetime(2026, 9, 2, 12, 0),
    )
    blocked_state = derive_task_workflow_state(
        db_session, blocked, as_of=datetime(2026, 9, 2, 12, 0)
    )
    nonblocking_state = derive_task_workflow_state(
        db_session, nonblocking, as_of=datetime(2026, 9, 2, 12, 0)
    )
    replacement_state = derive_task_workflow_state(
        db_session, replacement, as_of=datetime(2026, 9, 2, 12, 0)
    )
    assert blocked_state.active_frontier is False
    assert blocked_state.workflow_blocking is True
    assert nonblocking_state.superseded is True
    assert nonblocking_state.active_frontier is False
    assert replacement_state.active_frontier is True


def test_missing_and_cross_scope_link_endpoints_fail_closed(db_session):
    task = db_session.get(Task, fixture.TASK_BLOOD_TEST)
    workflow = db_session.get(CareWorkflow, task.workflow_id)
    with pytest.raises(WorkflowValidationError, match="missing"):
        create_workflow_link(
            db_session,
            workflow=workflow,
            from_type="task",
            from_id=task.task_id,
            relation_type="follow_up_for",
            to_id="task_missing",
            created_by_role="clinician",
            created_by_user_id=fixture.USER_CLINICIAN_ID,
            created_at=datetime(2026, 9, 2, 12, 0),
        )
    other = Task(
        task_id="task_sl1_cross_scope",
        patient_id=fixture.PATIENT_OTHER_ID,
        clinic_id=fixture.CLINIC_B_ID,
        event_id=fixture.EVT_LEAH_DOCTOR,
        source_artifact_id=None,
        source_span=None,
        title="Cross-scope probe",
        description="Metadata-only validation probe.",
        task_kind="care_action",
        workflow_id=None,
        attention_class="routine",
        creation_method="human",
        verification_outcome="not_required",
        routing_metadata={},
        assigned_role="clinician",
        assigned_user_id=fixture.USER_CLINICIAN_B_ID,
        patient_visible=False,
        status="open",
        due_at=None,
        created_by=fixture.USER_CLINICIAN_B_ID,
        created_at=datetime(2026, 9, 2, 11, 0),
        updated_at=datetime(2026, 9, 2, 11, 0),
    )
    db_session.add(other)
    db_session.flush()
    with pytest.raises(WorkflowValidationError, match="crosses"):
        create_workflow_link(
            db_session,
            workflow=workflow,
            from_type="task",
            from_id=task.task_id,
            relation_type="follow_up_for",
            to_id=other.task_id,
            created_by_role="clinician",
            created_by_user_id=fixture.USER_CLINICIAN_ID,
            created_at=datetime(2026, 9, 2, 12, 0),
        )


def test_reported_done_remains_on_active_frontier(db_session):
    task = db_session.get(Task, fixture.TASK_MAYA_BP_LOG)
    assert task.status == "reported_done"
    state = derive_task_workflow_state(
        db_session, task, as_of=datetime(2026, 9, 2, 12, 0)
    )
    assert state.terminal is False
    assert state.active_frontier is True
    assert state.patient_reported_done_pending_verification is True


def test_sl1_migration_is_additive_and_idempotent(db_session):
    before = (
        db_session.query(CareWorkflow).count(),
        db_session.query(WorkflowLink).count(),
        db_session.query(Task).count(),
    )
    db_session.commit()
    migrate_sl1_schema(engine)
    migrate_sl1_schema(engine)
    db_session.expire_all()
    after = (
        db_session.query(CareWorkflow).count(),
        db_session.query(WorkflowLink).count(),
        db_session.query(Task).count(),
    )
    assert after == before
