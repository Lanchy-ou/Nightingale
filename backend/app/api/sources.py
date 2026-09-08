"""Source ingestion + AI generation APIs (M4).

Transaction order (per M4 §10):
  1. authorize + validate input;
  2. check idempotency key — replay if a complete derived result exists;
  3. create Event (sessions) + raw Artifact, commit;
  4. run redaction/provider/fallback pipeline;
  5. atomically persist AI summary + valid Highlights;
  6. return an explicit status (never half a summary + half highlights).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..ingestion_service import (
    _create_consult, ingest_confirmed_voice_transcript, ingest_existing_event, ingest_patient_session,
)
from ..authz import authorize, authorize_scope, require_auth, resource_not_found
from ..checkin_visibility import require_checkin_event_visible
from ..db import get_db
from ..clinic_scope import load_event, load_patient
from ..ids import stable_id
from ..role_context import RoleContext
from ..schemas import (
    DoctorConsultCreate,
    DoctorConsultOut,
    NurseConsultCreate,
    NurseConsultOut,
    SessionIngestRequest,
    SourceIngestRequest,
)

router = APIRouter(prefix="/api", tags=["sources"])


def _derive_summary_id(source_artifact_id: str, summary_type: str) -> str:
    return f"art_{stable_id(source_artifact_id, summary_type)}"


def _session_event_id(patient_id: str, session_id: str) -> str:
    return f"evt_{stable_id(patient_id, session_id)}"


def _doctor_consult_ids(clinic_id: str, patient_id: str, consult_id: str) -> tuple[str, str, str]:
    """Stable Event, encounter, and raw Transcript identities for a consult."""
    event_id = f"evt_{stable_id('doctor_consult', clinic_id, patient_id, consult_id)}"
    encounter_id = f"enc_{stable_id('clinic_visit', clinic_id, patient_id, consult_id)}"
    source_id = f"art_{stable_id('doctor_transcript', clinic_id, patient_id, consult_id)}"
    return event_id, encounter_id, source_id


def _nurse_consult_ids(clinic_id: str, patient_id: str, consult_id: str) -> tuple[str, str, str]:
    event_id = f"evt_{stable_id('nurse_consult', clinic_id, patient_id, consult_id)}"
    # Default encounter identity is role/event-specific. Nurse and Doctor may
    # share a human-entered consult label without being grouped implicitly;
    # only an explicit request encounter_id may join their Clinic Visit.
    encounter_id = f"enc_{stable_id('clinic_visit', 'nurse_consult', clinic_id, patient_id, consult_id)}"
    source_id = f"art_{stable_id('nurse_transcript', clinic_id, patient_id, consult_id)}"
    return event_id, encounter_id, source_id


@router.post(
    "/patients/{patient_id}/doctor-consults",
    response_model=DoctorConsultOut,
)
def create_doctor_consult(
    patient_id: str,
    body: DoctorConsultCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Create one new Doctor Consult Event and ingest its immutable Transcript.

    Event + raw Transcript are committed before the existing AI pipeline runs.
    A retry with the same consult/ingestion identity reuses every stable row.
    """
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    result = _create_consult(
        db=db,
        ctx=ctx,
        patient=patient,
        body=body,
        event_type="doctor_consult",
        action="create_doctor_consult",
        audit_action="doctor_consult_create",
        summary_type="ai_doctor_consult_summary",
        ids=_doctor_consult_ids(patient.clinic_id, patient.patient_id, body.consult_id),
        audit_details={
            "speaker_labels_reviewed": body.speaker_labels_reviewed,
            "mixed_language_content_reviewed": body.mixed_language_content_reviewed,
            "medication_dosage_mentions_reviewed": body.medication_dosage_mentions_reviewed,
        },
    )
    return DoctorConsultOut(
        event=result["event"],
        encounter_id=result["encounter_id"],
        source_artifact_id=result["source_artifact_id"],
        ai_summary_artifact_id=result["ai_summary_artifact_id"],
        highlight_ids=result["highlight_ids"],
        generation_method=result["generation_method"],
        degraded=result["degraded"],
        fallback_reason=result["fallback_reason"],
        idempotent_replay=result["idempotent_replay"],
    )


@router.post(
    "/patients/{patient_id}/nurse-consults",
    response_model=NurseConsultOut,
)
def create_nurse_consult(
    patient_id: str,
    body: NurseConsultCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    """Create a separate Nurse Consult Event under staff authority."""
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    result = _create_consult(
        db=db,
        ctx=ctx,
        patient=patient,
        body=body,
        event_type="nurse_consult",
        action="create_nurse_consult",
        audit_action="nurse_consult_create",
        summary_type="ai_nurse_consult_summary",
        ids=_nurse_consult_ids(patient.clinic_id, patient.patient_id, body.consult_id),
        requested_encounter_id=body.encounter_id,
    )
    return NurseConsultOut(
        event=result["event"],
        encounter_id=result["encounter_id"],
        source_artifact_id=result["source_artifact_id"],
        ai_summary_artifact_id=result["ai_summary_artifact_id"],
        highlight_ids=result["highlight_ids"],
        generation_method=result["generation_method"],
        degraded=result["degraded"],
        fallback_reason=result["fallback_reason"],
        idempotent_replay=result["idempotent_replay"],
    )


@router.post("/events/{event_id}/sources")
def ingest_source(
    event_id: str,
    body: SourceIngestRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = load_event(db, ctx, event_id)
    if event is None:
        raise resource_not_found()

    # Scope BEFORE any role/type branching: cross-clinic and not-own-patient are
    # always a uniform 404, never a type/role hint.
    authorize_scope(ctx, event.clinic_id, event.patient_id)
    require_checkin_event_visible(db, event_id)

    if ctx.role == "staff":
        if event.event_type != "nurse_consult":
            raise HTTPException(status_code=422, detail="staff can only ingest nurse_consult transcripts")
        action = "ingest_nurse_transcript"
        summary_type = "ai_nurse_consult_summary"
    elif ctx.role == "clinician":
        if event.event_type != "doctor_consult":
            raise HTTPException(status_code=422, detail="clinician can only ingest doctor_consult transcripts")
        action = "ingest_doctor_transcript"
        summary_type = "ai_doctor_consult_summary"
    else:
        raise HTTPException(status_code=403, detail="Forbidden")

    authorize(ctx, action, event.clinic_id, event.patient_id)

    return ingest_existing_event(db, event, body, ctx, summary_type)


@router.post("/patients/{patient_id}/sessions")
def ingest_session(
    patient_id: str,
    body: SessionIngestRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "create_patient_session", patient.clinic_id, patient.patient_id)

    if body.ended_at is not None and body.ended_at < body.started_at:
        raise HTTPException(status_code=422, detail="ended_at must be >= started_at")

    return ingest_patient_session(db, patient, body, ctx)
