"""Patient Check-in lifecycle API with DB-authoritative ownership and scope."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authz import authorize, authorize_scope, require_auth, resource_not_found
from ..checkins import (
    add_patient_message,
    process_patient_message,
    save_patient_message,
    session_out,
    start_or_resume,
    submit_checkin,
    transition_state,
)
from ..checkin_visibility import CLINICALLY_VISIBLE_CHECKIN_STATUSES
from ..db import get_db
from ..clinic_scope import load_checkin, load_patient
from ..models import Patient, PatientCheckInSession
from ..role_context import RoleContext
from ..schemas import (
    CheckInListOut,
    CheckInPatientMessageRequest,
    CheckInSessionOut,
    CheckInStartRequest,
    CheckInStateRequest,
)

router = APIRouter(prefix="/api", tags=["patient-checkins"])


def _patient(db: Session, ctx: RoleContext, patient_id: str) -> Patient:
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    return patient


def _session(db: Session, session_id: str, ctx: RoleContext, action: str) -> PatientCheckInSession:
    session = load_checkin(db, ctx, session_id)
    if session is None:
        raise resource_not_found()
    authorize_scope(ctx, session.clinic_id, session.patient_id)
    if ctx.role != "patient" and session.status not in CLINICALLY_VISIBLE_CHECKIN_STATUSES:
        raise resource_not_found()
    authorize(ctx, action, session.clinic_id, session.patient_id)
    return session


@router.post(
    "/patients/{patient_id}/check-ins",
    response_model=CheckInSessionOut,
)
def start_patient_checkin(
    patient_id: str,
    body: CheckInStartRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = _patient(db, ctx, patient_id)
    authorize(ctx, "manage_patient_checkin", patient.clinic_id, patient.patient_id)
    return start_or_resume(db, patient, ctx.user_id, body.session_id)


@router.get(
    "/patients/{patient_id}/check-ins",
    response_model=CheckInListOut,
)
def list_patient_checkins(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = _patient(db, ctx, patient_id)
    authorize(ctx, "manage_patient_checkin", patient.clinic_id, patient.patient_id)
    sessions = db.scalars(
        select(PatientCheckInSession)
        .where(
            PatientCheckInSession.patient_id == patient.patient_id,
            PatientCheckInSession.clinic_id == ctx.clinic_id,
            PatientCheckInSession.patient_user_id == ctx.user_id,
            PatientCheckInSession.status != "abandoned",
        )
        .order_by(
            PatientCheckInSession.started_at.desc(),
            PatientCheckInSession.session_id.desc(),
        )
    ).all()
    active = next(
        (session.session_id for session in sessions if session.status in {"active", "awaiting_confirmation"}),
        None,
    )
    return CheckInListOut(
        active_session_id=active,
        sessions=[session_out(db, session) for session in sessions],
    )


@router.get("/check-ins/{session_id}", response_model=CheckInSessionOut)
def get_patient_checkin(
    session_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    return session_out(db, _session(db, session_id, ctx, "read_patient_checkin"), resumed=True)


@router.post("/check-ins/{session_id}/messages", response_model=CheckInSessionOut)
def post_patient_checkin_message(
    session_id: str,
    body: CheckInPatientMessageRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    patient = _patient(db, ctx, session.patient_id)
    return add_patient_message(db, patient, session, body)


@router.post("/check-ins/{session_id}/messages/save", response_model=CheckInSessionOut)
def save_patient_checkin_message(
    session_id: str,
    body: CheckInPatientMessageRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    return save_patient_message(db, session, body)


@router.post(
    "/check-ins/{session_id}/messages/{message_id}/process",
    response_model=CheckInSessionOut,
)
def process_patient_checkin_message(
    session_id: str,
    message_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    patient = _patient(db, ctx, session.patient_id)
    return process_patient_message(db, patient, session, message_id)


@router.post("/check-ins/{session_id}/finish", response_model=CheckInSessionOut)
def finish_patient_checkin(
    session_id: str,
    body: CheckInStateRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    return transition_state(db, session, body.expected_status, "awaiting_confirmation")


@router.post("/check-ins/{session_id}/resume", response_model=CheckInSessionOut)
def resume_patient_checkin(
    session_id: str,
    body: CheckInStateRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    return transition_state(db, session, body.expected_status, "active")


@router.post("/check-ins/{session_id}/abandon", response_model=CheckInSessionOut)
def abandon_patient_checkin(
    session_id: str,
    body: CheckInStateRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    return transition_state(db, session, body.expected_status, "abandoned")


@router.post("/check-ins/{session_id}/submit", response_model=CheckInSessionOut)
def confirm_patient_checkin(
    session_id: str,
    body: CheckInStateRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    session = _session(db, session_id, ctx, "manage_patient_checkin")
    patient = _patient(db, ctx, session.patient_id)
    return submit_checkin(db, patient, session, body.expected_status)
