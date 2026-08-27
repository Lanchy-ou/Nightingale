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

from app.db import Base, SessionLocal, engine
from app.ids import new_id
from app.models import (
    Artifact,
    ArtifactStorageState,
    ArtifactVersion,
    AuditLog,
    AuthSession,
    Clinic,
    Comment,
    Event,
    Highlight,
    ImportanceFeedback,
    Invite,
    Patient,
    Task,
    User,
    UserCredential,
)

from . import fixture
from .highlights import generate_highlights

EDITABLE_NOTE_TYPES = {"staff_note", "clinician_note"}


def create_schema(target_engine=engine) -> None:
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)


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


def seed(db: Session) -> None:
    # Clear in FK-safe order (children first). D1 identity tables reference
    # users/patients/clinics and are cleared before them.
    db.execute(delete(AuditLog))
    db.execute(delete(ImportanceFeedback))
    db.execute(delete(AuthSession))
    db.execute(delete(UserCredential))
    db.execute(delete(Invite))
    db.execute(delete(Comment))
    db.execute(delete(ArtifactVersion))
    db.execute(delete(ArtifactStorageState))
    db.execute(delete(Highlight))
    db.execute(delete(Task))
    db.execute(delete(Artifact))
    db.execute(delete(Event))
    db.execute(delete(User))
    db.execute(delete(Patient))
    db.execute(delete(Clinic))

    db.add_all(fixture.build_clinics())
    db.add_all(fixture.build_users())
    db.add_all(fixture.build_patients())
    db.add_all(fixture.build_credentials())
    db.add_all(fixture.build_events())
    db.add_all(fixture.build_artifacts())
    db.add_all(fixture.build_tasks())
    db.add_all(fixture.build_task_audits())
    db.commit()

    generate_highlights(db)
    _backfill_versions(db)


def main() -> None:
    create_schema()
    with SessionLocal() as db:
        seed(db)
    print(f"Seeded M1 fixture into {engine.url}")


if __name__ == "__main__":
    main()
