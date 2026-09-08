"""Database outbox: leased processing, atomic inbox insertion and bounded retries."""
import os
from datetime import timedelta
from sqlalchemy import select, update, or_, event
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session
from .ids import stable_id, new_id
from .models import Task, User, PatientInstructionPublication
from .result_models import NotificationJob, InboxNotification, NotificationSettings, TestOrder
from .test_result_service import now_utc, utc, active_user


def enabled():
    return os.getenv("NANTINGALE_NOTIFICATIONS_ENABLED", "false").lower() == "true"


def task_version(task):
    return stable_id("verification" if task.status == "reported_done" else "action", str(task.assigned_user_id), str(task.due_at),
                     str((task.routing_metadata or {}).get("notification_version", "")))


def recipients(db, task, shared=False):
    if not shared and task.assigned_user_id and active_user(db, task.clinic_id, task.assigned_user_id, {task.assigned_role} & {"staff", "clinician"}):
        return [task.assigned_user_id]
    # Patient reports of completion are routed to clinical verification, never back to the patient.
    role = "clinician" if shared or task.assigned_user_id or task.assigned_role == "patient" else task.assigned_role
    return [u.user_id for u in db.scalars(select(User).where(User.clinic_id == task.clinic_id, User.role == role)).all()
            if active_user(db, task.clinic_id, u.user_id, {role})]


def enqueue(db, clinic_id, target_type, target_id, version, owner_id, stage, due, now):
    job_id = stable_id("notify", target_type, target_id, version, owner_id, stage)
    db.execute(insert(NotificationJob).values(job_id=job_id, clinic_id=clinic_id, target_type=target_type,
        target_id=target_id, target_version=version, recipient_id=owner_id, stage=stage, status="pending",
        due_at=due, attempts=0, created_at=now).on_conflict_do_nothing())


def valid(db, job):
    owner = active_user(db, job.clinic_id, job.recipient_id, {"patient", "staff", "clinician"})
    if owner is None:
        return False
    if job.target_type == "publication":
        target = db.get(PatientInstructionPublication, job.target_id)
        return bool(target and target.state == "published" and target.clinic_id == job.clinic_id
                    and owner.role == "patient" and owner.patient_id == target.patient_id)
    target = db.get(Task, job.target_id)
    if not target or target.clinic_id != job.clinic_id or target.status not in {"open", "in_progress", "reported_done"}:
        return False
    return task_version(target) == job.target_version and job.recipient_id in recipients(db, target, job.stage == "escalation")


def reconcile_notifications(db, *, now=None):
    if not enabled():
        return
    now = now or now_utc()
    db.flush()
    tasks = db.scalars(select(Task).where(Task.status.in_(["open", "in_progress", "reported_done"]))).all()
    for task in tasks:
        if task.assigned_role == "patient" and task.status != "reported_done":
            continue
        assigned_recipients = recipients(db, task)
        unavailable_owner = bool(task.assigned_user_id and not active_user(db, task.clinic_id, task.assigned_user_id, {task.assigned_role} & {"staff", "clinician"}))
        metadata = dict(task.routing_metadata or {})
        metadata.update(notification_blocked=not bool(assigned_recipients), shared_clinician_queue=unavailable_owner)
        if metadata != task.routing_metadata:
            task.routing_metadata = metadata
        config = db.get(NotificationSettings, task.clinic_id)
        version = task_version(task)
        due = task.due_at
        if task.status == "reported_done":
            due = (utc(db, task.clinic_id, task.reported_done_at) if task.reported_done_at else now) + timedelta(hours=config.verification_hours if config else 24)
        elif due and (task.routing_metadata or {}).get("due_timezone") != "UTC":
            due = utc(db, task.clinic_id, due)
        for recipient in recipients(db, task):
            enqueue(db, task.clinic_id, "task", task.task_id, version, recipient, "initial", now, now)
            if due:
                enqueue(db, task.clinic_id, "task", task.task_id, version, recipient, "overdue", due, now)
        if due:
            for recipient in recipients(db, task, True):
                enqueue(db, task.clinic_id, "task", task.task_id, version, recipient, "escalation",
                        due + timedelta(hours=config.escalation_hours if config else 24), now)
    for publication in db.scalars(select(PatientInstructionPublication).where(PatientInstructionPublication.state == "published")).all():
        for user in db.scalars(select(User).where(User.clinic_id == publication.clinic_id,
                              User.patient_id == publication.patient_id, User.role == "patient")).all():
            enqueue(db, publication.clinic_id, "publication", publication.publication_id,
                    str(publication.artifact_version), user.user_id, "initial", now, now)
    for job in db.scalars(select(NotificationJob).where(NotificationJob.status.in_(["pending", "processing", "failed", "delivered"]))).all():
        if not valid(db, job):
            if job.status != "delivered":
                job.status = "cancelled"
            notification = db.scalar(select(InboxNotification).where(InboxNotification.job_id == job.job_id))
            if notification and notification.resolved_at is None:
                notification.resolved_at = now


@event.listens_for(Session, "before_commit")
def business_outbox(db):
    if db.info.get("authentication_metadata_only"):
        return
    # Keep the examination's parent workflow live while independently assigned care actions remain.
    changed = [t for t in db.dirty if isinstance(t, Task) and (t.routing_metadata or {}).get("test_order_id")]
    if changed:
        from .workflow_state import refresh_workflow_status
        db.flush()
        for task in changed:
            order = db.get(TestOrder, task.routing_metadata["test_order_id"])
            if order:
                refresh_workflow_status(db, order.workflow_id, as_of=now_utc())
    # This runs inside the business transaction, including legacy Task/publication mutations.
    if enabled() and not db.info.get("notification_worker"):
        reconcile_notifications(db)


def sweep(session_factory, *, now=None, deliver_hook=None):
    if not enabled():
        return 0
    now = now or now_utc()
    with session_factory() as db:
        db.info["notification_worker"] = True
        reconcile_notifications(db, now=now)
        db.commit()
        ids = db.scalars(select(NotificationJob.job_id).where(
            or_((NotificationJob.status == "pending") & (NotificationJob.due_at <= now),
                (NotificationJob.status == "processing") & (NotificationJob.lease_until <= now)))
            .order_by(NotificationJob.due_at).limit(100)).all()
    count = 0
    for job_id in ids:
        token = new_id("lease")
        with session_factory() as db:
            db.info["notification_worker"] = True
            claimed = db.execute(update(NotificationJob).where(NotificationJob.job_id == job_id,
                or_((NotificationJob.status == "pending") & (NotificationJob.due_at <= now),
                    (NotificationJob.status == "processing") & (NotificationJob.lease_until <= now)))
                .values(status="processing", lease_token=token, lease_until=now + timedelta(minutes=2)))
            db.commit()
            if claimed.rowcount != 1:
                continue
        try:
            with session_factory() as db:
                db.info["notification_worker"] = True
                # Acquire write ownership before checking live domain state and inserting inbox row.
                locked = db.execute(update(NotificationJob).where(NotificationJob.job_id == job_id,
                    NotificationJob.lease_token == token, NotificationJob.status == "processing").values(lease_until=now + timedelta(minutes=2)))
                if locked.rowcount != 1:
                    continue
                job = db.get(NotificationJob, job_id)
                if not valid(db, job):
                    job.status = "cancelled"
                else:
                    if deliver_hook:
                        deliver_hook(job)
                    db.execute(insert(InboxNotification).values(notification_id=stable_id("inbox", job_id),
                        job_id=job_id, owner_id=job.recipient_id, created_at=now).on_conflict_do_nothing())
                    if job.target_type == "task" and job.stage == "escalation":
                        task = db.get(Task, job.target_id)
                        if task.escalated_at is None:
                            task.escalated_at = now
                            from .audit import add_audit
                            add_audit(db, actor_id=None, actor_role="system", action="notification_escalated", target_type="task",
                                target_id=task.task_id, clinic_id=task.clinic_id, patient_id=task.patient_id, event_id=task.event_id,
                                details={"original_owner_id": task.assigned_user_id, "queue": "clinic_clinicians"})
                    job.status = "delivered"
                    job.attempts += 1
                    job.error_code = None
                    count += 1
                job.lease_until = None
                job.lease_token = None
                db.commit()
        except Exception:
            with session_factory() as db:
                db.info["notification_worker"] = True
                job = db.scalar(select(NotificationJob).where(NotificationJob.job_id == job_id, NotificationJob.lease_token == token))
                if job:
                    job.attempts += 1
                    job.status = "failed" if job.attempts >= 5 else "pending"
                    job.due_at = now + timedelta(minutes=[1, 5, 15, 60][min(job.attempts - 1, 3)])
                    job.lease_until = None
                    job.lease_token = None
                    job.error_code = "inbox_delivery_failed"
                    db.commit()
    with session_factory() as db:
        db.info["notification_worker"] = True
        from .models import Clinic
        for clinic_id in db.scalars(select(Clinic.clinic_id)).all():
            db.execute(insert(NotificationSettings).values(clinic_id=clinic_id, revision=1, timezone="Asia/Singapore",
                review_hours=24, communication_hours=24, verification_hours=24, escalation_hours=24,
                last_sweep_at=now).on_conflict_do_update(index_elements=["clinic_id"], set_={"last_sweep_at": now}))
        db.commit()
    return count
