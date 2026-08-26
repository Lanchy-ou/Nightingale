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

import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..ai_pipeline import persist_derived, run_pipeline
from ..audit import add_audit
from ..authz import authorize, authorize_scope, require_auth, resource_not_found
from ..db import get_db
from ..ids import new_id, stable_id
from ..llm_client import build_client
from ..models import Artifact, Event, Highlight, Patient
from ..role_context import RoleContext
from ..schemas import SessionIngestRequest, SourceIngestRequest

router = APIRouter(prefix="/api", tags=["sources"])


def _provider_name() -> str:
    return os.environ.get("NANTINGALE_LLM_PROVIDER", "deepseek")


def _derive_summary_id(source_artifact_id: str, summary_type: str) -> str:
    return f"art_{stable_id(source_artifact_id, summary_type)}"


def _session_event_id(patient_id: str, session_id: str) -> str:
    return f"evt_{stable_id(patient_id, session_id)}"


def _namespaced_key(*parts: str) -> str:
    return ":".join(parts)


def _existing_raw(db: Session, key: str) -> Artifact | None:
    return db.scalar(select(Artifact).where(Artifact.ingestion_key == key))


def _provider_meta(provider_name: str) -> tuple[str | None, str | None]:
    if provider_name == "deepseek":
        return "deepseek", "deepseek-v4-flash"
    return None, None


def _ingest_common(
    db: Session,
    event: Event,
    raw: Artifact,
    summary_type: str,
    ctx: RoleContext,
    patient_visible: bool,
):
    provider_name = _provider_name()
    client = build_client(provider_name)

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
    summary_id, highlight_ids = persist_derived(
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


@router.post("/events/{event_id}/sources")
def ingest_source(
    event_id: str,
    body: SourceIngestRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = db.get(Event, event_id)
    if event is None:
        raise resource_not_found()

    # Scope BEFORE any role/type branching: cross-clinic and not-own-patient are
    # always a uniform 404, never a type/role hint.
    authorize_scope(ctx, event.clinic_id, event.patient_id)

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
        db.commit()
        raw = db.get(Artifact, raw.artifact_id)

    return _ingest_common(db, event, raw, summary_type, ctx, patient_visible=False)


@router.post("/patients/{patient_id}/sessions")
def ingest_session(
    patient_id: str,
    body: SessionIngestRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise resource_not_found()
    authorize(ctx, "create_patient_session", patient.clinic_id, patient.patient_id)

    if body.ended_at is not None and body.ended_at < body.started_at:
        raise HTTPException(status_code=422, detail="ended_at must be >= started_at")

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
        db.commit()
        event = db.get(Event, event_id)
        raw = db.get(Artifact, raw.artifact_id)
    else:
        event = db.get(Event, raw.event_id)

    return _ingest_common(db, event, raw, "ai_patient_session_summary", ctx, patient_visible=True)
