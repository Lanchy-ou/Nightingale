"""B12 clinician-owned patient-instruction publication lifecycle."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth, resource_not_found
from ..clinic_scope import load_artifact_with_event
from ..db import get_db
from ..ids import new_id, stable_id
from ..instruction_publications import (
    get_publication,
    normalize_instruction_content,
    publication_id,
)
from ..instruction_receipts import ensure_available_receipt, is_patient_instruction_available
from ..models import (
    Artifact,
    ArtifactVersion,
    PatientInstructionPublication,
)
from ..role_context import RoleContext
from ..schemas import (
    PatientInstructionCorrectionRequest,
    PatientInstructionPublicationOut,
    PatientInstructionPublishRequest,
    PatientInstructionWithdrawRequest,
)

router = APIRouter(prefix="/api/patient-instructions", tags=["instruction-publications"])


def _target(db: Session, ctx: RoleContext, artifact_id: str, action: str):
    scoped = load_artifact_with_event(db, ctx, artifact_id)
    if scoped is None:
        raise resource_not_found()
    artifact, event = scoped
    authorize(ctx, action, event.clinic_id, event.patient_id)
    if not is_patient_instruction_available(db, artifact, event):
        raise resource_not_found()
    publication = get_publication(db, artifact.artifact_id, artifact.version)
    if (
        publication is None
        or publication.clinic_id != event.clinic_id
        or publication.patient_id != event.patient_id
    ):
        raise resource_not_found()
    return artifact, event, publication


def _out(row: PatientInstructionPublication) -> PatientInstructionPublicationOut:
    return PatientInstructionPublicationOut(
        artifact_id=row.instruction_artifact_id,
        artifact_version=row.artifact_version,
        lineage_id=row.lineage_id,
        lineage_revision=row.lineage_revision,
        state=row.state,
        created_at=row.created_at,
        published_at=row.published_at,
        superseded_at=row.superseded_at,
        superseded_by_artifact_id=row.superseded_by_artifact_id,
        withdrawn_at=row.withdrawn_at,
        withdrawal_reason_code=row.withdrawal_reason_code,
    )


@router.get(
    "/{artifact_id}/publication",
    response_model=PatientInstructionPublicationOut,
)
def read_publication(
    artifact_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _artifact, _event, publication = _target(
        db, ctx, artifact_id, "read_instruction_publication"
    )
    return _out(publication)


@router.get(
    "/{artifact_id}/publication-history",
    response_model=list[PatientInstructionPublicationOut],
)
def read_publication_history(
    artifact_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    _artifact, _event, publication = _target(
        db, ctx, artifact_id, "read_instruction_publication"
    )
    rows = db.scalars(
        select(PatientInstructionPublication)
        .where(
            PatientInstructionPublication.lineage_id == publication.lineage_id,
            PatientInstructionPublication.clinic_id == publication.clinic_id,
            PatientInstructionPublication.patient_id == publication.patient_id,
        )
        .order_by(PatientInstructionPublication.lineage_revision.desc())
    ).all()
    return [_out(row) for row in rows]


@router.post(
    "/{artifact_id}/publish",
    response_model=PatientInstructionPublicationOut,
)
def publish_instruction(
    artifact_id: str,
    body: PatientInstructionPublishRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event, publication = _target(
        db, ctx, artifact_id, "publish_patient_instruction"
    )
    if publication.state == "published":
        return _out(publication)
    if publication.state != body.expected_state:
        raise HTTPException(status_code=409, detail="Instruction publication state conflict")

    now = datetime.now()
    result = db.execute(
        update(PatientInstructionPublication)
        .where(
            PatientInstructionPublication.publication_id == publication.publication_id,
            PatientInstructionPublication.state == "draft",
        )
        .values(
            state="published",
            published_by_user_id=ctx.user_id,
            published_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        current = get_publication(db, artifact.artifact_id, artifact.version)
        if current is not None and current.state == "published":
            return _out(current)
        raise HTTPException(status_code=409, detail="Instruction publication state conflict")

    ensure_available_receipt(db, artifact, event)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="instruction_published",
        target_type="publication",
        target_id=artifact.artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        details={
            "artifact_version": artifact.version,
            "lineage_id": publication.lineage_id,
            "lineage_revision": publication.lineage_revision,
        },
    )
    db.commit()
    return _out(get_publication(db, artifact.artifact_id, artifact.version))


@router.post(
    "/{artifact_id}/correct",
    response_model=PatientInstructionPublicationOut,
)
def correct_instruction(
    artifact_id: str,
    body: PatientInstructionCorrectionRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event, publication = _target(
        db, ctx, artifact_id, "correct_patient_instruction"
    )
    try:
        content = normalize_instruction_content(body.content)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient instruction")

    correction_key = f"pck_{stable_id(event.clinic_id, publication.lineage_id, body.correction_id)}"
    replay = db.scalar(
        select(PatientInstructionPublication).where(
            PatientInstructionPublication.correction_key == correction_key
        )
    )
    if replay is not None:
        replay_artifact = db.get(Artifact, replay.instruction_artifact_id)
        if replay.lineage_id == publication.lineage_id and replay_artifact and replay_artifact.content == content:
            return _out(replay)
        raise HTTPException(status_code=409, detail="Correction id payload conflict")
    if publication.state != body.expected_state:
        raise HTTPException(status_code=409, detail="Instruction publication state conflict")

    now = datetime.now()
    new_artifact_id = f"art_{stable_id('instruction-correction', event.clinic_id, publication.lineage_id, body.correction_id)}"
    new_revision = publication.lineage_revision + 1
    new_artifact = Artifact(
        artifact_id=new_artifact_id,
        event_id=event.event_id,
        artifact_type="patient_instruction",
        author_role="clinician",
        author_id=ctx.user_id,
        content=content,
        created_at=now,
        version=1,
        provenance_pointer=None,
        ingestion_key=None,
        generation_metadata=None,
    )
    db.add(new_artifact)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        replay = db.scalar(
            select(PatientInstructionPublication).where(
                PatientInstructionPublication.correction_key == correction_key
            )
        )
        replay_artifact = (
            db.get(Artifact, replay.instruction_artifact_id) if replay is not None else None
        )
        if replay is not None and replay_artifact and replay_artifact.content == content:
            return _out(replay)
        raise HTTPException(status_code=409, detail="Correction id payload conflict")
    result = db.execute(
        update(PatientInstructionPublication)
        .where(
            PatientInstructionPublication.publication_id == publication.publication_id,
            PatientInstructionPublication.state == "published",
        )
        .values(
            state="superseded",
            superseded_by_artifact_id=new_artifact_id,
            superseded_at=now,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        raise HTTPException(status_code=409, detail="Instruction publication state conflict")

    db.add(
        ArtifactVersion(
            version_id=new_id("ver"),
            artifact_id=new_artifact_id,
            version=1,
            content=content,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            created_at=now,
        )
    )
    new_publication = PatientInstructionPublication(
        publication_id=publication_id(new_artifact_id, 1),
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        lineage_id=publication.lineage_id,
        lineage_revision=new_revision,
        instruction_artifact_id=new_artifact_id,
        artifact_version=1,
        state="published",
        created_by_user_id=ctx.user_id,
        created_at=now,
        published_by_user_id=ctx.user_id,
        published_at=now,
        superseded_by_artifact_id=None,
        superseded_at=None,
        withdrawn_by_user_id=None,
        withdrawn_at=None,
        withdrawal_reason_code=None,
        correction_key=correction_key,
        updated_at=now,
    )
    db.add(new_publication)
    ensure_available_receipt(db, new_artifact, event)
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="instruction_superseded",
        target_type="publication",
        target_id=artifact.artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        details={
            "artifact_version": artifact.version,
            "lineage_id": publication.lineage_id,
            "lineage_revision": publication.lineage_revision,
            "superseded_by_artifact_id": new_artifact_id,
        },
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="instruction_corrected",
        target_type="publication",
        target_id=new_artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        details={
            "artifact_version": 1,
            "lineage_id": publication.lineage_id,
            "lineage_revision": new_revision,
            "source_artifact_id": artifact.artifact_id,
        },
    )
    db.commit()
    return _out(new_publication)


@router.post(
    "/{artifact_id}/withdraw",
    response_model=PatientInstructionPublicationOut,
)
def withdraw_instruction(
    artifact_id: str,
    body: PatientInstructionWithdrawRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event, publication = _target(
        db, ctx, artifact_id, "withdraw_patient_instruction"
    )
    if publication.state == "withdrawn":
        if publication.withdrawal_reason_code == body.reason_code:
            return _out(publication)
        raise HTTPException(status_code=409, detail="Withdrawal reason conflict")
    if publication.state != body.expected_state:
        raise HTTPException(status_code=409, detail="Instruction publication state conflict")

    now = datetime.now()
    result = db.execute(
        update(PatientInstructionPublication)
        .where(
            PatientInstructionPublication.publication_id == publication.publication_id,
            PatientInstructionPublication.state == "published",
        )
        .values(
            state="withdrawn",
            withdrawn_by_user_id=ctx.user_id,
            withdrawn_at=now,
            withdrawal_reason_code=body.reason_code,
            updated_at=now,
        )
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        db.rollback()
        current = get_publication(db, artifact.artifact_id, artifact.version)
        if (
            current is not None
            and current.state == "withdrawn"
            and current.withdrawal_reason_code == body.reason_code
        ):
            return _out(current)
        raise HTTPException(status_code=409, detail="Instruction publication state conflict")
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="instruction_withdrawn",
        target_type="publication",
        target_id=artifact.artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        details={
            "artifact_version": artifact.version,
            "lineage_id": publication.lineage_id,
            "lineage_revision": publication.lineage_revision,
            "reason_code": body.reason_code,
        },
    )
    db.commit()
    return _out(get_publication(db, artifact.artifact_id, artifact.version))
