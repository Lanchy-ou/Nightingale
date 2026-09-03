"""B11 in-product patient-instruction open and acknowledgement receipts."""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..audit import add_audit
from ..authz import authorize, require_auth, resource_not_found
from ..clinic_scope import load_artifact_with_event
from ..db import get_db
from ..instruction_receipts import (
    ensure_available_receipt,
    get_receipt,
    is_patient_instruction_available,
    public_status,
)
from ..instruction_publications import is_instruction_published
from ..models import PatientInstructionReceipt
from ..role_context import RoleContext
from ..schemas import (
    PatientInstructionReceiptHistoryOut,
    PatientInstructionReceiptOut,
)

router = APIRouter(prefix="/api/patient-instructions", tags=["instruction-receipts"])


def _target(
    db: Session,
    ctx: RoleContext,
    artifact_id: str,
    action: str,
    *,
    require_published: bool,
):
    scoped = load_artifact_with_event(db, ctx, artifact_id)
    if scoped is None:
        raise resource_not_found()
    artifact, event = scoped
    # Scope and role permission are resolved before artifact-type validation so
    # cross-scope callers cannot probe whether an id names an instruction.
    authorize(ctx, action, event.clinic_id, event.patient_id)
    if not is_patient_instruction_available(db, artifact, event):
        raise resource_not_found()
    if require_published and not is_instruction_published(db, artifact, event):
        raise resource_not_found()
    return artifact, event


def _out(receipt: PatientInstructionReceipt) -> PatientInstructionReceiptOut:
    return PatientInstructionReceiptOut(
        status=public_status(receipt),
        opened_at=receipt.opened_at,
        acknowledged_at=receipt.acknowledged_at,
    )


@router.post(
    "/{artifact_id}/versions/{version}/open",
    response_model=PatientInstructionReceiptOut,
)
def open_instruction(
    artifact_id: str,
    version: int,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event = _target(
        db,
        ctx,
        artifact_id,
        "open_patient_instruction",
        require_published=True,
    )
    if version != artifact.version:
        raise resource_not_found()
    receipt = get_receipt(db, artifact_id, version) or ensure_available_receipt(db, artifact, event)
    if receipt.state == "available":
        now = datetime.now()
        result = db.execute(
            update(PatientInstructionReceipt)
            .where(
                PatientInstructionReceipt.receipt_id == receipt.receipt_id,
                PatientInstructionReceipt.state == "available",
            )
            .values(
                state="opened",
                opened_by_user_id=ctx.user_id,
                opened_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            add_audit(
                db,
                actor_id=ctx.user_id,
                actor_role=ctx.role,
                action="instruction_opened",
                target_type="artifact",
                target_id=artifact_id,
                clinic_id=event.clinic_id,
                patient_id=event.patient_id,
                event_id=event.event_id,
                details={"artifact_version": version},
            )
            db.commit()
        else:
            db.rollback()
        receipt = get_receipt(db, artifact_id, version)
    return _out(receipt)


@router.post(
    "/{artifact_id}/versions/{version}/acknowledge",
    response_model=PatientInstructionReceiptOut,
)
def acknowledge_instruction(
    artifact_id: str,
    version: int,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, event = _target(
        db,
        ctx,
        artifact_id,
        "acknowledge_patient_instruction",
        require_published=True,
    )
    if version != artifact.version:
        raise resource_not_found()
    receipt = get_receipt(db, artifact_id, version) or ensure_available_receipt(db, artifact, event)
    if receipt.state == "available":
        raise HTTPException(
            status_code=409,
            detail="Open this instruction before acknowledging it",
        )
    if receipt.state == "opened":
        now = datetime.now()
        result = db.execute(
            update(PatientInstructionReceipt)
            .where(
                PatientInstructionReceipt.receipt_id == receipt.receipt_id,
                PatientInstructionReceipt.state == "opened",
            )
            .values(
                state="acknowledged",
                acknowledged_by_user_id=ctx.user_id,
                acknowledged_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if result.rowcount == 1:
            add_audit(
                db,
                actor_id=ctx.user_id,
                actor_role=ctx.role,
                action="instruction_acknowledged",
                target_type="artifact",
                target_id=artifact_id,
                clinic_id=event.clinic_id,
                patient_id=event.patient_id,
                event_id=event.event_id,
                details={"artifact_version": version},
            )
            db.commit()
        else:
            db.rollback()
        receipt = get_receipt(db, artifact_id, version)
    return _out(receipt)


@router.get(
    "/{artifact_id}/receipts",
    response_model=list[PatientInstructionReceiptHistoryOut],
)
def list_receipts(
    artifact_id: str,
    db: Session = Depends(get_db),
    ctx: RoleContext = Depends(require_auth),
):
    artifact, _event = _target(
        db,
        ctx,
        artifact_id,
        "read_instruction_receipts",
        require_published=False,
    )
    rows = db.scalars(
        select(PatientInstructionReceipt)
        .where(
            PatientInstructionReceipt.instruction_artifact_id == artifact.artifact_id,
            PatientInstructionReceipt.clinic_id == _event.clinic_id,
            PatientInstructionReceipt.patient_id == _event.patient_id,
        )
        .order_by(PatientInstructionReceipt.artifact_version.desc())
    ).all()
    return [
        PatientInstructionReceiptHistoryOut(
            artifact_id=artifact.artifact_id,
            artifact_version=row.artifact_version,
            status=public_status(row),
            opened_at=row.opened_at,
            acknowledged_at=row.acknowledged_at,
        )
        for row in rows
    ]
