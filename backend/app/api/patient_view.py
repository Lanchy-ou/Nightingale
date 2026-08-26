"""M6 Patient View — read-only, minimal-information aggregate endpoint.

The patient never sees internal clinical workspace content. This endpoint is a
deterministic *read-time projection* of clinician-confirmed `patient_instruction`
artifacts only. It does NOT call an LLM, does NOT persist a second summary, and
does NOT fall back to clinician/staff notes, transcripts, AI summaries,
highlights or comments.

Visibility contract (locked by tests/test_patient_view.py):
- only `artifact_type == "patient_instruction"` with a non-empty string
  `content.instruction` is projected;
- only `instruction` / `follow_up` fields are copied (explicit projection);
- `current_summary` is the latest instruction by Event.started_at, then
  Artifact.created_at, then artifact_id;
- `upcoming` contains only non-empty `content.follow_up` strings;
- `sessions` lists only this patient's own AI-session Events (those with a
  `raw_conversation` authored by this patient).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authz import authorize, require_auth, resource_not_found
from ..db import get_db
from ..models import Artifact, Event, Patient, User
from ..role_context import RoleContext
from ..schemas import (
    PatientViewInstruction,
    PatientViewOut,
    PatientViewSession,
    PatientViewSummary,
    PatientViewUpcoming,
)

router = APIRouter(prefix="/api", tags=["patient-view"])

SESSION_EVENT_TYPES = {"patient_ai_preconsult", "patient_followup"}


def _project(content: dict) -> tuple[str | None, str | None]:
    """Return (instruction, follow_up) or (None, None) when not safely projectable.

    A missing/non-string/blank instruction drops the whole artifact — we never
    substitute another field to "fill in" a patient summary.
    """
    instruction = content.get("instruction")
    if not isinstance(instruction, str) or not instruction.strip():
        return None, None
    follow_up = content.get("follow_up")
    if not isinstance(follow_up, str) or not follow_up.strip():
        follow_up = None
    return instruction, follow_up


@router.get("/patients/{patient_id}/patient-view", response_model=PatientViewOut)
def get_patient_view(
    patient_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    patient = db.get(Patient, patient_id)
    if patient is None:
        raise resource_not_found()
    # Scope check first, then permission: cross-clinic / not-own-patient => 404;
    # same-scope non-patient => 403; anonymous => 401.
    authorize(ctx, "read_patient_view", patient.clinic_id, patient.patient_id)

    # --- instructions / upcoming / current_summary ------------------------
    # Three-layer consistency: Artifact -> Event -> Patient must all agree.
    rows = db.execute(
        select(Artifact, Event)
        .join(Event, Artifact.event_id == Event.event_id)
        .join(User, Artifact.author_id == User.user_id)
        .where(
            Event.patient_id == patient_id,
            Event.clinic_id == patient.clinic_id,
            Artifact.artifact_type == "patient_instruction",
            Artifact.author_role == "clinician",
            User.role == "clinician",
            User.clinic_id == patient.clinic_id,
        )
    ).all()

    projected: list[tuple[Artifact, Event, str, str | None]] = []
    for artifact, event in rows:
        instruction, follow_up = _project(artifact.content)
        if instruction is None:
            continue
        projected.append((artifact, event, instruction, follow_up))

    # Stable ordering: event_time desc, then created_at desc, then id desc.
    projected.sort(
        key=lambda t: (t[1].started_at, t[0].created_at, t[0].artifact_id),
        reverse=True,
    )

    instructions = [
        PatientViewInstruction(
            artifact_id=a.artifact_id,
            event_id=e.event_id,
            event_time=e.started_at,
            instruction=instruction,
            follow_up=follow_up,
        )
        for a, e, instruction, follow_up in projected
    ]

    upcoming = [
        PatientViewUpcoming(
            source_artifact_id=a.artifact_id,
            event_id=e.event_id,
            event_time=e.started_at,
            kind="follow_up",
            text=follow_up,
        )
        for a, e, instruction, follow_up in projected
        if follow_up is not None
    ]

    current_summary = None
    if projected:
        a, e, instruction, follow_up = projected[0]
        current_summary = PatientViewSummary(
            source_artifact_id=a.artifact_id,
            event_id=e.event_id,
            event_time=e.started_at,
            instruction=instruction,
            follow_up=follow_up,
        )

    # --- sessions (own AI sessions only) ----------------------------------
    session_events = db.scalars(
        select(Event).where(
            Event.patient_id == patient_id,
            Event.event_type.in_(SESSION_EVENT_TYPES),
        )
    ).all()

    # "Own" raw conversation = authored by this patient user.
    own_event_ids = set(
        db.scalars(
            select(Artifact.event_id).where(
                Artifact.artifact_type == "raw_conversation",
                Artifact.author_id == ctx.user_id,
            )
        ).all()
    )

    sessions = [
        PatientViewSession(
            event_id=e.event_id,
            event_type=e.event_type,
            started_at=e.started_at,
            ended_at=e.ended_at,
        )
        for e in session_events
        if e.event_id in own_event_ids
    ]
    sessions.sort(key=lambda s: (s.started_at, s.event_id), reverse=True)

    return PatientViewOut(
        patient_id=patient.patient_id,
        display_name=patient.name,
        current_summary=current_summary,
        instructions=instructions,
        upcoming=upcoming,
        sessions=sessions,
    )
