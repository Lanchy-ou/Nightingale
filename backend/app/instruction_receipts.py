"""B11 patient-instruction portal receipts (no external delivery claim)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import stable_id
from .models import Artifact, Event, PatientInstructionReceipt, User


def receipt_id(artifact_id: str, version: int) -> str:
    return f"pir_{stable_id('patient-instruction-receipt', artifact_id, str(version))}"


def get_receipt(
    db: Session, artifact_id: str, version: int
) -> PatientInstructionReceipt | None:
    return db.scalar(
        select(PatientInstructionReceipt).where(
            PatientInstructionReceipt.instruction_artifact_id == artifact_id,
            PatientInstructionReceipt.artifact_version == version,
        )
    )


def ensure_available_receipt(
    db: Session, artifact: Artifact, event: Event
) -> PatientInstructionReceipt:
    existing = get_receipt(db, artifact.artifact_id, artifact.version)
    if existing is not None:
        return existing
    now = datetime.now()
    receipt = PatientInstructionReceipt(
        receipt_id=receipt_id(artifact.artifact_id, artifact.version),
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        instruction_artifact_id=artifact.artifact_id,
        artifact_version=artifact.version,
        state="available",
        opened_by_user_id=None,
        opened_at=None,
        acknowledged_by_user_id=None,
        acknowledged_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(receipt)
    return receipt


def is_patient_instruction_available(
    db: Session, artifact: Artifact, event: Event
) -> bool:
    if artifact.artifact_type != "patient_instruction" or artifact.author_role != "clinician":
        return False
    author = db.get(User, artifact.author_id) if artifact.author_id else None
    instruction = (artifact.content or {}).get("instruction")
    return bool(
        author
        and author.role == "clinician"
        and author.clinic_id == event.clinic_id
        and isinstance(instruction, str)
        and instruction.strip()
    )


def public_status(receipt: PatientInstructionReceipt | None) -> str:
    if receipt is None:
        return "not_viewed"
    if receipt.state == "opened":
        return "viewed"
    if receipt.state == "acknowledged":
        return "acknowledged"
    return "not_viewed"
