from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, func, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from ..authz import authorize, require_auth, resource_not_found
from ..db import get_db
from ..models import Task, PatientInstructionPublication
from ..result_models import NotificationJob, InboxNotification, NotificationSettings
from ..result_schemas import ReminderSettingsUpdate
from ..role_context import RoleContext
from ..notifications import enabled, valid, recipients
from ..test_result_service import now_utc

router = APIRouter(prefix="/api", tags=["notifications"])


@router.get("/notifications")
def inbox(offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100),
          db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "read_notifications", ctx.clinic_id, ctx.patient_id)
    pairs = db.execute(select(InboxNotification, NotificationJob).join(NotificationJob).where(
        InboxNotification.owner_id == ctx.user_id, NotificationJob.clinic_id == ctx.clinic_id)
        .order_by(InboxNotification.created_at.desc(), InboxNotification.notification_id).offset(offset).limit(limit)).all()
    items = []
    for notification, job in pairs:
        live = valid(db, job)
        target = None
        if live and job.target_type == "task":
            task = db.get(Task, job.target_id)
            order_id = (task.routing_metadata or {}).get("test_order_id")
            target = f"/clinical/patients/{task.patient_id}/tests?order={order_id}" if order_id and task.task_kind != "care_action" else f"/clinical/patients/{task.patient_id}/tasks?task={task.task_id}"
        elif live and job.target_type == "publication":
            publication = db.get(PatientInstructionPublication, job.target_id)
            target = f"/patient/visit-summaries?instruction={publication.instruction_artifact_id}&version={publication.artifact_version}"
        items.append({"notification_id": notification.notification_id, "created_at": notification.created_at,
            "read_at": notification.read_at, "resolved": not live or notification.resolved_at is not None,
            "title": "New care guidance is available" if job.target_type == "publication" else
                     "Clinic review needed" if job.stage == "escalation" else "A care task needs your attention",
            "stage": job.stage, "target": target})
    unread = db.scalar(select(func.count()).select_from(InboxNotification).join(NotificationJob).where(
        InboxNotification.owner_id == ctx.user_id, NotificationJob.clinic_id == ctx.clinic_id, InboxNotification.read_at.is_(None)))
    return {"enabled": enabled(), "items": items, "unread_count": unread, "offset": offset, "limit": limit}


@router.post("/notifications/{notification_id}/read")
def mark_read(notification_id: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "read_notifications", ctx.clinic_id, ctx.patient_id)
    row = db.scalar(select(InboxNotification).join(NotificationJob).where(InboxNotification.notification_id == notification_id,
                    InboxNotification.owner_id == ctx.user_id, NotificationJob.clinic_id == ctx.clinic_id))
    if row is None:
        raise resource_not_found()
    row.read_at = row.read_at or now_utc()
    db.commit()
    return {"read_at": row.read_at}


@router.get("/admin/notification-settings")
def settings(db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "manage_notifications", ctx.clinic_id, None)
    row = db.get(NotificationSettings, ctx.clinic_id)
    return {"enabled": enabled(), "revision": row.revision if row else 0,
        "timezone": row.timezone if row else "Asia/Singapore",
        **{key: getattr(row, key) if row else 24 for key in ("review_hours", "communication_hours", "verification_hours", "escalation_hours")}}


@router.put("/admin/notification-settings")
def save_settings(body: ReminderSettingsUpdate, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "manage_notifications", ctx.clinic_id, None)
    try:
        ZoneInfo(body.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        raise HTTPException(422, "Unknown clinic timezone")
    values = body.model_dump(exclude={"expected_revision"}) | {"revision": body.expected_revision + 1}
    if body.expected_revision == 0:
        result = db.execute(insert(NotificationSettings).values(clinic_id=ctx.clinic_id, **values).on_conflict_do_nothing())
    else:
        result = db.execute(update(NotificationSettings).where(NotificationSettings.clinic_id == ctx.clinic_id,
            NotificationSettings.revision == body.expected_revision).values(**values))
    if result.rowcount != 1:
        raise HTTPException(409, "Reminder settings changed")
    db.commit()
    return settings(db, ctx)


@router.get("/admin/notification-jobs")
def jobs(db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "manage_notifications", ctx.clinic_id, None)
    pending = NotificationJob.status.in_(["pending", "processing"])
    scoped = NotificationJob.clinic_id == ctx.clinic_id
    rows = db.scalars(select(NotificationJob).where(scoped, NotificationJob.status == "failed").order_by(NotificationJob.due_at).limit(100)).all()
    config = db.get(NotificationSettings, ctx.clinic_id)
    blocked = sum(not recipients(db, task) for task in db.scalars(select(Task).where(Task.clinic_id == ctx.clinic_id,
        Task.status.in_(["open", "in_progress", "reported_done"]), ((Task.assigned_role.in_(["staff", "clinician"])) | (Task.status == "reported_done")))).all())
    return {"pending_count": db.scalar(select(func.count()).select_from(NotificationJob).where(scoped, pending)),
        "oldest_pending_at": db.scalar(select(func.min(NotificationJob.created_at)).where(scoped, pending)),
        "failed_count": db.scalar(select(func.count()).select_from(NotificationJob).where(scoped, NotificationJob.status == "failed")),
        "blocked_without_clinician_count": blocked, "last_sweep_at": config.last_sweep_at if config else None,
        "failures": [{k: getattr(row, k) for k in ("job_id", "status", "stage", "attempts", "error_code", "due_at")} for row in rows]}


@router.post("/admin/notification-jobs/{job_id}/retry")
def retry(job_id: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "manage_notifications", ctx.clinic_id, None)
    job = db.scalar(select(NotificationJob).where(NotificationJob.job_id == job_id, NotificationJob.clinic_id == ctx.clinic_id))
    if job is None:
        raise resource_not_found()
    if job.status != "failed":
        raise HTTPException(409, "Only failed delivery can be retried")
    job.status = "pending" if valid(db, job) else "cancelled"
    job.attempts = 0
    job.due_at = now_utc()
    job.error_code = None
    db.commit()
    return {"status": job.status}
