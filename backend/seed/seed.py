"""Create schema + seed the canonical M1 fixture. Idempotent (clears then inserts).

M3 additions:
- backfills an ArtifactVersion(v1) snapshot for every editable note so that
  v1 can be diffed / reverted from the start;
- clears tables in FK-safe order (AuditLog/Comment/ArtifactVersion reference
  users/artifacts; User.patient_id references patients).
"""
from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine, install_clinic_isolation_schema
from app.ids import new_id
from app.models import (
    Artifact,
    ArtifactStorageState,
    ArtifactVersion,
    AuditLog,
    AuthSession,
    Clinic,
    ClinicOnboardingToken,
    ClinicSettings,
    Comment,
    CareWorkflow,
    Event,
    Highlight,
    GlanceProjection,
    ImportanceFeedback,
    Invite,
    LearningEvaluation,
    LearningPolicyVersion,
    LearningSignal,
    Patient,
    PatientExternalIdentity,
    PatientImportBatch,
    PatientImportRow,
    PatientCheckInMessage,
    PatientCheckInSession,
    PatientInstructionReceipt,
    PatientInstructionPublication,
    PatientReviewItem,
    RankingDecision,
    RankingRun,
    Task,
    WorkflowLink,
    SystemSettings,
    User,
    UserCredential,
)
from app.voice.models import VoiceCaptureRecord

from . import fixture
from .highlights import generate_highlights

EDITABLE_NOTE_TYPES = {"staff_note", "clinician_note"}


def create_schema(target_engine=engine) -> None:
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)
    install_clinic_isolation_schema(target_engine)


def _backfill_versions(db: Session) -> None:
    editable = db.scalars(
        select(Artifact).where(Artifact.artifact_type.in_(EDITABLE_NOTE_TYPES))
    ).all()
    for a in editable:
        db.add(
            ArtifactVersion(
                version_id=new_id("ver"),
                artifact_id=a.artifact_id,
                version=a.version,
                content=a.content,
                actor_id=a.author_id or "system",
                actor_role=a.author_role,
                created_at=a.created_at,
            )
        )
    db.commit()


def _backfill_instruction_receipts(db: Session) -> None:
    from app.instruction_receipts import ensure_available_receipt, is_patient_instruction_available
    from app.instruction_publications import is_instruction_published

    rows = db.execute(
        select(Artifact, Event)
        .join(Event, Event.event_id == Artifact.event_id)
        .where(Artifact.artifact_type == "patient_instruction")
    ).all()
    for artifact, event in rows:
        if (
            is_patient_instruction_available(db, artifact, event)
            and is_instruction_published(db, artifact, event)
        ):
            ensure_available_receipt(db, artifact, event)
    db.commit()


def _backfill_instruction_publications(db: Session) -> None:
    from app.instruction_publications import ensure_legacy_published
    from app.instruction_receipts import is_patient_instruction_available

    rows = db.execute(
        select(Artifact, Event)
        .join(Event, Event.event_id == Artifact.event_id)
        .where(Artifact.artifact_type == "patient_instruction")
    ).all()
    for artifact, event in rows:
        if is_patient_instruction_available(db, artifact, event):
            ensure_legacy_published(db, artifact, event)
    db.commit()


def seed(db: Session) -> None:
    # Clear in FK-safe order (children first). D1 identity tables reference
    # users/patients/clinics and are cleared before them.
    db.execute(delete(VoiceCaptureRecord))
    db.execute(delete(ClinicSettings))
    db.execute(delete(ClinicOnboardingToken))
    db.execute(delete(PatientImportRow))
    db.execute(delete(PatientImportBatch))
    db.execute(delete(PatientExternalIdentity))
    db.execute(delete(SystemSettings))
    db.execute(delete(PatientCheckInMessage))
    db.execute(delete(PatientCheckInSession))
    db.execute(delete(PatientInstructionReceipt))
    db.execute(delete(PatientInstructionPublication))
    db.execute(delete(AuditLog))
    db.execute(delete(LearningEvaluation))
    db.execute(delete(LearningSignal))
    db.execute(delete(RankingDecision))
    db.execute(delete(RankingRun))
    db.execute(delete(LearningPolicyVersion))
    db.execute(delete(ImportanceFeedback))
    db.execute(delete(AuthSession))
    db.execute(delete(UserCredential))
    db.execute(delete(Invite))
    db.execute(delete(Comment))
    db.execute(delete(ArtifactVersion))
    db.execute(delete(ArtifactStorageState))
    db.execute(delete(GlanceProjection))
    db.execute(delete(PatientReviewItem))
    db.execute(delete(Highlight))
    db.execute(delete(WorkflowLink))
    db.execute(delete(Task))
    db.execute(delete(CareWorkflow))
    db.execute(delete(Artifact))
    db.execute(delete(Event))
    db.execute(delete(User))
    db.execute(delete(Patient))
    db.execute(delete(Clinic))

    # A3 privileged seed allowlist: insert ownership roots before descendants.
    # Runtime application writes never receive this global seed capability.
    db.add_all(fixture.build_clinics())
    db.add_all(fixture.build_patients())
    db.commit()
    db.add_all(fixture.build_users())
    db.add_all(fixture.build_credentials())
    db.commit()
    db.add_all(fixture.build_events())
    db.commit()
    db.add_all(fixture.build_artifacts())
    db.commit()
    _backfill_instruction_publications(db)
    _backfill_instruction_receipts(db)
    db.add_all(fixture.build_tasks())
    db.add_all(fixture.build_task_audits())
    db.add_all(fixture.build_comments())
    db.commit()

    from app.workflow_state import backfill_workflows

    backfill_workflows(db)
    db.commit()

    generate_highlights(db)
    from app.tasks import link_task_highlight

    for task in db.scalars(select(Task).order_by(Task.task_id)).all():
        if db.scalar(select(Highlight.highlight_id).where(Highlight.task_id == task.task_id)) is None:
            link_task_highlight(db, task)
    db.flush()
    from app.glance_projection import rebuild_glance_projections

    for patient_id in db.scalars(select(Patient.patient_id)).all():
        rebuild_glance_projections(db, patient_id)
    db.commit()
    _backfill_versions(db)


def main() -> None:
    create_schema()
    with SessionLocal() as db:
        seed(db)
    # Never print the full database URL/path (F_A4): it would reveal the
    # on-disk storage location of the encrypted database.
    print("Seeded M1 fixture into the configured database")


if __name__ == "__main__":
    main()
