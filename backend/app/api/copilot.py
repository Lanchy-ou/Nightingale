"""Clinician-only D4 Evidence-Bound Copilot query endpoint."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..authz import authorize, require_auth, resource_not_found
from ..copilot import answer_query
from ..copilot_models import CopilotQuery, CopilotResponse
from ..db import get_db
from ..llm_client import build_client
from ..models import Patient
from ..role_context import RoleContext
from ..system_settings import effective_ai_config

router = APIRouter(prefix="/api", tags=["copilot"])


@router.post("/patients/{patient_id}/copilot/query", response_model=CopilotResponse)
def query_copilot(
    patient_id: str,
    body: CopilotQuery,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise resource_not_found()
    # Scope precedes the clinician-only permission, preserving uniform 404 for
    # absent/cross-clinic records and refusing patient/staff/admin use.
    authorize(ctx, "query_copilot", patient.clinic_id, patient.patient_id)
    config = effective_ai_config(db)
    client = (
        build_client(config.provider)
        if config.api_key is None
        else build_client(config.provider, api_key=config.api_key)
    )
    return answer_query(
        db,
        patient,
        body,
        client,
        config.provider,
        ctx.user_id,
    )
