"""B12 patient-instruction publication authority and lineage helpers."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from .ids import stable_id
from .models import Artifact, Event, PatientInstructionPublication

PUBLICATION_STATES = {"draft", "published", "superseded", "withdrawn"}
WITHDRAWAL_REASON_CODES = {
    "entered_in_error",
    "no_longer_applicable",
    "replaced_elsewhere",
}


def normalize_instruction_content(content: dict) -> dict:
    if not isinstance(content, dict) or set(content) - {"instruction", "follow_up"}:
        raise ValueError("Invalid patient instruction")
    instruction = content.get("instruction")
    follow_up = content.get("follow_up")
    if (
        not isinstance(instruction, str)
        or not instruction.strip()
        or len(instruction) > 2000
        or instruction.strip().upper().startswith("EDIT REQUIRED")
        or (
            follow_up is not None
            and (not isinstance(follow_up, str) or len(follow_up) > 2000)
        )
    ):
        raise ValueError("Invalid patient instruction")
    return {
        "instruction": instruction.strip(),
        "follow_up": follow_up.strip() if isinstance(follow_up, str) and follow_up.strip() else None,
    }


def publication_id(artifact_id: str, version: int) -> str:
    return f"pip_{stable_id('patient-instruction-publication', artifact_id, str(version))}"


def lineage_id(artifact_id: str) -> str:
    return f"pil_{stable_id('patient-instruction-lineage', artifact_id)}"


def get_publication(
    db: Session, artifact_id: str, version: int
) -> PatientInstructionPublication | None:
    return db.scalar(
        select(PatientInstructionPublication).where(
            PatientInstructionPublication.instruction_artifact_id == artifact_id,
            PatientInstructionPublication.artifact_version == version,
        )
    )


def create_draft_publication(
    db: Session, artifact: Artifact, event: Event, actor_id: str
) -> PatientInstructionPublication:
    now = artifact.created_at or datetime.now()
    row = PatientInstructionPublication(
        publication_id=publication_id(artifact.artifact_id, artifact.version),
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        lineage_id=lineage_id(artifact.artifact_id),
        lineage_revision=1,
        instruction_artifact_id=artifact.artifact_id,
        artifact_version=artifact.version,
        state="draft",
        created_by_user_id=actor_id,
        created_at=now,
        published_by_user_id=None,
        published_at=None,
        superseded_by_artifact_id=None,
        superseded_at=None,
        withdrawn_by_user_id=None,
        withdrawn_at=None,
        withdrawal_reason_code=None,
        correction_key=None,
        updated_at=now,
    )
    db.add(row)
    return row


def ensure_legacy_published(
    db: Session, artifact: Artifact, event: Event
) -> PatientInstructionPublication:
    existing = get_publication(db, artifact.artifact_id, artifact.version)
    if existing is not None:
        return existing
    now = artifact.created_at or datetime.now()
    row = PatientInstructionPublication(
        publication_id=publication_id(artifact.artifact_id, artifact.version),
        clinic_id=event.clinic_id,
        patient_id=event.patient_id,
        lineage_id=lineage_id(artifact.artifact_id),
        lineage_revision=1,
        instruction_artifact_id=artifact.artifact_id,
        artifact_version=artifact.version,
        state="published",
        created_by_user_id=artifact.author_id or "system",
        created_at=now,
        published_by_user_id=artifact.author_id,
        published_at=now,
        superseded_by_artifact_id=None,
        superseded_at=None,
        withdrawn_by_user_id=None,
        withdrawn_at=None,
        withdrawal_reason_code=None,
        correction_key=None,
        updated_at=now,
    )
    db.add(row)
    return row


def is_instruction_published(
    db: Session, artifact: Artifact, event: Event | None = None
) -> bool:
    row = get_publication(db, artifact.artifact_id, artifact.version)
    return bool(
        row
        and row.state == "published"
        and (
            event is None
            or (row.clinic_id == event.clinic_id and row.patient_id == event.patient_id)
        )
    )
