"""Note creation/edit, revision history, diff, and revert (M3).

Concurrency: editable artifacts use an `expected_version` optimistic lock.
A stale write is rejected with 409 via an atomic conditional UPDATE, never a
read-then-write comparison. A conflict is recorded to AuditLog in its own
transaction (independent of any rolled-back business write).
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, note_edit_action, require_auth, resource_not_found
from ..checkin_visibility import require_checkin_event_visible
from ..copilot_confirmation import audit_details, validate_confirmation_token
from ..db import get_db
from ..clinic_scope import load_artifact_with_event, load_event
from ..ids import new_id
from ..instruction_publications import (
    create_draft_publication,
    normalize_instruction_content,
)
from ..models import Artifact, ArtifactVersion, Event
from ..revisions import diff_text
from ..role_context import RoleContext
from ..schemas import (
    ArtifactOut,
    ArtifactUpdate,
    ArtifactVersionOut,
    DiffOut,
    NoteCreate,
    RevertRequest,
)

router = APIRouter(prefix="/api", tags=["notes"])


def _validate_patient_instruction(content: dict) -> None:
    try:
        normalize_instruction_content(content)
    except ValueError:
        raise HTTPException(status_code=422, detail="Invalid patient instruction")


def _event(db: Session, ctx: RoleContext, event_id: str) -> Event:
    event = load_event(db, ctx, event_id)
    if event is None:
        raise resource_not_found()
    require_checkin_event_visible(db, event_id)
    return event


def _artifact_with_event(
    db: Session, ctx: RoleContext, artifact_id: str
) -> tuple[Artifact, Event]:
    scoped = load_artifact_with_event(db, ctx, artifact_id)
    if scoped is None:
        raise resource_not_found()
    artifact, event = scoped
    require_checkin_event_visible(db, event.event_id)
    return artifact, event


def _record_conflict(db: Session, ctx: RoleContext, event: Event, artifact_id: str, expected_version: int) -> None:
    # End the failed/stale business transaction first, then persist the audit in
    # a fresh transaction so the conflict record cannot be rolled back with it.
    clinic_id = event.clinic_id
    patient_id = event.patient_id
    event_id = event.event_id
    db.rollback()
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="conflict",
        target_type="artifact",
        target_id=artifact_id,
        clinic_id=clinic_id,
        patient_id=patient_id,
        event_id=event_id,
        from_version=expected_version,
        to_version=None,
    )
    db.commit()


def _conflict_response(
    db: Session, ctx: RoleContext, artifact_id: str, expected_version: int
) -> JSONResponse:
    scoped = load_artifact_with_event(db, ctx, artifact_id)
    current = scoped[0] if scoped is not None else None
    return JSONResponse(
        status_code=409,
        content={
            "error": {
                "code": "conflict",
                "message": "Stale write: expected_version does not match current version",
                "expected_version": expected_version,
                "current_version": current.version if current else None,
                "current_content": current.content if current else None,
            }
        },
    )


@router.post("/events/{event_id}/notes", response_model=ArtifactOut)
def create_note(
    event_id: str,
    body: NoteCreate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    event = _event(db, ctx, event_id)
    # author_role is derived from role context only; never trusted from client.
    authorize(ctx, f"write_{body.artifact_type}", event.clinic_id, event.patient_id)
    if body.artifact_type == "patient_instruction":
        _validate_patient_instruction(body.content)
    confirmation = validate_confirmation_token(
        body.confirmation_token,
        db=db,
        ctx=ctx,
        event=event,
        expected_type=body.artifact_type,
        content=body.content,
    )

    now = datetime.now()
    artifact_id = new_id("art")
    artifact = Artifact(
            artifact_id=artifact_id,
            event_id=event_id,
            artifact_type=body.artifact_type,
            author_role=ctx.role,
            author_id=ctx.user_id,
            content=body.content,
            created_at=now,
            version=1,
            provenance_pointer=None,
        )
    db.add(artifact)
    db.add(
        ArtifactVersion(
            version_id=new_id("ver"),
            artifact_id=artifact_id,
            version=1,
            content=body.content,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            created_at=now,
        )
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="create_note",
        target_type="artifact",
        target_id=artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event_id,
        from_version=None,
        to_version=1,
        details=audit_details(confirmation),
    )
    if body.artifact_type == "patient_instruction":
        create_draft_publication(db, artifact, event, ctx.user_id)
    db.commit()
    artifact = db.get(Artifact, artifact_id)
    return artifact


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactOut)
def edit_artifact(
    artifact_id: str,
    body: ArtifactUpdate,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event = _artifact_with_event(db, ctx, artifact_id)
    # Scope must be checked before artifact-type branching; otherwise a caller
    # from another clinic can distinguish editable from non-editable resources.
    authorize(ctx, "read_artifacts", event.clinic_id, event.patient_id)
    action = note_edit_action(artifact.artifact_type)
    if action is None:
        raise HTTPException(status_code=403, detail="This artifact type is not editable")
    authorize(ctx, action, event.clinic_id, event.patient_id)

    if body.expected_version != artifact.version:
        _record_conflict(db, ctx, event, artifact_id, body.expected_version)
        return _conflict_response(db, ctx, artifact_id, body.expected_version)

    new_version = artifact.version + 1
    # Atomic compare-and-swap: version only bumps if still at expected_version.
    result = db.execute(
        update(Artifact)
        .where(Artifact.artifact_id == artifact_id, Artifact.version == body.expected_version)
        .values(version=new_version, content=body.content)
    )
    if result.rowcount != 1:
        _record_conflict(db, ctx, event, artifact_id, body.expected_version)
        return _conflict_response(db, ctx, artifact_id, body.expected_version)

    db.add(
        ArtifactVersion(
            version_id=new_id("ver"),
            artifact_id=artifact_id,
            version=new_version,
            content=body.content,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            created_at=datetime.now(),
        )
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="edit_note",
        target_type="artifact",
        target_id=artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        from_version=body.expected_version,
        to_version=new_version,
    )
    db.commit()
    scoped = load_artifact_with_event(db, ctx, artifact_id)
    return scoped[0] if scoped is not None else None


@router.post("/artifacts/{artifact_id}/revert", response_model=ArtifactOut)
def revert_artifact(
    artifact_id: str,
    body: RevertRequest,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event = _artifact_with_event(db, ctx, artifact_id)
    authorize(ctx, "read_artifacts", event.clinic_id, event.patient_id)
    action = note_edit_action(artifact.artifact_type)
    if action is None:
        raise HTTPException(status_code=403, detail="This artifact type is not editable")
    authorize(ctx, action, event.clinic_id, event.patient_id)

    target = db.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == body.to_version,
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail=f"Version {body.to_version} not found")

    if body.expected_version != artifact.version:
        _record_conflict(db, ctx, event, artifact_id, body.expected_version)
        return _conflict_response(db, ctx, artifact_id, body.expected_version)

    new_version = artifact.version + 1
    result = db.execute(
        update(Artifact)
        .where(Artifact.artifact_id == artifact_id, Artifact.version == body.expected_version)
        .values(version=new_version, content=target.content)
    )
    if result.rowcount != 1:
        _record_conflict(db, ctx, event, artifact_id, body.expected_version)
        return _conflict_response(db, ctx, artifact_id, body.expected_version)

    db.add(
        ArtifactVersion(
            version_id=new_id("ver"),
            artifact_id=artifact_id,
            version=new_version,
            content=target.content,
            actor_id=ctx.user_id,
            actor_role=ctx.role,
            created_at=datetime.now(),
        )
    )
    add_audit(
        db,
        actor_id=ctx.user_id,
        actor_role=ctx.role,
        action="revert",
        target_type="artifact",
        target_id=artifact_id,
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        event_id=event.event_id,
        from_version=body.expected_version,
        to_version=new_version,
    )
    db.commit()
    scoped = load_artifact_with_event(db, ctx, artifact_id)
    return scoped[0] if scoped is not None else None


@router.get("/artifacts/{artifact_id}/versions", response_model=list[ArtifactVersionOut])
def list_versions(
    artifact_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event = _artifact_with_event(db, ctx, artifact_id)
    authorize(ctx, "read_versions", event.clinic_id, event.patient_id)
    return db.scalars(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version)
    ).all()


@router.get("/artifacts/{artifact_id}/diff", response_model=DiffOut)
def get_diff(
    artifact_id: str,
    since: int,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event = _artifact_with_event(db, ctx, artifact_id)
    authorize(ctx, "read_versions", event.clinic_id, event.patient_id)

    since_v = db.scalar(
        select(ArtifactVersion).where(
            ArtifactVersion.artifact_id == artifact_id,
            ArtifactVersion.version == since,
        )
    )
    if since_v is None:
        raise HTTPException(status_code=404, detail=f"Version {since} not found")

    latest = db.scalar(
        select(ArtifactVersion)
        .where(ArtifactVersion.artifact_id == artifact_id)
        .order_by(ArtifactVersion.version.desc())
        .limit(1)
    )
    return DiffOut(
        artifact_id=artifact_id,
        since_version=since,
        to_version=latest.version,
        diff=diff_text(since_v.content, latest.content),
    )
