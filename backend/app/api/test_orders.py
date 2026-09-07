"""Authenticated examination workflow; every mutation locks the parent revision."""
import base64
import binascii
import hashlib
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session
from ..authz import authorize, require_auth, resource_not_found
from ..clinic_scope import load_event, load_patient
from ..checkin_visibility import require_checkin_event_visible
from ..db import get_db
from ..ids import new_id, stable_id
from ..models import Artifact, Event, Patient, Task, PatientInstructionPublication
from ..result_models import TestOrder, TestReport, TestReview, TestCommunication
from ..result_schemas import OrderCreate, OrderUpdate, ReportUpload, WithdrawReport, ReviewCreate, CommunicationCreate
from ..role_context import RoleContext
from .. import test_result_service as service
from ..workflow_state import ensure_workflow, create_workflow_link

router = APIRouter(prefix="/api", tags=["test results"])


def scoped(db, ctx, order_id, action="read_test_results"):
    order = db.scalar(select(TestOrder).join(Patient, Patient.patient_id == TestOrder.patient_id).where(
        TestOrder.order_id == order_id, TestOrder.clinic_id == ctx.clinic_id, Patient.clinic_id == ctx.clinic_id,
        TestOrder.patient_id == ctx.patient_id if ctx.role == "patient" else True))
    if order is None:
        raise resource_not_found()
    authorize(ctx, action, order.clinic_id, order.patient_id)
    return order


def report_scope(db, ctx, report_id, action="read_test_results"):
    pair = db.execute(select(TestReport, TestOrder).join(TestOrder, TestOrder.order_id == TestReport.order_id)
        .join(Patient, Patient.patient_id == TestOrder.patient_id).where(TestReport.report_id == report_id,
        TestOrder.clinic_id == ctx.clinic_id, Patient.clinic_id == ctx.clinic_id,
        TestOrder.patient_id == ctx.patient_id if ctx.role == "patient" else True)).one_or_none()
    if pair is None:
        raise resource_not_found()
    authorize(ctx, action, pair[1].clinic_id, pair[1].patient_id)
    return pair


def out(db, order):
    return {name: getattr(order, name) for name in ("order_id", "patient_id", "event_id", "result_event_id", "workflow_id", "title", "reason",
        "expected_at", "coordinator_id", "reviewer_id", "legacy_task_id", "revision", "current_report_id", "current_review_id", "cancelled_reason", "created_at")} | {"stage": service.stage(db, order)}


@router.get("/test-results/capabilities")
def capabilities(ctx: RoleContext = Depends(require_auth)):
    return {"enabled": service.enabled()}


@router.get("/test-results/team")
def team(db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    authorize(ctx, "read_test_results", ctx.clinic_id, None)
    from ..models import User
    return [{"user_id": u.user_id, "name": u.name, "role": u.role} for u in db.scalars(select(User).where(
        User.clinic_id == ctx.clinic_id, User.role.in_(["staff", "clinician"]))).all()
        if service.active_user(db, ctx.clinic_id, u.user_id, {"staff", "clinician"})]


@router.post("/events/{event_id}/test-orders")
def create(event_id: str, body: OrderCreate, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    event = load_event(db, ctx, event_id)
    if event is None:
        raise resource_not_found()
    authorize(ctx, "manage_test_order", event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event_id)
    service.require_enabled()
    if event.event_type != "doctor_consult":
        raise HTTPException(422, "Open examinations from a doctor consultation")
    op = service.operation(db, ctx, event_id, body)
    if op[2] is not None:
        return op[2]
    coordinator = service.assignee(db, event.clinic_id, body.coordinator_id or ctx.user_id, {"staff", "clinician"})
    reviewer = service.assignee(db, event.clinic_id, body.reviewer_id or ctx.user_id, {"clinician"})
    if body.legacy_task_id:
        from ..clinic_scope import load_task
        legacy = load_task(db, ctx, body.legacy_task_id)
        if legacy is None or legacy.patient_id != event.patient_id or legacy.task_kind != "care_action":
            raise HTTPException(422, "Choose an existing care task from this patient")
    order_id = stable_id("test_order", op[0])
    now = service.now_utc()
    workflow_id = stable_id("test_workflow", order_id)
    ensure_workflow(db, workflow_id=workflow_id, clinic_id=event.clinic_id, patient_id=event.patient_id,
        workflow_kind="care_action_chain", root_event_id=event_id, created_by_role=ctx.role, created_by_user_id=ctx.user_id, created_at=now)
    row = TestOrder(order_id=order_id, clinic_id=event.clinic_id, patient_id=event.patient_id, event_id=event_id,
        workflow_id=workflow_id, title=body.title, reason=body.reason, expected_at=service.utc(db, event.clinic_id, body.expected_at),
        coordinator_id=coordinator.user_id, reviewer_id=reviewer.user_id, legacy_task_id=body.legacy_task_id,
        created_by=ctx.user_id, created_at=now, updated_at=now, revision=1)
    db.add(row)
    return service.finish(db, row, ctx, op, "test_order_created")


@router.get("/patients/{patient_id}/test-orders")
def list_orders(patient_id: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_test_results", patient.clinic_id, patient_id)
    return [out(db, row) for row in db.scalars(select(TestOrder).where(TestOrder.patient_id == patient_id,
            TestOrder.clinic_id == ctx.clinic_id).order_by(TestOrder.created_at.desc())).all()]


@router.get("/test-orders/{order_id}")
def detail(order_id: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    order = scoped(db, ctx, order_id)
    reports = db.scalars(select(TestReport).where(TestReport.order_id == order_id).order_by(TestReport.version.desc())).all()
    reviews = db.scalars(select(TestReview).join(TestReport).where(TestReport.order_id == order_id).order_by(TestReview.created_at.desc())).all()
    comms = db.scalars(select(TestCommunication).where(TestCommunication.order_id == order_id).order_by(TestCommunication.created_at.desc())).all()
    publications = db.scalars(select(PatientInstructionPublication).join(Artifact,
        Artifact.artifact_id == PatientInstructionPublication.instruction_artifact_id).where(
        PatientInstructionPublication.patient_id == order.patient_id, PatientInstructionPublication.clinic_id == ctx.clinic_id,
        PatientInstructionPublication.state == "published", Artifact.event_id == order.result_event_id)).all()
    return out(db, order) | {
        "reports": [{"report_id": r.report_id, "version": r.version, "sha256": r.sha256, "issued_at": r.issued_at,
            "uploaded_by": r.uploaded_by, "created_at": r.created_at, "withdrawn_reason": r.withdrawn_reason,
            "external_source": db.get(Artifact, r.artifact_id).content["external_source"], "artifact_id": r.artifact_id} for r in reports],
        "reviews": [{"review_id": r.review_id, "report_id": r.report_id, "outcome": r.outcome, "clinician_id": r.clinician_id,
            "conclusion": db.get(Artifact, r.artifact_id).content["conclusion"], "follow_up_task_id": r.follow_up_task_id, "created_at": r.created_at} for r in reviews],
        "communications": [{k: getattr(r, k) for k in ("communication_id", "review_id", "method", "outcome", "performed_at", "performed_by", "publication_id")} for r in comms],
        "publications": [{"publication_id": p.publication_id, "artifact_id": p.instruction_artifact_id, "artifact_version": p.artifact_version} for p in publications]}


@router.patch("/test-orders/{order_id}")
def change(order_id: str, body: OrderUpdate, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    order = scoped(db, ctx, order_id, "manage_test_order")
    service.require_enabled()
    op = service.operation(db, ctx, order_id + ":update", body)
    if op[2] is not None:
        return op[2]
    service.lock_order(db, order, body.expected_revision)
    for field, roles in (("coordinator_id", {"staff", "clinician"}), ("reviewer_id", {"clinician"})):
        if getattr(body, field):
            setattr(order, field, service.assignee(db, order.clinic_id, getattr(body, field), roles).user_id)
    if body.expected_at:
        order.expected_at = service.utc(db, order.clinic_id, body.expected_at)
    if body.cancel_reason:
        service.invalidate_guidance(db, order, ctx)
        order.cancelled_reason = body.cancel_reason
    return service.finish(db, order, ctx, op, "test_order_updated")


@router.get("/test-orders/{order_id}/reports")
def reports(order_id: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    return detail(order_id, db, ctx)["reports"]


@router.post("/test-orders/{order_id}/reports")
def upload(order_id: str, body: ReportUpload, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    order = scoped(db, ctx, order_id, "upload_test_report")
    service.require_enabled()
    op = service.operation(db, ctx, order_id + ":report", body)
    if op[2] is not None:
        return op[2]
    try:
        data = base64.b64decode(body.file_base64, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Invalid PDF encoding")
    if not body.filename.lower().endswith(".pdf") or not data.startswith(b"%PDF-") or b"%%EOF" not in data[-1024:] or len(data) > 10 * 1024 * 1024:
        raise HTTPException(422, "Upload a PDF of at most 10 MiB")
    digest = hashlib.sha256(data).hexdigest()
    duplicate = db.scalar(select(TestReport).where(TestReport.order_id == order_id, TestReport.sha256 == digest, TestReport.withdrawn_reason.is_(None)))
    if duplicate:
        from ..result_models import ResultOperation
        response = {"order_id": order.order_id, "revision": order.revision, "stage": service.stage(db, order)}
        db.get(ResultOperation, op[0]).response = response
        db.commit()
        return response
    service.lock_order(db, order, body.expected_revision)
    service.invalidate_guidance(db, order, ctx)
    issued = service.utc(db, order.clinic_id, body.issued_at)
    if order.result_event_id is None:
        event = Event(event_id=new_id("evt"), clinic_id=order.clinic_id, patient_id=order.patient_id,
                      event_type="test_result", started_at=issued, created_at=service.now_utc())
        db.add(event)
        db.flush()
        order.result_event_id = event.event_id
    report_id = new_id("report")
    version = (db.scalar(select(func.max(TestReport.version)).where(TestReport.order_id == order_id)) or 0) + 1
    art = service.artifact(db, order, "external_test_report", {"external_source": body.external_source,
        "report_id": report_id, "report_version": version, "sha256": digest, "uploaded_by": ctx.user_id}, ctx,
        {"report_id": report_id, "version": version, "kind": "file"})
    report = TestReport(report_id=report_id, order_id=order_id, artifact_id=art.artifact_id, version=version,
        sha256=digest, file_bytes=data, issued_at=issued, uploaded_by=ctx.user_id, created_at=service.now_utc())
    db.add(report)
    order.current_report_id = report_id
    return service.finish(db, order, ctx, op, "test_report_received")


@router.get("/test-reports/{report_id}/file")
def download(report_id: str, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    report, _ = report_scope(db, ctx, report_id)
    return Response(report.file_bytes, media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="report-v{report.version}.pdf"',
        "Cache-Control": "no-store, private", "Pragma": "no-cache", "X-Content-Type-Options": "nosniff"})


@router.post("/test-reports/{report_id}/withdraw")
def withdraw(report_id: str, body: WithdrawReport, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    report, order = report_scope(db, ctx, report_id, "manage_test_order")
    service.require_enabled()
    op = service.operation(db, ctx, report_id + ":withdraw", body)
    if op[2] is not None:
        return op[2]
    service.lock_order(db, order, body.expected_revision)
    report.withdrawn_reason = body.reason
    if order.current_report_id == report_id:
        service.invalidate_guidance(db, order, ctx)
        order.current_report_id = None
    return service.finish(db, order, ctx, op, "test_report_withdrawn")


@router.post("/test-reports/{report_id}/reviews")
def review(report_id: str, body: ReviewCreate, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    report, order = report_scope(db, ctx, report_id, "review_test_report")
    service.require_enabled()
    op = service.operation(db, ctx, report_id + ":review", body)
    if op[2] is not None:
        return op[2]
    service.lock_order(db, order, body.expected_revision)
    if order.current_report_id != report_id or report.withdrawn_reason:
        raise HTTPException(409, "Review the current valid report")
    service.invalidate_guidance(db, order, ctx)
    followup = None
    if body.outcome != "no_action":
        if not all((body.follow_up_title, body.follow_up_owner_id, body.follow_up_due_at)):
            raise HTTPException(422, "Observation and action require a responsible person and dated follow-up task")
        owner = service.assignee(db, order.clinic_id, body.follow_up_owner_id, {"staff", "clinician"})
        # A separate care-action workflow avoids the legacy unique role/kind constraint;
        # the review's explicit FK keeps it attached to this result's closure gate.
        followup = Task(task_id=new_id("tsk"), patient_id=order.patient_id, clinic_id=order.clinic_id,
            event_id=order.result_event_id, title=body.follow_up_title, description="Follow-up from reviewed examination",
            task_kind="care_action", assigned_role=owner.role, assigned_user_id=owner.user_id, patient_visible=False,
            status="open", due_at=service.utc(db, order.clinic_id, body.follow_up_due_at), routing_metadata={"test_order_id": order.order_id, "due_timezone": "UTC"},
            created_by=ctx.user_id, created_at=service.now_utc(), updated_at=service.now_utc())
        db.add(followup)
        db.flush()
        from ..workflow_state import ensure_task_workflow
        ensure_task_workflow(db, followup)
    art = service.artifact(db, order, "test_result_review", {"conclusion": body.conclusion, "outcome": body.outcome}, ctx,
        {"artifact_id": report.artifact_id, "report_id": report_id, "kind": "file", "version": report.version})
    item = TestReview(review_id=new_id("rev"), report_id=report_id, artifact_id=art.artifact_id,
        outcome=body.outcome, follow_up_task_id=followup.task_id if followup else None, clinician_id=ctx.user_id, created_at=service.now_utc())
    db.add(item)
    order.current_review_id = item.review_id
    return service.finish(db, order, ctx, op, "test_result_reviewed")


@router.post("/test-orders/{order_id}/communications")
def communicate(order_id: str, body: CommunicationCreate, db: Session = Depends(get_db), ctx: RoleContext = Depends(require_auth)):
    order = scoped(db, ctx, order_id, "communicate_test_result")
    service.require_enabled()
    op = service.operation(db, ctx, order_id + ":communicate", body)
    if op[2] is not None:
        return op[2]
    service.lock_order(db, order, body.expected_revision)
    if order.current_review_id != body.review_id or service.stage(db, order) not in {"waiting_communication", "completed"}:
        raise HTTPException(409, "Communicate the current clinician review")
    performed = service.utc(db, order.clinic_id, body.performed_at)
    review = db.get(TestReview, order.current_review_id)
    if performed < review.created_at or performed > service.now_utc():
        raise HTTPException(422, "Communication time must follow the review and cannot be in the future")
    publication = None
    if body.method == "portal":
        publication = db.scalar(select(PatientInstructionPublication).join(Artifact,
            Artifact.artifact_id == PatientInstructionPublication.instruction_artifact_id).where(
            PatientInstructionPublication.publication_id == body.publication_id,
            PatientInstructionPublication.clinic_id == ctx.clinic_id, PatientInstructionPublication.patient_id == order.patient_id,
            Artifact.event_id == order.result_event_id, PatientInstructionPublication.state == "published",
            Artifact.generation_metadata["test_review_id"].as_string() == review.review_id))
        if publication is None or body.outcome != "delivered":
            raise HTTPException(422, "Select a current published instruction created for this reviewed result")
        # A conditional write serializes with correction/withdrawal on this same publication.
        touched = db.execute(update(PatientInstructionPublication).where(
            PatientInstructionPublication.publication_id == publication.publication_id,
            PatientInstructionPublication.state == "published").values(updated_at=service.now_utc()))
        if touched.rowcount != 1:
            raise HTTPException(409, "Instruction publication changed")
    elif body.publication_id is not None:
        raise HTTPException(422, "Offline communication cannot bind a publication")
    art = service.artifact(db, order, "test_result_communication", {"method": body.method, "outcome": body.outcome,
        "performed_at": performed.isoformat(), "review_id": body.review_id}, ctx,
        {"artifact_id": review.artifact_id, "kind": "section", "index": "conclusion"})
    db.add(TestCommunication(communication_id=new_id("com"), order_id=order_id, review_id=body.review_id,
        artifact_id=art.artifact_id, publication_id=publication.publication_id if publication else None,
        method=body.method, outcome=body.outcome, performed_by=ctx.user_id, performed_at=performed, created_at=service.now_utc()))
    return service.finish(db, order, ctx, op, "test_result_communicated")
