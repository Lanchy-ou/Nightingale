"""Transactional result handling. All times in these new records are naive UTC."""
import hashlib
import json
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import select, update
from .audit import add_audit
from .ids import new_id, stable_id
from .models import Artifact, Event, Task, User, UserCredential, PatientInstructionPublication
from .result_models import TestOrder, TestReport, TestReview, TestCommunication, ResultOperation, NotificationSettings
from .workflow_state import ensure_workflow, create_workflow_link, refresh_workflow_status

RESULT_ARTIFACT_TYPES = {"external_test_report", "test_result_review", "test_result_communication"}
RESULT_TASK_KINDS = {"report_followup", "result_review", "result_communication"}


def enabled():
    return os.getenv("NANTINGALE_TEST_RESULTS_ENABLED", "false").lower() == "true"


def require_enabled():
    if not enabled():
        raise HTTPException(409, "New result handling is disabled; saved records remain readable")


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utc(db, clinic_id, value):
    settings = db.get(NotificationSettings, clinic_id)
    zone = ZoneInfo(settings.timezone if settings else "Asia/Singapore")
    return (value.replace(tzinfo=zone) if value.tzinfo is None else value).astimezone(timezone.utc).replace(tzinfo=None)


def active_user(db, clinic_id, user_id, roles):
    user = db.scalar(select(User).where(User.user_id == user_id, User.clinic_id == clinic_id, User.role.in_(roles)))
    credential = db.get(UserCredential, user_id) if user else None
    return user if user and not (credential and credential.disabled_at) else None


def assignee(db, clinic_id, user_id, roles):
    user = active_user(db, clinic_id, user_id, roles)
    if user is None:
        raise HTTPException(422, "Choose an active permitted clinic team member")
    return user


def operation(db, ctx, scope, body):
    key = stable_id("result_op", ctx.clinic_id, ctx.user_id, scope, body.idempotency_key)
    payload = body.model_dump(mode="json", exclude={"idempotency_key"})
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    previous = db.get(ResultOperation, key)
    if previous and previous.payload_hash != digest:
        raise HTTPException(409, "Idempotency key was used for different content")
    if previous:
        return key, digest, previous.response
    from sqlalchemy.dialects.sqlite import insert
    claimed = db.execute(insert(ResultOperation).values(operation_id=key, payload_hash=digest, response={}).on_conflict_do_nothing())
    if claimed.rowcount != 1:
        previous = db.get(ResultOperation, key)
        if previous.payload_hash != digest:
            raise HTTPException(409, "Idempotency key was used for different content")
        return key, digest, previous.response
    return key, digest, None


def lock_order(db, order, revision):
    result = db.execute(update(TestOrder).where(TestOrder.order_id == order.order_id,
                       TestOrder.revision == revision).values(revision=revision + 1, updated_at=now_utc()))
    if result.rowcount != 1:
        raise HTTPException(409, "This examination changed. Reload before continuing")
    db.refresh(order)
    if order.cancelled_reason:
        raise HTTPException(409, "This examination was cancelled")


def stage(db, order):
    if order.cancelled_reason:
        return "cancelled"
    report = db.get(TestReport, order.current_report_id) if order.current_report_id else None
    if not report or report.withdrawn_reason:
        return "waiting_report"
    review = db.get(TestReview, order.current_review_id) if order.current_review_id else None
    if not review or review.report_id != report.report_id:
        return "waiting_review"
    communications = db.scalars(select(TestCommunication).where(TestCommunication.order_id == order.order_id,
                                  TestCommunication.review_id == review.review_id, TestCommunication.outcome == "delivered")).all()
    for item in communications:
        if item.method != "portal":
            return "completed"
        publication = db.get(PatientInstructionPublication, item.publication_id)
        if publication and publication.state == "published":
            return "completed"
    return "waiting_communication"


def artifact(db, order, kind, content, ctx, provenance=None):
    row = Artifact(artifact_id=new_id("art"), event_id=order.result_event_id, artifact_type=kind,
                   author_role="external" if kind == "external_test_report" else ctx.role,
                   author_id=None if kind == "external_test_report" else ctx.user_id, content=content, version=1,
                   provenance_pointer=provenance, created_at=now_utc())
    db.add(row)
    db.flush()
    return row


def invalidate_guidance(db, order, ctx):
    publications = db.scalars(select(PatientInstructionPublication).join(Artifact,
        Artifact.artifact_id == PatientInstructionPublication.instruction_artifact_id).where(
        Artifact.event_id == order.result_event_id, PatientInstructionPublication.state == "published")).all() if order.result_event_id else []
    for publication in publications:
        publication.state = "withdrawn"
        publication.withdrawn_at = publication.updated_at = now_utc()
        publication.withdrawn_by_user_id = ctx.user_id
        publication.withdrawal_reason_code = "report_superseded"
    order.current_review_id = None


def sync_tasks(db, order, ctx):
    """One durable Task per stage; reopening is versioned in routing metadata and audit."""
    db.flush()
    current = stage(db, order)
    config = db.get(NotificationSettings, order.clinic_id)
    from datetime import timedelta
    report = db.get(TestReport, order.current_report_id) if order.current_report_id else None
    review = db.get(TestReview, order.current_review_id) if order.current_review_id else None
    workflow = ensure_workflow(db, workflow_id=order.workflow_id, clinic_id=order.clinic_id,
        patient_id=order.patient_id, workflow_kind="care_action_chain", root_event_id=order.event_id,
        created_by_role="clinician", created_by_user_id=order.created_by, created_at=order.created_at)
    definitions = [("report_followup", "waiting_report", order.coordinator_id, order.expected_at),
                   ("result_review", "waiting_review", order.reviewer_id,
                    report.created_at + timedelta(hours=config.review_hours if config else 24) if report else None),
                   ("result_communication", "waiting_communication", order.coordinator_id,
                    review.created_at + timedelta(hours=config.communication_hours if config else 24) if review else None)]
    for kind, active_stage, owner_id, due in definitions:
        task_id = stable_id("result_task", order.order_id, kind)
        task = db.get(Task, task_id)
        if task is None and current != active_stage:
            continue
        if task is None:
            owner = db.get(User, owner_id)
            task = Task(task_id=task_id, patient_id=order.patient_id, clinic_id=order.clinic_id,
                event_id=order.event_id, title=f"{kind.replace('_', ' ').title()}: {order.title}", description="Open the examination to continue",
                task_kind=kind, workflow_id=order.workflow_id, assigned_role=owner.role, assigned_user_id=owner_id,
                status="open", patient_visible=False, created_by=order.created_by, created_at=now_utc(), updated_at=now_utc())
            db.add(task)
            db.flush()
            create_workflow_link(db, workflow=workflow, from_type="event", from_id=order.event_id,
                relation_type="triggered_review" if kind == "result_review" else "triggered_action", to_id=task_id,
                created_by_role=ctx.role, created_by_user_id=ctx.user_id, created_at=now_utc())
        desired = "open" if current == active_stage else "cancelled" if current == "cancelled" else "completed"
        task.status = desired
        task.assigned_user_id = owner_id
        task.assigned_role = db.get(User, owner_id).role
        task.due_at = due
        task.routing_metadata = {"test_order_id": order.order_id, "revision": order.revision, "notification_version": (order.current_review_id if kind == "result_communication" else order.current_report_id) or "awaiting", "due_timezone": "UTC"}
        task.updated_at = now_utc()
        task.completed_at = now_utc() if desired == "completed" else None
        task.completed_by = ctx.user_id if desired == "completed" else None
    db.flush()
    refresh_workflow_status(db, order.workflow_id, as_of=now_utc())


def finish(db, order, ctx, op, action):
    sync_tasks(db, order, ctx)
    add_audit(db, actor_id=ctx.user_id, actor_role=ctx.role, action=action, target_type="test_order",
              target_id=order.order_id, clinic_id=order.clinic_id, patient_id=order.patient_id,
              event_id=order.result_event_id or order.event_id, to_version=order.revision)
    response = {"order_id": order.order_id, "revision": order.revision, "stage": stage(db, order)}
    db.get(ResultOperation, op[0]).response = response
    from .notifications import reconcile_notifications
    reconcile_notifications(db, now=now_utc())
    db.commit()
    return response


def publication_changed(db, ctx, event_id):
    """Withdrawal/correction reopens communication within the publication transaction."""
    db.flush()
    db.expire_all()  # Existing publication handlers use conditional bulk updates.
    order = db.scalar(select(TestOrder).where(TestOrder.result_event_id == event_id, TestOrder.clinic_id == ctx.clinic_id))
    if not order or order.cancelled_reason:
        return
    task = db.get(Task, stable_id("result_task", order.order_id, "result_communication"))
    if task and task.status == "completed" and stage(db, order) == "waiting_communication":
        lock_order(db, order, order.revision)
        sync_tasks(db, order, ctx)
        add_audit(db, actor_id=ctx.user_id, actor_role=ctx.role, action="result_communication_reopened", target_type="test_order",
            target_id=order.order_id, clinic_id=order.clinic_id, patient_id=order.patient_id, event_id=event_id, to_version=order.revision)
