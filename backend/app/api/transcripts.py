"""D3 raw transcript normalization preview API (no persistence, no LLM)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..authz import authorize, require_auth
from ..role_context import RoleContext
from ..nurse_transcript_normalizer import normalize_nurse_transcript
from ..schemas import (
    NurseTranscriptNormalizeOut,
    TranscriptNormalizeOut,
    TranscriptNormalizeRequest,
)
from ..transcript_normalizer import normalize_transcript


router = APIRouter(prefix="/api/transcripts", tags=["transcripts"])


@router.post("/normalize", response_model=TranscriptNormalizeOut)
def normalize_transcript_preview(
    body: TranscriptNormalizeRequest,
    ctx: RoleContext = Depends(require_auth),
):
    # New Doctor Consult is clinician-only.  No patient resource is resolved or
    # read at preview time; DB-backed identity is still the authorization source.
    authorize(ctx, "normalize_doctor_transcript", ctx.clinic_id, None)
    result = normalize_transcript(body.raw_text)
    if result.reason == "INPUT_TOO_LONG":
        raise HTTPException(status_code=413, detail=result.reason)
    if result.reason in {"EMPTY_INPUT", "TOO_MANY_SEGMENTS", "SEGMENT_TEXT_TOO_LONG"}:
        raise HTTPException(status_code=422, detail=result.reason)
    return TranscriptNormalizeOut(
        outcome=result.outcome,
        normalize_reason=result.reason,
        raw_byte_length=result.raw_byte_length,
        segments=[segment.__dict__ for segment in result.segments],
        issues=result.issues,
    )


@router.post("/nurse-normalize", response_model=NurseTranscriptNormalizeOut)
def normalize_nurse_transcript_preview(
    body: TranscriptNormalizeRequest,
    ctx: RoleContext = Depends(require_auth),
):
    authorize(ctx, "normalize_nurse_transcript", ctx.clinic_id, None)
    result = normalize_nurse_transcript(body.raw_text)
    if result.reason == "INPUT_TOO_LONG":
        raise HTTPException(status_code=413, detail=result.reason)
    if result.reason in {"EMPTY_INPUT", "TOO_MANY_SEGMENTS", "SEGMENT_TEXT_TOO_LONG"}:
        raise HTTPException(status_code=422, detail=result.reason)
    return NurseTranscriptNormalizeOut(
        outcome=result.outcome,
        normalize_reason=result.reason,
        raw_byte_length=result.raw_byte_length,
        segments=[segment.__dict__ for segment in result.segments],
        issues=result.issues,
    )
