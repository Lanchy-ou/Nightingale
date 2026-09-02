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
from ..clinic_scope import load_event, load_patient, load_task
from ..ids import new_id
from ..models import Artifact, Event, Patient, PatientReviewItem, Task, User
from ..models import Highlight
from ..glance_projection import rebuild_glance_projections
from ..patient_review import ensure_clinician_review_task, materialize_due_escalations
from ..role_context import RoleContext
from ..schemas import (
    ArtifactOut,
    ClinicalTaskOut,
    EventBrief,
    PatientTaskOut,
    TaskCreate,
    PatientReportVerification,
    PatientReviewItemOut,
    PatientReviewItemUpdate,
    ClinicianReviewCompletion,
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
    event = load_event(db, ctx, event_id)
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
    from ..workflow_state import ensure_task_workflow

    ensure_task_workflow(
        db,
        task,
        created_by_role=ctx.role,
        created_by_user_id=ctx.user_id,
    )
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
    rebuild_glance_projections(db, event.patient_id)
    db.commit()
    db.refresh(task)
    return _task_response(task, ctx)


@router.get("/patients/{patient_id}/tasks")
def list_tasks(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_tasks", patient.clinic_id, patient.patient_id)
    if ctx.role in {"staff", "clinician"}:
        if materialize_due_escalations(db):
            db.commit()
    query = select(Task).where(
        Task.patient_id == patient_id,
        Task.clinic_id == ctx.clinic_id,
    )
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
    current = load_task(db, ctx, task_id)
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


def _authorize_staff_review(ctx: RoleContext, task: Task) -> None:
    if (
        ctx.role != "staff"
        or task.task_kind != "patient_report_review"
        or task.assigned_role != "staff"
        or (task.assigned_user_id is not None and task.assigned_user_id != ctx.user_id)
    ):
        raise HTTPException(status_code=403, detail="Forbidden")


def _aggregate_review_outcome(items: list[PatientReviewItem]) -> str | None:
    if not items:
        return None
    outcomes = {item.outcome for item in items}
    if "pending" in outcomes:
        raise HTTPException(status_code=422, detail="Every patient-report candidate must be reviewed")
    if "unable_to_verify" in outcomes:
        return "unable_to_verify"
    if "corrected" in outcomes:
        return "corrected"
    return "verified"


@router.post("/tasks/{task_id}/transition")
def transition_task(
    task_id: str,
    body: object = Body(...),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = load_task(db, ctx, task_id)
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
    rebuild_glance_projections(db, task.patient_id)
    db.commit()
    current = load_task(db, ctx, task_id)
    return _task_response(current, ctx)


@router.post("/tasks/{task_id}/verify-patient-report", response_model=ClinicalTaskOut)
def verify_patient_report(
    task_id: str,
    body: object = Body(...),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = load_task(db, ctx, task_id)
    if task is None:
        raise resource_not_found()
    authorize_scope(ctx, task.clinic_id, task.patient_id)
    authorize(ctx, "transition_task", task.clinic_id, task.patient_id)
    _authorize_staff_review(ctx, task)
    parsed = _validate(PatientReportVerification, body)
    if parsed.expected_status != task.status:
        return _conflict(db, ctx, task, parsed.expected_status)
    review_items = db.scalars(
        select(PatientReviewItem)
        .where(PatientReviewItem.staff_task_id == task.task_id)
        .order_by(PatientReviewItem.review_item_id)
    ).all()
    aggregate = _aggregate_review_outcome(review_items)
    if aggregate is None and parsed.verification_outcome == "corrected":
        raise HTTPException(status_code=422, detail="A correction must identify a reviewed candidate")
    if aggregate is not None and parsed.verification_outcome != aggregate:
        raise HTTPException(
            status_code=422,
            detail=f"Session outcome must match reviewed candidates: {aggregate}",
        )
    now = datetime.now()
    result = db.execute(
        update(Task)
        .where(Task.task_id == task_id, Task.status == parsed.expected_status)
        .values(
            status="completed",
            verification_outcome=parsed.verification_outcome,
            completed_by=ctx.user_id,
            completed_at=now,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        return _conflict(db, ctx, task, parsed.expected_status)
    task.status = "completed"
    task.verification_outcome = parsed.verification_outcome
    if parsed.next_route == "clinician_review":
        ensure_clinician_review_task(db, staff_task=task, now=now)
    clinician_task = db.scalar(
        select(Task).where(
            Task.workflow_id == task.workflow_id,
            Task.task_kind == "clinician_priority_review",
            Task.assigned_role == "clinician",
        )
    )
    if clinician_task is not None:
        clinician_task.verification_outcome = parsed.verification_outcome
        clinician_task.updated_at = now
        db.add(clinician_task)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="patient_review_verify",
        target_type="task",
        target_id=task_id,
        clinic_id=task.clinic_id,
        patient_id=task.patient_id,
        event_id=task.event_id,
        details={
            "verification_outcome": parsed.verification_outcome,
            "next_route": parsed.next_route,
        },
    )
    recompute_task_highlights(db, task.patient_id)
    db.flush()
    rebuild_glance_projections(db, task.patient_id, as_of=now)
    db.commit()
    return load_task(db, ctx, task_id)


@router.post(
    "/tasks/{task_id}/review-items/{review_item_id}",
    response_model=PatientReviewItemOut,
)
def review_patient_report_item(
    task_id: str,
    review_item_id: str,
    body: object = Body(...),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = load_task(db, ctx, task_id)
    if task is None:
        raise resource_not_found()
    authorize_scope(ctx, task.clinic_id, task.patient_id)
    authorize(ctx, "transition_task", task.clinic_id, task.patient_id)
    _authorize_staff_review(ctx, task)
    if task.status not in {"open", "in_progress"}:
        raise HTTPException(status_code=422, detail="Patient review Task is already closed")
    item = db.get(PatientReviewItem, review_item_id)
    if item is None or item.staff_task_id != task.task_id or item.workflow_id != task.workflow_id:
        raise resource_not_found()
    parsed = _validate(PatientReviewItemUpdate, body)
    correction = None
    if parsed.correction_artifact_id is not None:
        correction = db.get(Artifact, parsed.correction_artifact_id)
        note = correction.content.get("note") if correction is not None else None
        if (
            correction is None
            or correction.event_id != task.event_id
            or correction.artifact_type != "staff_note"
            or correction.author_role != "staff"
            or correction.author_id != ctx.user_id
            or not isinstance(note, str)
            or not note.strip()
        ):
            raise HTTPException(status_code=422, detail="Correction must link this Nurse's Staff Note")
    now = datetime.now()
    result = db.execute(
        update(PatientReviewItem)
        .where(
            PatientReviewItem.review_item_id == review_item_id,
            PatientReviewItem.outcome == parsed.expected_outcome,
        )
        .values(
            outcome=parsed.outcome,
            correction_artifact_id=parsed.correction_artifact_id,
            reviewed_by=ctx.user_id,
            reviewed_at=now,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Patient review item changed concurrently")
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="patient_review_item",
        target_type="task",
        target_id=task.task_id,
        clinic_id=task.clinic_id,
        patient_id=task.patient_id,
        event_id=task.event_id,
        details={
            "review_item_id": review_item_id,
            "highlight_id": item.highlight_id,
            "from_outcome": parsed.expected_outcome,
            "to_outcome": parsed.outcome,
            "correction_artifact_id": parsed.correction_artifact_id,
        },
    )
    db.commit()
    return db.get(PatientReviewItem, review_item_id)


@router.post("/tasks/{task_id}/complete-clinician-review", response_model=ClinicalTaskOut)
def complete_clinician_review(
    task_id: str,
    body: object = Body(...),
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = load_task(db, ctx, task_id)
    if task is None:
        raise resource_not_found()
    authorize_scope(ctx, task.clinic_id, task.patient_id)
    authorize(ctx, "transition_task", task.clinic_id, task.patient_id)
    if ctx.role != "clinician" or task.task_kind != "clinician_priority_review":
        raise HTTPException(status_code=403, detail="Forbidden")
    parsed = _validate(ClinicianReviewCompletion, body)
    if parsed.expected_status != task.status:
        return _conflict(db, ctx, task, parsed.expected_status)
    follow_up = db.get(Task, parsed.follow_up_task_id) if parsed.follow_up_task_id else None
    if parsed.review_outcome == "action_required":
        if (
            follow_up is None
            or follow_up.task_id == task.task_id
            or follow_up.patient_id != task.patient_id
            or follow_up.clinic_id != task.clinic_id
            or follow_up.task_kind != "care_action"
            or follow_up.status not in {"open", "in_progress", "reported_done"}
            or follow_up.assigned_role not in {"staff", "clinician"}
            or (
                follow_up.assigned_role == "clinician"
                and follow_up.assigned_user_id != ctx.user_id
            )
        ):
            raise HTTPException(
                status_code=422,
                detail="Action required must link an active Care Task owned by this clinician or the Nurse queue",
            )
        if parsed.time_sensitivity == "time_sensitive" and follow_up.due_at is None:
            raise HTTPException(status_code=422, detail="Time-sensitive follow-up requires a due time")
    elif parsed.follow_up_task_id is not None:
        raise HTTPException(status_code=422, detail="Only action_required may link a follow-up Task")
    grade = {
        ("no_action", "routine"): 0,
        ("monitor_or_record", "routine"): 1,
        ("monitor_or_record", "time_sensitive"): 2,
        ("action_required", "routine"): 2,
        ("action_required", "time_sensitive"): 3,
    }[(parsed.review_outcome, parsed.time_sensitivity)]
    now = datetime.now()
    if follow_up is not None:
        from ..workflow_state import attach_task_to_workflow, ensure_task_workflow

        workflow = ensure_task_workflow(db, task)
        attach_task_to_workflow(
            db,
            task=follow_up,
            workflow=workflow,
            relation_from_task_id=task.task_id,
            relation_type="requires_action",
            created_by_role=ctx.role,
            created_by_user_id=ctx.user_id,
            created_at=now,
        )
    metadata = dict(task.routing_metadata or {})
    metadata.update(attention_label_version="attention-label-v1", attention_label_grade=grade)
    result = db.execute(
        update(Task)
        .where(Task.task_id == task_id, Task.status == parsed.expected_status)
        .values(
            status="completed",
            review_outcome=parsed.review_outcome,
            time_sensitivity=parsed.time_sensitivity,
            follow_up_task_id=parsed.follow_up_task_id,
            routing_metadata=metadata,
            completed_by=ctx.user_id,
            completed_at=now,
            updated_at=now,
        )
    )
    if result.rowcount != 1:
        return _conflict(db, ctx, task, parsed.expected_status)
    task.status = "completed"
    task.review_outcome = parsed.review_outcome
    task.time_sensitivity = parsed.time_sensitivity
    task.follow_up_task_id = parsed.follow_up_task_id
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="clinician_review_complete",
        target_type="task",
        target_id=task_id,
        clinic_id=task.clinic_id,
        patient_id=task.patient_id,
        event_id=task.event_id,
        details={
            "review_outcome": parsed.review_outcome,
            "time_sensitivity": parsed.time_sensitivity,
            "attention_label_grade": grade,
            "attention_label_version": "attention-label-v1",
            "follow_up_task_id": parsed.follow_up_task_id,
        },
    )
    from ..shadow_learning import record_outcome_label

    record_outcome_label(
        db,
        task=task,
        actor_id=ctx.user_id,
        grade=grade,
        now=now,
    )
    recompute_task_highlights(db, task.patient_id)
    db.flush()
    rebuild_glance_projections(db, task.patient_id, as_of=now)
    db.commit()
    return load_task(db, ctx, task_id)


@router.get("/tasks/{task_id}/review-context")
def patient_review_context(
    task_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = load_task(db, ctx, task_id)
    if task is None:
        raise resource_not_found()
    authorize(ctx, "read_internal_patient_review", task.clinic_id, task.patient_id)
    if task.task_kind not in {"patient_report_review", "clinician_priority_review"}:
        raise HTTPException(status_code=422, detail="Task is not a patient review workflow")
    summary = db.scalar(
        select(Artifact).where(
            Artifact.event_id == task.event_id,
            Artifact.artifact_type == "ai_patient_session_summary",
        )
    )
    if summary is None:
        raise resource_not_found()
    candidates = db.scalars(
        select(Highlight)
        .where(Highlight.artifact_id == summary.artifact_id)
        .order_by(Highlight.created_at, Highlight.highlight_id)
    ).all()
    review_items = {
        item.highlight_id: item
        for item in db.scalars(
            select(PatientReviewItem).where(PatientReviewItem.workflow_id == task.workflow_id)
        ).all()
    }
    return {
        "task": ClinicalTaskOut.model_validate(task).model_dump(mode="json"),
        "summary_artifact_id": summary.artifact_id,
        "generation_method": summary.generation_method,
        "degraded": summary.degraded,
        "candidates": [
            {
                "highlight_id": item.highlight_id,
                "text": item.text,
                "entity_type": item.entity_type,
                "source_artifact_id": item.source_artifact_id,
                "source_span": item.source_span,
                "review_status": item.review_status,
                "review_item_id": review_items[item.highlight_id].review_item_id,
                "review_outcome": review_items[item.highlight_id].outcome,
                "correction_artifact_id": review_items[item.highlight_id].correction_artifact_id,
                "reviewed_by": review_items[item.highlight_id].reviewed_by,
                "reviewed_at": review_items[item.highlight_id].reviewed_at,
            }
            for item in candidates
            if item.highlight_id in review_items
        ],
    }


@router.get("/tasks/{task_id}/provenance", response_model=TaskProvenanceOut)
def get_task_provenance(
    task_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    task = load_task(db, ctx, task_id)
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
    if artifact is not None and task.source_span is not None:
        quote = resolve_exact_span(artifact.content, task.source_span)
        if quote is None:
            raise resource_not_found()
    return TaskProvenanceOut(
        task_id=task.task_id,
        event=EventBrief.model_validate(event),
        source_artifact=ArtifactOut.model_validate(artifact) if artifact else None,
        span=task.source_span,
        quote=quote,
    )
