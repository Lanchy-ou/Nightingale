"""Read-only patient + timeline endpoints (now under unified authorization)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..authz import PATIENT_VISIBLE_ARTIFACT_TYPES, authorize, require_auth, resource_not_found
from ..db import get_db
from ..clinic_scope import load_patient
from ..models import Artifact, Clinic, Event, Patient, PatientCheckInSession
from ..role_context import RoleContext
from ..schemas import EventOut, PatientOut

router = APIRouter(prefix="/api", tags=["patients"])


@router.get("/patients", response_model=list[PatientOut])
def list_clinic_patients(
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Minimal C1 clinic-scoped directory for the C2 clinician shell."""
    authorize(ctx, "list_clinic_patients", ctx.clinic_id, None)
    clinic = db.get(Clinic, ctx.clinic_id)
    patients = db.scalars(
        select(Patient)
        .where(Patient.clinic_id == ctx.clinic_id)
        .order_by(Patient.name, Patient.patient_id)
    ).all()
    return [
        PatientOut(
            patient_id=patient.patient_id,
            clinic_id=patient.clinic_id,
            name=patient.name,
            clinic_name=clinic.name if clinic else None,
        )
        for patient in patients
    ]


@router.get("/patients/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_patient", patient.clinic_id, patient.patient_id)
    clinic = db.get(Clinic, patient.clinic_id)
    return PatientOut(
        patient_id=patient.patient_id,
        clinic_id=patient.clinic_id,
        name=patient.name,
        clinic_name=clinic.name if clinic else None,
    )


@router.get("/patients/{patient_id}/events", response_model=list[EventOut])
def list_events(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "read_events", patient.clinic_id, patient.patient_id)

    hidden_checkin_event_ids = set(
        db.scalars(
            select(PatientCheckInSession.event_id).where(
                PatientCheckInSession.patient_id == patient_id,
                PatientCheckInSession.status.in_({"active", "awaiting_confirmation", "abandoned"}),
            )
        ).all()
    )
    events = db.scalars(
        select(Event)
        .where(
            Event.patient_id == patient_id,
            Event.clinic_id == ctx.clinic_id,
        )
        .order_by(Event.started_at, Event.event_id)
    ).all()

    result: list[EventOut] = []
    for event in events:
        if event.event_id in hidden_checkin_event_ids:
            continue
        if ctx.role == "patient":
            # artifact_count must not leak the number of hidden artifacts.
            count = db.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(
                    Artifact.event_id == event.event_id,
                    Artifact.artifact_type.in_(PATIENT_VISIBLE_ARTIFACT_TYPES),
                )
            ) or 0
        else:
            count = db.scalar(
                select(func.count())
                .select_from(Artifact)
                .where(Artifact.event_id == event.event_id)
            ) or 0
        result.append(
            EventOut.model_validate(event).model_copy(update={"artifact_count": count})
        )
    return result
