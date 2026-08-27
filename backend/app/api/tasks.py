"""First-class D2 care-task endpoints."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Body, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, authorize_scope, require_auth, resource_not_found
from ..checkin_visibility import require_checkin_event_visible
from ..copilot_confirmation import audit_details, validate_confirmation_token
from ..db import get_db
from ..ids import new_id
from ..models import Artifact, Event, Patient, Task, User
from ..role_context import RoleContext
from ..schemas import (
    ArtifactOut,
    ClinicalTaskOut,
    EventBrief,
    PatientTaskOut,
    TaskCreate,
    TaskProvenanceOut,
    TaskTransition,
)
from ..tasks import link_task_highlight, recompute_task_highlights, resolve_exact_span, task_transitions

router = APIRouter(prefix="/api", tags=["tasks"])


def _validate(schema, body: object):
    try:
        return schema.model_validate(body)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail="Invalid task request") from exc


def _patient_projection(task: Task) -> PatientTaskOut:
    return PatientTaskOut.model_validate(task)


def _task_response(task: Task, ctx: RoleContext):
    if ctx.role == "patient":
        return _patient_projection(task).model_dump(mode="json")
    return ClinicalTaskOut.model_validate(task).model_dump(mode="json")


def _patient_can_see(ctx: RoleContext, task: Task) -> bool:
    return bool(
        ctx.role == "patient"
        and task.patient_visible
        and task.assigned_role == "patient"
        and task.assigned_user_id == ctx.user_id
        and task.patient_id == ctx.patient_id
    )


def _assignment(db: Session, body: TaskCreate, event: Event) -> str | None:
    user = db.get(User, body.assigned_user_id) if body.assigned_user_id else None
    if body.assigned_role == "patient" and user is None and body.assigned_user_id is None:
        matches = db.scalars(
            select(User).where(
                User.clinic_id == event.clinic_id,
                User.role == "patient",
                User.patient_id == event.patient_id,
            )
        ).all()
        if len(matches) != 1:
            raise HTTPException(status_code=422, detail="Invalid task assignment")
        user = matches[0]
    if body.assigned_user_id and (
        user is None or user.clinic_id != event.clinic_id or user.role != body.assigned_role
    ):
        raise HTTPException(status_code=422, detail="Invalid task assignment")
    if body.assigned_role == "patient":
        if user is None or user.patient_id != event.patient_id or not body.patient_visible:
            raise HTTPException(status_code=422, detail="Invalid task assignment")
    return user.user_id if user is not None else None


def _provenance(db: Session, body: TaskCreate, event: Event) -> None:
    if body.source_artifact_id is None:
        return
    artifact = db.get(Artifact, body.source_artifact_id)
    if artifact is None or artifact.event_id != event.event_id:
        raise HTTPException(status_code=422, detail="Invalid task provenance")
    if resolve_exact_span(artifact.content, body.source_span or {}) is None:
        raise HTTPException(status_code=422, detail="Invalid task provenance")


@router.post("/events/{event_id}/tasks")
def create_task(
    event_id: str,
    body: object = Body(...),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = db.get(Event, event_id)
    if event is None:
        raise resource_not_found()
    # Scope and permission precede all request-content/assignment/provenance branches.
    authorize(ctx, "create_task", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event_id)
    parsed = _validate(TaskCreate, body)
    confirmation = validate_confirmation_token(
        parsed.confirmation_token,
        db=db,
        ctx=ctx,
        event=event,
        expected_type="task",
        content={"title": parsed.title, "description": parsed.description},
    )
    if confirmation is not None:
        source = confirmation.evidence[0]
        if (
            parsed.assigned_role != "clinician"
            or parsed.assigned_user_id is not None
            or parsed.patient_visible
            or parsed.source_artifact_id != source.get("artifact_id")
            or parsed.source_span != source.get("span")
        ):
            raise HTTPException(status_code=422, detail="Copilot task confirmation does not match server draft")
    assigned_user_id = _assignment(db, parsed, event)
    _provenance(db, parsed, event)

    now = datetime.now()
    task = Task(
        task_id=new_id("tsk"),
        patient_id=event.patient_id,
        clinic_id=event.clinic_id,
        event_id=event.event_id,
        source_artifact_id=parsed.source_artifact_id,
        source_span=parsed.source_span,
        title=parsed.title,
        description=parsed.description,
        assigned_role=parsed.assigned_role,
        assigned_user_id=assigned_user_id,
        patient_visible=parsed.patient_visible,
        status="open",
        due_at=parsed.due_at,
        created_by=ctx.user_id,
        created_at=now,
        updated_at=now,
        reported_done_at=None,
        completed_by=None,
        completed_at=None,
        cancelled_by=None,
        cancelled_at=None,
    )
    db.add(task)
    db.flush()
    link_task_highlight(db, task)
    # autoflush is disabled project-wide: persist the adopted/dedicated
    # highlight row so recompute_task_highlights can see the new mapping.
    db.flush()
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="task_create",
        target_type="task",
        target_id=task.task_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        details=audit_details(confirmation, {"status": "open"}),
    )
    recompute_task_highlights(db, event.patient_id)
    db.commit()
    db.refresh(task)
    return _task_response(task, ctx)


@router.get("/patients/{patient_id}/tasks")
def list_tasks(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_tasks", patient.clinic_id, patient.patient_id)
    query = select(Task).where(Task.patient_id == patient_id)
    if ctx.role == "patient":
        query = query.where(
            Task.patient_visible.is_(True),
            Task.assigned_role == "patient",
            Task.assigned_user_id == ctx.user_id,
        )
    tasks = db.scalars(query.order_by(Task.created_at, Task.task_id)).all()
    return [_task_response(task, ctx) for task in tasks]


def _conflict(db: Session, ctx: RoleContext, task: Task, expected: str) -> JSONResponse:
    task_id = task.task_id
    clinic_id = task.clinic_id
    patient_id = task.patient_id
    event_id = task.event_id
    db.rollback()
    current = db.get(Task, task_id)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="conflict",
        target_type="task",
        target_id=task_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        event_id=event_id,
        details={"expected_status": expected},
    )
    db.commit()
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "conflict",
                "message": "Stale write: expected_status does not match current status",
                "expected_status": expected,
                "current_status": current.status if current else None,
            }
        },
    )


def _authorize_transition(ctx: RoleContext, task: Task, new: str) -> None:
    if ctx.role == "patient":
        if not _patient_can_see(ctx, task):
            raise resource_not_found()
        if new not in {"in_progress", "reported_done"}:
            raise HTTPException(status_code=403, detail="Forbidden")
        return
    if ctx.role not in {"staff", "clinician"}:
        raise HTTPException(status_code=403, detail="Forbidden")
    if new == "in_progress" and (
        task.assigned_role != ctx.role
        or (task.assigned_user_id is not None and task.assigned_user_id != ctx.user_id)
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


@router.post("/tasks/{task_id}/transition")
def transition_task(
    task_id: str,
    body: object = Body(...),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = db.get(Task, task_id)
    if task is None:
        raise resource_not_found()
    # Scope first; patient assignment/visibility next; body/status only after.
    authorize_scope(ctx, task.clinic_id, task.patient_id)
    if ctx.role == "patient" and not _patient_can_see(ctx, task):
        raise resource_not_found()
    authorize(ctx, "transition_task", task.clinic_id, task.patient_id)
    parsed = _validate(TaskTransition, body)

    if parsed.expected_status != task.status:
        return _conflict(db, ctx, task, parsed.expected_status)
    if parsed.status not in task_transitions().get(task.status, set()):
        raise HTTPException(
            status_code=422,
            detail=f"Illegal task transition: {task.status} -> {parsed.status}",
        )
    _authorize_transition(ctx, task, parsed.status)

    now = datetime.now()
    values: dict = {"status": parsed.status, "updated_at": now}
    if parsed.status == "reported_done":
        values["reported_done_at"] = now
    elif parsed.status == "completed":
        values.update(completed_by=ctx.user_id, completed_at=now)
    elif parsed.status == "cancelled":
        values.update(cancelled_by=ctx.user_id, cancelled_at=now)
    result = db.execute(
        update(Task)
        .where(Task.task_id == task_id, Task.status == parsed.expected_status)
        .values(**values)
    )
    if result.rowcount != 1:
        return _conflict(db, ctx, task, parsed.expected_status)

    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="task_transition",
        target_type="task",
        target_id=task_id,
        clinic_id=task.clinic_id,
        patient_id=task.patient_id,
        event_id=task.event_id,
        details={"from_status": parsed.expected_status, "to_status": parsed.status},
    )
    recompute_task_highlights(db, task.patient_id)
    db.commit()
    current = db.get(Task, task_id)
    return _task_response(current, ctx)


@router.get("/tasks/{task_id}/provenance", response_model=TaskProvenanceOut)
def get_task_provenance(
    task_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = db.get(Task, task_id)
    if task is None:
        raise resource_not_found()
    authorize(ctx, "read_task_provenance", task.clinic_id, task.patient_id)
    event = db.get(Event, task.event_id)
    if event is None:
        raise resource_not_found()
    artifact = db.get(Artifact, task.source_artifact_id) if task.source_artifact_id else None
    if task.source_artifact_id and (
        artifact is None or artifact.event_id != event.event_id
    ):
        raise resource_not_found()
    quote = None
    if artifact is not None:
        quote = resolve_exact_span(artifact.content, task.source_span or {})
        if quote is None:
            raise resource_not_found()
    return TaskProvenanceOut(
        task_id=task.task_id,
        event=EventBrief.model_validate(event),
        source_artifact=ArtifactOut.model_validate(artifact) if artifact else None,
        span=task.source_span,
        quote=quote,
    )
