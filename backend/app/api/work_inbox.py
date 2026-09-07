"""Clinic-scoped projection over existing Tasks; no second task store."""
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.orm import Session

from ..authz import authorize, require_auth
from ..db import get_db
from ..models import Event, Patient, PatientCheckInSession, Task
from ..role_context import RoleContext

router = APIRouter(prefix="/api", tags=["work inbox"])


@router.get("/work-inbox")
def work_inbox(view: Literal["mine", "clinic"] = "mine", offset: int = Query(0, ge=0),
               limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db),
               ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "read_work_inbox", ctx.clinic_id, None)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    assigned = and_(Task.assigned_role == ctx.role, or_(Task.assigned_user_id.is_(None), Task.assigned_user_id == ctx.user_id))
    verification = and_(Task.task_kind == "care_action", Task.assigned_role == "patient", Task.status == "reported_done")
    shared = and_(or_(Task.escalated_at.is_not(None), Task.routing_metadata["shared_clinician_queue"].as_boolean() == True), ctx.role == "clinician")
    actionable = or_(assigned, verification, shared)
    hidden = select(PatientCheckInSession.event_id).where(PatientCheckInSession.status.not_in(["submitted", "safety_escalated"]))
    query = select(Task, Patient.name).join(Event, and_(Event.event_id == Task.event_id, Event.patient_id == Task.patient_id)).join(Patient, Patient.patient_id == Task.patient_id).where(
        Task.clinic_id == ctx.clinic_id, Event.clinic_id == ctx.clinic_id, Patient.clinic_id == ctx.clinic_id,
        Task.status.in_(["open", "in_progress", "reported_done"]), Task.event_id.not_in(hidden),
    )
    if view == "mine":
        query = query.where(actionable)
    from ..test_result_service import utc
    rows = db.execute(query).all()
    total = len(rows)
    def deadline(task):
        return task.due_at if task.due_at is None or (task.routing_metadata or {}).get("due_timezone") == "UTC" else utc(db, task.clinic_id, task.due_at)
    def ordering(row):
        task = row[0]
        due = deadline(task)
        rank = 0 if task.task_kind == "clinician_priority_review" else 1 if task.status == "reported_done" else 2 if due and due <= now else 3
        return rank, due or datetime.max, task.created_at, task.task_id
    rows.sort(key=ordering)
    items = []
    for task, patient_name in rows[offset:offset + limit]:
        due = deadline(task)
        can_act = (task.assigned_role == ctx.role and task.assigned_user_id in {None, ctx.user_id}) or (
            task.task_kind == "care_action" and task.assigned_role == "patient" and task.status == "reported_done")
        can_act = bool(can_act or (ctx.role == "clinician" and (task.escalated_at is not None or (task.routing_metadata or {}).get("shared_clinician_queue"))))
        items.append(dict(task_id=task.task_id, patient_id=task.patient_id, patient_name=patient_name,
                          event_id=task.event_id, title=task.title, task_kind=task.task_kind,
                          status=task.status, assigned_role=task.assigned_role, assigned_user_id=task.assigned_user_id,
                          due_at=due.replace(tzinfo=timezone.utc) if due else None, overdue=bool(due and due <= now and task.status in {"open", "in_progress"}),
                          actionable=can_act, has_exact_source=task.source_artifact_id is not None and task.source_span is not None))
        if task.task_kind in {"report_followup", "result_review", "result_communication"}:
            items[-1]["test_order_id"] = (task.routing_metadata or {}).get("test_order_id")
    return {"items": items, "total": total, "offset": offset, "limit": limit, "as_of": now}
