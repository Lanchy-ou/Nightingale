"""Ingestion transaction owner. Raw first; derived data is a separate atomic stage."""
from datetime import datetime
from fastapi import HTTPException
from sqlalchemy import select, func
from .audit import add_audit
from .authz import authorize, resource_not_found
from .clinic_scope import load_patient
from .schemas import DoctorConsultCreate, NurseConsultCreate, EventOut
from sqlalchemy.orm import Session
from .ai_pipeline import persist_derived, run_pipeline
from .ids import stable_id, new_id
from .llm_client import build_client
from .models import Artifact, Event, Highlight, Patient
from .role_context import RoleContext
from .system_settings import effective_ai_config


def _derive_summary_id(source_artifact_id, summary_type):
    return f"art_{stable_id(source_artifact_id, summary_type)}"


def _provider_meta(provider_name):
    return ("deepseek", "deepseek-v4-flash") if provider_name == "deepseek" else (None, None)


def commit_raw(db):
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise


def commit_derived(db, *args, **kwargs):
    try:
        result = persist_derived(db, *args, **kwargs)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def ingest_common(
    db: Session,
    event: Event,
    raw: Artifact,
    summary_type: str,
    ctx: RoleContext,
    patient_visible: bool,
):
    config = effective_ai_config(db, event.clinic_id)
    provider_name = config.provider
    client = (
        build_client(provider_name)
        if config.api_key is None
        else build_client(provider_name, api_key=config.api_key)
    )

    summary_id = _derive_summary_id(raw.artifact_id, summary_type)
    existing = db.get(Artifact, summary_id)
    if existing is not None:
        if patient_visible:
            # Idempotent replay must preserve the same patient-safe response
            # boundary as the first request. Internal derived IDs are never
            # exposed through the patient ingestion endpoint.
            return {
                "event_id": event.event_id,
                "source_artifact_id": raw.artifact_id,
                "processing_status": "completed",
                "degraded": existing.generation_metadata.get("degraded"),
            }
        highlights = db.scalars(
            select(Highlight).where(Highlight.source_artifact_id == raw.artifact_id)
        ).all()
        return {
            "event_id": event.event_id,
            "source_artifact_id": raw.artifact_id,
            "ai_summary_artifact_id": summary_id,
            "highlight_ids": [h.highlight_id for h in highlights],
            "generation_method": existing.generation_metadata.get("method"),
            "degraded": existing.generation_metadata.get("degraded"),
            "fallback_reason": existing.generation_metadata.get("fallback_reason"),
            "idempotent_replay": True,
        }

    output = run_pipeline(db, event, raw, summary_type, datetime.now(), client, provider_name)
    provider, model = _provider_meta(provider_name)
    summary_id, highlight_ids = commit_derived(
        db, event, raw, summary_type, output, ctx.user_id, ctx.role, provider, model
    )

    if patient_visible:
        # Patient never receives internal summary/highlight ids.
        return {
            "event_id": event.event_id,
            "source_artifact_id": raw.artifact_id,
            "processing_status": "completed",
            "degraded": output.degraded,
        }

    return {
        "event_id": event.event_id,
        "source_artifact_id": raw.artifact_id,
        "ai_summary_artifact_id": summary_id,
        "highlight_ids": highlight_ids,
        "generation_method": output.method,
        "degraded": output.degraded,
        "fallback_reason": output.fallback_reason,
        "idempotent_replay": False,
    }




def ingest_existing_event(db, event, body, ctx, summary_type):
    event_id = event.event_id
    key = _namespaced_key(event.clinic_id, event_id, body.ingestion_key)
    raw = _existing_raw(db, key)
    if raw is None:
        raw = Artifact(
            artifact_id=new_id("art"),
            event_id=event_id,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content=body.content,
            created_at=datetime.now(),
            version=1,
            provenance_pointer=None,
            ingestion_key=key,
        )
        db.add(raw)
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="source_ingest",
            target_type="artifact",
            target_id=raw.artifact_id,
            clinic_id=event.clinic_id,
            patient_id=event.patient_id,
            event_id=event_id,
        )
        commit_raw(db)
        raw = db.get(Artifact, raw.artifact_id)

    return ingest_common(db, event, raw, summary_type, ctx, patient_visible=False)



def ingest_patient_session(db, patient, body, ctx):
    patient_id = patient.patient_id
    key = _namespaced_key(patient.clinic_id, patient_id, body.session_id)
    event_id = _session_event_id(patient_id, body.session_id)

    raw = _existing_raw(db, key)
    if raw is None:
        event = db.get(Event, event_id)
        if event is None:
            event = Event(
                event_id=event_id,
                patient_id=patient_id,
                clinic_id=patient.clinic_id,
                event_type=body.event_type,
                started_at=body.started_at,
                ended_at=body.ended_at,
                created_at=datetime.now(),
            )
            db.add(event)
            db.flush()
        raw = Artifact(
            artifact_id=new_id("art"),
            event_id=event_id,
            artifact_type="raw_conversation",
            author_role="patient",
            author_id=ctx.user_id,
            content=body.content,
            created_at=datetime.now(),
            version=1,
            provenance_pointer=None,
            ingestion_key=key,
        )
        db.add(raw)
        db.flush()
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="source_ingest",
            target_type="artifact",
            target_id=raw.artifact_id,
            clinic_id=patient.clinic_id,
            patient_id=patient_id,
            event_id=event_id,
        )
        commit_raw(db)
        event = db.get(Event, event_id)
        raw = db.get(Artifact, raw.artifact_id)
    else:
        event = db.get(Event, raw.event_id)

    return ingest_common(db, event, raw, "ai_patient_session_summary", ctx, patient_visible=True)



def ingest_confirmed_voice_transcript(
    *,
    db: Session,
    ctx: RoleContext,
    capture_id: str,
    patient_id: str,
    event_type: str,
    started_at: datetime,
    ended_at: datetime | None,
    encounter_id: str | None,
    content: dict,
    audio_ranges: list[dict],
) -> dict:
    """Persist a confirmed voice Transcript raw-first, then reuse AI pipeline.

    This is the only Voice -> existing ingestion seam. Recording bytes and the
    machine transcript never enter the Summary LLM.
    """
    patient = load_patient(db, ctx, patient_id)
    if patient is None:
        raise resource_not_found()

    role_contract = {
        ("clinician", "doctor_consult"): (
            "create_doctor_consult",
            "ai_doctor_consult_summary",
            "doctor_consult_create",
        ),
        ("staff", "nurse_consult"): (
            "create_nurse_consult",
            "ai_nurse_consult_summary",
            "nurse_consult_create",
        ),
        ("patient", "patient_ai_preconsult"): (
            "create_patient_session",
            "ai_patient_session_summary",
            "source_ingest",
        ),
        ("patient", "patient_followup"): (
            "create_patient_session",
            "ai_patient_session_summary",
            "source_ingest",
        ),
    }
    contract = role_contract.get((ctx.role, event_type))
    if contract is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    action, summary_type, event_audit_action = contract
    authorize(ctx, action, patient.clinic_id, patient.patient_id)

    event_id = f"evt_{stable_id('voice_capture', patient.clinic_id, patient_id, capture_id)}"
    source_id = f"art_{stable_id('voice_transcript', patient.clinic_id, patient_id, capture_id)}"
    if event_type in {"doctor_consult", "nurse_consult"}:
        resolved_encounter_id = encounter_id or f"enc_{stable_id(event_type, capture_id)}"
    else:
        resolved_encounter_id = None
    key = _namespaced_key(patient.clinic_id, patient_id, "voice", capture_id)

    raw = _existing_raw(db, key)
    event = db.get(Event, event_id)
    if raw is not None:
        if raw.event_id != event_id or event is None or raw.artifact_id != source_id:
            raise HTTPException(status_code=409, detail="Voice ingestion identity conflict")
    else:
        if event is not None or db.get(Artifact, source_id) is not None:
            raise HTTPException(status_code=409, detail="Voice capture already exists")
        now = datetime.now()
        event = Event(
            event_id=event_id,
            patient_id=patient.patient_id,
            clinic_id=patient.clinic_id,
            event_type=event_type,
            encounter_id=resolved_encounter_id,
            started_at=started_at,
            ended_at=ended_at,
            created_at=now,
        )
        raw = Artifact(
            artifact_id=source_id,
            event_id=event_id,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content=content,
            created_at=now,
            version=1,
            provenance_pointer={
                "recording_capture_id": capture_id,
                "audio_ranges": audio_ranges,
            },
            ingestion_key=key,
        )
        db.add(event)
        db.flush()
        db.add(raw)
        db.flush()
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action=event_audit_action,
            target_type="event",
            target_id=event_id,
            clinic_id=patient.clinic_id,
            patient_id=patient.patient_id,
            event_id=event_id,
        )
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="source_ingest",
            target_type="artifact",
            target_id=source_id,
            clinic_id=patient.clinic_id,
            patient_id=patient.patient_id,
            event_id=event_id,
        )
        commit_raw(db)
        event = db.get(Event, event_id)
        raw = db.get(Artifact, source_id)

    result = ingest_common(
        db,
        event,
        raw,
        summary_type,
        ctx,
        patient_visible=False,
    )
    result["event_id"] = event_id
    result["source_artifact_id"] = source_id
    result["encounter_id"] = event.encounter_id
    return result


def _create_consult(
    *,
    db: Session,
    ctx: RoleContext,
    patient: Patient,
    body: DoctorConsultCreate | NurseConsultCreate,
    event_type: str,
    action: str,
    audit_action: str,
    summary_type: str,
    ids: tuple[str, str, str],
    requested_encounter_id: str | None = None,
    audit_details: dict | None = None,
) -> dict:
    """Shared raw-first orchestration; role semantics stay in each endpoint."""
    authorize(ctx, action, patient.clinic_id, patient.patient_id)
    event_id, generated_encounter_id, source_id = ids
    encounter_id = requested_encounter_id or generated_encounter_id
    key = _namespaced_key(
        patient.clinic_id,
        patient.patient_id,
        event_type,
        stable_id(body.consult_id, body.ingestion_key),
    )

    raw = _existing_raw(db, key)
    event = db.get(Event, event_id)
    if raw is not None:
        if raw.event_id != event_id or event is None:
            raise HTTPException(status_code=409, detail="Idempotency identity conflict")
    else:
        if event is not None or db.get(Artifact, source_id) is not None:
            raise HTTPException(status_code=409, detail="consult_id already exists")

        now = datetime.now()
        event = Event(
            event_id=event_id,
            patient_id=patient.patient_id,
            clinic_id=patient.clinic_id,
            event_type=event_type,
            encounter_id=encounter_id,
            started_at=body.started_at,
            ended_at=body.ended_at,
            created_at=now,
        )
        raw = Artifact(
            artifact_id=source_id,
            event_id=event_id,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content=body.content.model_dump(),
            created_at=now,
            version=1,
            provenance_pointer=None,
            ingestion_key=key,
        )
        db.add(event)
        db.flush()
        db.add(raw)
        db.flush()
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action=audit_action,
            target_type="event",
            target_id=event_id,
            clinic_id=patient.clinic_id,
            patient_id=patient.patient_id,
            event_id=event_id,
            details=audit_details,
        )
        add_audit(
            db,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            action="source_ingest",
            target_type="artifact",
            target_id=source_id,
            clinic_id=patient.clinic_id,
            patient_id=patient.patient_id,
            event_id=event_id,
        )
        commit_raw(db)
        event = db.get(Event, event_id)
        raw = db.get(Artifact, source_id)

    result = ingest_common(
        db, event, raw, summary_type, ctx, patient_visible=False
    )
    artifact_count = db.scalar(
        select(func.count()).select_from(Artifact).where(Artifact.event_id == event_id)
    ) or 0
    result["event"] = EventOut.model_validate(event).model_copy(
        update={"artifact_count": artifact_count}
    )
    result["encounter_id"] = event.encounter_id
    return result




def _namespaced_key(*parts):
    return ":".join(parts)


def _existing_raw(db, key):
    return db.scalar(select(Artifact).where(Artifact.ingestion_key == key))


def _session_event_id(patient_id, session_id):
    return f"evt_{stable_id(patient_id, session_id)}"
