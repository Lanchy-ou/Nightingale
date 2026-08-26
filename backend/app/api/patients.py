"""Read-only patient + timeline endpoints (now under unified authorization)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..authz import PATIENT_VISIBLE_ARTIFACT_TYPES, authorize, require_auth
from ..db import get_db
from ..models import Artifact, Clinic, Event, Patient
from ..role_context import RoleContext
from ..schemas import EventOut, PatientOut

router = APIRouter(prefix="/api", tags=["patients"])


@router.get("/patients/{patient_id}", response_model=PatientOut)
def get_patient(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
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
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise HTTPException(status_code=404, detail=f"Patient {patient_id} not found")
    authorize(ctx, "read_events", patient.clinic_id, patient.patient_id)

    events = db.scalars(
        select(Event).where(Event.patient_id == patient_id).order_by(Event.started_at)
    ).all()

    result: list[EventOut] = []
    for event in events:
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
