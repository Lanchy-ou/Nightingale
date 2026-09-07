"""SL1 explicit workflow links and deterministic active-frontier derivation.

The module reads and writes identifiers and operational metadata only. It never
copies patient text and ranking callers cannot create Tasks through this API.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from .ids import stable_id
from .models import CareWorkflow, Event, Task, User, WorkflowLink

WORKFLOW_SCHEMA_VERSION = "care-workflow-v1"
TERMINAL_TASK_STATUSES = frozenset({"completed", "cancelled"})
EVENT_TO_TASK_RELATIONS = frozenset({"triggered_review", "triggered_action"})
TASK_TO_TASK_RELATIONS = frozenset(
    {
        "verification_updates",
        "depends_on",
        "requires_action",
        "follow_up_for",
        "superseded_by",
    }
)


class WorkflowValidationError(ValueError):
    pass


@dataclass(frozen=True)
class WorkflowTaskState:
    workflow_status: str
    active_frontier: bool
    terminal: bool
    superseded: bool
    patient_reported_done_pending_verification: bool
    workflow_link_known: bool
    inbound_relation_types: tuple[str, ...]
    outbound_relation_types: tuple[str, ...]
    blocking_predecessor_count: int
    open_downstream_action_count: int
    workflow_blocking_known: bool
    workflow_blocking: bool | None
    parent_context_known: bool
    upstream_verification_known: bool
    upstream_verification_outcome: str | None


def _actor_role(db: Session, task: Task) -> tuple[str, str | None]:
    user = db.get(User, task.created_by)
    if user is not None and user.role in {"staff", "clinician"}:
        return user.role, user.user_id
    return "system", None


def _validate_workflow_scope(db: Session, workflow: CareWorkflow) -> Event:
    root = db.get(Event, workflow.root_event_id)
    if root is None:
        raise WorkflowValidationError("workflow root event is missing")
    if (root.clinic_id, root.patient_id) != (workflow.clinic_id, workflow.patient_id):
        raise WorkflowValidationError("workflow root event is outside workflow scope")
    return root


def ensure_workflow(
    db: Session,
    *,
    workflow_id: str,
    clinic_id: str,
    patient_id: str,
    workflow_kind: str,
    root_event_id: str,
    created_by_role: str,
    created_by_user_id: str | None,
    created_at: datetime,
) -> CareWorkflow:
    existing = db.get(CareWorkflow, workflow_id)
    if existing is not None:
        expected = (clinic_id, patient_id, workflow_kind, root_event_id)
        actual = (
            existing.clinic_id,
            existing.patient_id,
            existing.workflow_kind,
            existing.root_event_id,
        )
        if actual != expected:
            raise WorkflowValidationError("workflow identity conflicts with existing scope or root")
        return existing
    if workflow_kind not in {"patient_report_response", "care_action_chain"}:
        raise WorkflowValidationError("unsupported workflow kind")
    if created_by_role not in {"system", "staff", "clinician"}:
        raise WorkflowValidationError("unsupported workflow creator role")
    root = db.get(Event, root_event_id)
    if root is None or (root.clinic_id, root.patient_id) != (clinic_id, patient_id):
        raise WorkflowValidationError("workflow root event is outside workflow scope")
    if created_by_user_id is not None:
        creator = db.get(User, created_by_user_id)
        if creator is None or creator.clinic_id != clinic_id or creator.role != created_by_role:
            raise WorkflowValidationError("workflow creator is outside workflow scope")
    workflow = CareWorkflow(
        workflow_id=workflow_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        workflow_kind=workflow_kind,
        root_event_id=root_event_id,
        status="active",
        created_by_role=created_by_role,
        created_by_user_id=created_by_user_id,
        created_at=created_at,
        updated_at=created_at,
        completed_at=None,
    )
    db.add(workflow)
    db.flush()
    return workflow


def _task_in_scope(db: Session, workflow: CareWorkflow, task_id: str) -> Task:
    task = db.get(Task, task_id)
    if task is None:
        raise WorkflowValidationError("workflow link Task endpoint is missing")
    if (task.clinic_id, task.patient_id) != (workflow.clinic_id, workflow.patient_id):
        raise WorkflowValidationError("workflow link crosses clinic or patient scope")
    if task.workflow_id != workflow.workflow_id:
        raise WorkflowValidationError("workflow link Task endpoint belongs to another workflow")
    return task


def _would_create_cycle(
    db: Session, workflow_id: str, from_task_id: str, to_task_id: str
) -> bool:
    adjacency: dict[str, set[str]] = {}
    links = db.scalars(
        select(WorkflowLink).where(
            WorkflowLink.workflow_id == workflow_id,
            WorkflowLink.from_type == "task",
        )
    ).all()
    for link in links:
        adjacency.setdefault(link.from_id, set()).add(link.to_id)
    adjacency.setdefault(from_task_id, set()).add(to_task_id)
    stack = [to_task_id]
    seen: set[str] = set()
    while stack:
        node = stack.pop()
        if node == from_task_id:
            return True
        if node in seen:
            continue
        seen.add(node)
        stack.extend(adjacency.get(node, ()))
    return False


def create_workflow_link(
    db: Session,
    *,
    workflow: CareWorkflow,
    from_type: str,
    from_id: str,
    relation_type: str,
    to_id: str,
    created_by_role: str,
    created_by_user_id: str | None,
    created_at: datetime,
) -> WorkflowLink:
    """Validate and idempotently create one typed edge."""
    _validate_workflow_scope(db, workflow)
    target_task: Task
    if from_type == "event":
        if relation_type not in EVENT_TO_TASK_RELATIONS:
            raise WorkflowValidationError("invalid Event-to-Task relation")
        if from_id != workflow.root_event_id:
            raise WorkflowValidationError("Event link must start at the workflow root")
        target_task = _task_in_scope(db, workflow, to_id)
        if relation_type == "triggered_review" and target_task.task_kind not in {
            "patient_report_review",
            "clinician_priority_review",
            "result_review",
        }:
            raise WorkflowValidationError("triggered_review requires a review Task")
        if relation_type == "triggered_action" and target_task.task_kind in {
            "patient_report_review",
            "clinician_priority_review",
            "result_review",
        }:
            raise WorkflowValidationError("triggered_action cannot target a review Task")
    elif from_type == "task":
        if relation_type not in TASK_TO_TASK_RELATIONS:
            raise WorkflowValidationError("invalid Task-to-Task relation")
        source_task = _task_in_scope(db, workflow, from_id)
        if from_id == to_id:
            raise WorkflowValidationError("workflow self-link is not allowed")
        target_task = _task_in_scope(db, workflow, to_id)
        if relation_type == "verification_updates" and not (
            source_task.task_kind == "patient_report_review"
            and source_task.assigned_role == "staff"
            and target_task.task_kind == "clinician_priority_review"
            and target_task.assigned_role == "clinician"
        ):
            raise WorkflowValidationError(
                "verification_updates requires Nurse review -> clinician review"
            )
        if relation_type == "requires_action" and not (
            source_task.task_kind == "clinician_priority_review"
            and target_task.task_kind == "care_action"
            and target_task.assigned_role in {"staff", "clinician"}
        ):
            raise WorkflowValidationError(
                "requires_action requires clinician review -> clinical-role Care Task"
            )
    else:
        raise WorkflowValidationError("unsupported workflow source node type")
    if from_type == "task" and _would_create_cycle(
        db, workflow.workflow_id, from_id, to_id
    ):
        raise WorkflowValidationError("workflow link would create a directed cycle")
    if created_by_role not in {"system", "staff", "clinician"}:
        raise WorkflowValidationError("unsupported workflow link creator role")
    if created_by_user_id is not None:
        creator = db.get(User, created_by_user_id)
        if (
            creator is None
            or creator.clinic_id != workflow.clinic_id
            or creator.role != created_by_role
        ):
            raise WorkflowValidationError("workflow link creator is outside workflow scope")
    existing = db.scalar(
        select(WorkflowLink).where(
            WorkflowLink.workflow_id == workflow.workflow_id,
            WorkflowLink.from_type == from_type,
            WorkflowLink.from_id == from_id,
            WorkflowLink.relation_type == relation_type,
            WorkflowLink.to_type == "task",
            WorkflowLink.to_id == to_id,
        )
    )
    if existing is not None:
        return existing
    link = WorkflowLink(
        link_id=f"wln_{stable_id(workflow.workflow_id, from_type, from_id, relation_type, 'task', to_id)}",
        workflow_id=workflow.workflow_id,
        clinic_id=workflow.clinic_id,
        patient_id=workflow.patient_id,
        from_type=from_type,
        from_id=from_id,
        relation_type=relation_type,
        to_type="task",
        to_id=to_id,
        created_by_role=created_by_role,
        created_by_user_id=created_by_user_id,
        created_at=created_at,
    )
    db.add(link)
    db.flush()
    return link


def ensure_task_workflow(
    db: Session,
    task: Task,
    *,
    created_by_role: str | None = None,
    created_by_user_id: str | None = None,
    workflow_kind: str | None = None,
) -> CareWorkflow:
    """Give a Task one explicit workflow and root trigger without guessing."""
    role, user_id = _actor_role(db, task)
    role = created_by_role or role
    user_id = created_by_user_id if created_by_role is not None else user_id
    kind = workflow_kind or (
        "patient_report_response"
        if task.task_kind in {"patient_report_review", "clinician_priority_review"}
        else "care_action_chain"
    )
    workflow_id = task.workflow_id or f"wf_{stable_id(task.task_id, WORKFLOW_SCHEMA_VERSION)}"
    task.workflow_id = workflow_id
    db.add(task)
    workflow = ensure_workflow(
        db,
        workflow_id=workflow_id,
        clinic_id=task.clinic_id,
        patient_id=task.patient_id,
        workflow_kind=kind,
        root_event_id=task.event_id,
        created_by_role=role,
        created_by_user_id=user_id,
        created_at=task.created_at,
    )
    relation = (
        "triggered_review"
        if task.task_kind in {"patient_report_review", "clinician_priority_review"}
        else "triggered_action"
    )
    create_workflow_link(
        db,
        workflow=workflow,
        from_type="event",
        from_id=workflow.root_event_id,
        relation_type=relation,
        to_id=task.task_id,
        created_by_role=role,
        created_by_user_id=user_id,
        created_at=task.created_at,
    )
    return workflow


def attach_task_to_workflow(
    db: Session,
    *,
    task: Task,
    workflow: CareWorkflow,
    relation_from_task_id: str,
    relation_type: str,
    created_by_role: str,
    created_by_user_id: str | None,
    created_at: datetime,
) -> WorkflowLink:
    """Move a singleton Task workflow into an explicit downstream branch."""
    if (task.clinic_id, task.patient_id) != (workflow.clinic_id, workflow.patient_id):
        raise WorkflowValidationError("downstream Task crosses workflow scope")
    if task.workflow_id and task.workflow_id != workflow.workflow_id:
        old_id = task.workflow_id
        siblings = db.scalars(select(Task).where(Task.workflow_id == old_id)).all()
        if any(item.task_id != task.task_id for item in siblings):
            raise WorkflowValidationError("downstream Task belongs to a non-singleton workflow")
        db.execute(delete(WorkflowLink).where(WorkflowLink.workflow_id == old_id))
        db.execute(delete(CareWorkflow).where(CareWorkflow.workflow_id == old_id))
    task.workflow_id = workflow.workflow_id
    db.add(task)
    db.flush()
    return create_workflow_link(
        db,
        workflow=workflow,
        from_type="task",
        from_id=relation_from_task_id,
        relation_type=relation_type,
        to_id=task.task_id,
        created_by_role=created_by_role,
        created_by_user_id=created_by_user_id,
        created_at=created_at,
    )


def derive_task_workflow_state(
    db: Session, task: Task, *, as_of: datetime
) -> WorkflowTaskState:
    terminal = task.status in TERMINAL_TASK_STATUSES
    reported_pending = task.status == "reported_done"
    workflow = db.get(CareWorkflow, task.workflow_id) if task.workflow_id else None
    if workflow is None or (
        workflow.clinic_id,
        workflow.patient_id,
    ) != (task.clinic_id, task.patient_id):
        return WorkflowTaskState(
            workflow_status="not_applicable",
            active_frontier=False,
            terminal=terminal,
            superseded=False,
            patient_reported_done_pending_verification=reported_pending,
            workflow_link_known=False,
            inbound_relation_types=(),
            outbound_relation_types=(),
            blocking_predecessor_count=0,
            open_downstream_action_count=0,
            workflow_blocking_known=False,
            workflow_blocking=None,
            parent_context_known=False,
            upstream_verification_known=False,
            upstream_verification_outcome=None,
        )
    inbound = db.scalars(
        select(WorkflowLink).where(
            WorkflowLink.workflow_id == workflow.workflow_id,
            WorkflowLink.to_id == task.task_id,
        )
    ).all()
    outbound = db.scalars(
        select(WorkflowLink).where(
            WorkflowLink.workflow_id == workflow.workflow_id,
            WorkflowLink.from_type == "task",
            WorkflowLink.from_id == task.task_id,
        )
    ).all()
    link_known = bool(inbound)
    blocking = []
    verification_sources: list[Task] = []
    for link in inbound:
        if link.from_type != "task":
            continue
        source = db.get(Task, link.from_id)
        if source is None:
            continue
        if link.relation_type == "depends_on" and source.status not in TERMINAL_TASK_STATUSES:
            blocking.append(source)
        if link.relation_type == "verification_updates":
            verification_sources.append(source)
    superseded = any(link.relation_type == "superseded_by" for link in outbound)
    open_downstream = 0
    for link in outbound:
        if link.relation_type != "requires_action":
            continue
        target = db.get(Task, link.to_id)
        if target is not None and target.status not in TERMINAL_TASK_STATUSES:
            open_downstream += 1
    verification_outcome = None
    verification_known = False
    for source in verification_sources:
        if (
            source.status in TERMINAL_TASK_STATUSES
            and source.verification_outcome in {"verified", "corrected", "unable_to_verify"}
        ):
            verification_outcome = source.verification_outcome
            verification_known = True
            break
    active = bool(
        link_known
        and workflow.status == "active"
        and not terminal
        and not superseded
        and not blocking
    )
    return WorkflowTaskState(
        workflow_status=workflow.status,
        active_frontier=active,
        terminal=terminal,
        superseded=superseded,
        patient_reported_done_pending_verification=reported_pending,
        workflow_link_known=link_known,
        inbound_relation_types=tuple(sorted({link.relation_type for link in inbound})),
        outbound_relation_types=tuple(sorted({link.relation_type for link in outbound})),
        blocking_predecessor_count=len(blocking),
        open_downstream_action_count=open_downstream,
        workflow_blocking_known=link_known,
        workflow_blocking=bool(blocking) if link_known else None,
        parent_context_known=bool(inbound),
        upstream_verification_known=verification_known,
        upstream_verification_outcome=verification_outcome,
    )


def refresh_workflow_status(
    db: Session, workflow_id: str, *, as_of: datetime
) -> CareWorkflow | None:
    workflow = db.get(CareWorkflow, workflow_id)
    if workflow is None or workflow.status == "cancelled":
        return workflow
    tasks = db.scalars(select(Task).where(Task.workflow_id == workflow_id)).all()
    links = db.scalars(
        select(WorkflowLink).where(WorkflowLink.workflow_id == workflow_id)
    ).all()
    superseded_sources = {
        link.from_id
        for link in links
        if link.from_type == "task" and link.relation_type == "superseded_by"
    }
    current = [task for task in tasks if task.task_id not in superseded_sources]
    incomplete_actions = False
    for source in current:
        if source.review_outcome != "action_required":
            continue
        targets = [
            db.get(Task, link.to_id)
            for link in links
            if link.from_type == "task"
            and link.from_id == source.task_id
            and link.relation_type == "requires_action"
        ]
        if not targets or any(
            target is None or target.status not in TERMINAL_TASK_STATUSES
            for target in targets
        ):
            incomplete_actions = True
    completed = bool(current) and all(
        task.status in TERMINAL_TASK_STATUSES for task in current
    ) and not incomplete_actions
    from .result_models import TestOrder, TestReview, TestReport
    from .test_result_service import stage
    order = db.scalar(select(TestOrder).where(TestOrder.workflow_id == workflow_id))
    if order is not None:
        reviews = db.scalars(select(TestReview).join(TestReport).where(TestReport.order_id == order.order_id)).all()
        followups = [db.get(Task, r.follow_up_task_id) for r in reviews if r.follow_up_task_id]
        completed = completed and stage(db, order) in {"completed", "cancelled"} and all(t and t.status in TERMINAL_TASK_STATUSES for t in followups)
    desired = "completed" if completed else "active"
    if workflow.status != desired or (not completed and workflow.completed_at is not None):
        workflow.status = desired
        workflow.completed_at = as_of if completed else None
        workflow.updated_at = as_of
        db.add(workflow)
    return workflow


def backfill_workflows(db: Session) -> dict[str, int]:
    """Idempotently convert legacy Task.workflow_id strings into explicit chains."""
    tasks = db.scalars(select(Task).order_by(Task.task_id)).all()
    grouped: dict[str, list[Task]] = {}
    for task in tasks:
        key = task.workflow_id or f"wf_{stable_id(task.task_id, WORKFLOW_SCHEMA_VERSION)}"
        task.workflow_id = key
        db.add(task)
        grouped.setdefault(key, []).append(task)
    db.flush()
    for workflow_id, members in sorted(grouped.items()):
        scopes = {(task.clinic_id, task.patient_id) for task in members}
        if len(scopes) != 1:
            raise WorkflowValidationError("legacy workflow spans clinic or patient scope")
        review_tasks = [
            task
            for task in members
            if task.task_kind in {"patient_report_review", "clinician_priority_review"}
        ]
        root_candidates = {task.event_id for task in (review_tasks or members)}
        if len(root_candidates) != 1:
            raise WorkflowValidationError("legacy workflow has incompatible root Events")
        root_event_id = next(iter(root_candidates))
        first = min(members, key=lambda item: (item.created_at, item.task_id))
        role, user_id = _actor_role(db, first)
        kind = "patient_report_response" if review_tasks else "care_action_chain"
        workflow = ensure_workflow(
            db,
            workflow_id=workflow_id,
            clinic_id=first.clinic_id,
            patient_id=first.patient_id,
            workflow_kind=kind,
            root_event_id=root_event_id,
            created_by_role=role,
            created_by_user_id=user_id,
            created_at=first.created_at,
        )
        follow_up_targets = {
            task.follow_up_task_id for task in members if task.follow_up_task_id
        }
        for task in members:
            if task.task_id in follow_up_targets:
                continue
            relation = (
                "triggered_review"
                if task.task_kind in {"patient_report_review", "clinician_priority_review"}
                else "triggered_action"
            )
            create_workflow_link(
                db,
                workflow=workflow,
                from_type="event",
                from_id=workflow.root_event_id,
                relation_type=relation,
                to_id=task.task_id,
                created_by_role=role,
                created_by_user_id=user_id,
                created_at=task.created_at,
            )
        staff = next((task for task in members if task.task_kind == "patient_report_review"), None)
        clinician = next(
            (task for task in members if task.task_kind == "clinician_priority_review"),
            None,
        )
        if staff is not None and clinician is not None:
            create_workflow_link(
                db,
                workflow=workflow,
                from_type="task",
                from_id=staff.task_id,
                relation_type="verification_updates",
                to_id=clinician.task_id,
                created_by_role="system",
                created_by_user_id=None,
                created_at=max(staff.created_at, clinician.created_at),
            )
    db.flush()
    for source in tasks:
        if source.follow_up_task_id is None:
            continue
        target = db.get(Task, source.follow_up_task_id)
        workflow = db.get(CareWorkflow, source.workflow_id)
        if target is None or workflow is None:
            raise WorkflowValidationError("legacy follow-up link endpoint is missing")
        role, user_id = _actor_role(db, source)
        attach_task_to_workflow(
            db,
            task=target,
            workflow=workflow,
            relation_from_task_id=source.task_id,
            relation_type="requires_action",
            created_by_role=role,
            created_by_user_id=user_id,
            created_at=source.updated_at,
        )
    db.flush()
    for workflow_id in sorted(grouped):
        refresh_workflow_status(db, workflow_id, as_of=datetime.now())
    return {
        "workflow_count": len(db.scalars(select(CareWorkflow.workflow_id)).all()),
        "link_count": len(db.scalars(select(WorkflowLink.link_id)).all()),
        "task_count": len(tasks),
    }
