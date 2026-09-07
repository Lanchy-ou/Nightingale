"""Read-only event artifact endpoints (under unified authorization)."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..authz import PATIENT_VISIBLE_ARTIFACT_TYPES, authorize, require_auth, resource_not_found
from ..db import get_db
from ..clinic_scope import load_event
from ..checkin_visibility import require_checkin_event_visible
from ..models import Artifact, Event, PatientInstructionPublication
from ..role_context import RoleContext
from ..schemas import ArtifactOut

router = APIRouter(prefix="/api", tags=["events"])


@router.get("/events/{event_id}/artifacts", response_model=list[ArtifactOut])
def list_artifacts(
    event_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = load_event(db, ctx, event_id)
    if event is None:
        raise resource_not_found()
    authorize(ctx, "read_artifacts", event.clinic_id, event.patient_id)

    require_checkin_event_visible(db, event_id)

    q = select(Artifact).where(Artifact.event_id == event_id)
    if ctx.role == "admin":
        from ..test_result_service import RESULT_ARTIFACT_TYPES
        q = q.where(Artifact.artifact_type.not_in(RESULT_ARTIFACT_TYPES))
    if ctx.role == "patient":
        q = (
            q.join(
                PatientInstructionPublication,
                (PatientInstructionPublication.instruction_artifact_id == Artifact.artifact_id)
                & (PatientInstructionPublication.artifact_version == Artifact.version),
            )
            .where(
                Artifact.artifact_type.in_(PATIENT_VISIBLE_ARTIFACT_TYPES),
                PatientInstructionPublication.state == "published",
                PatientInstructionPublication.clinic_id == event.clinic_id,
                PatientInstructionPublication.patient_id == event.patient_id,
            )
        )

    return db.scalars(q.order_by(Artifact.created_at, Artifact.artifact_id)).all()
