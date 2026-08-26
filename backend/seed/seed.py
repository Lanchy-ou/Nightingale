"""Create schema + seed the canonical M1 fixture. Idempotent (clears then inserts)."""
from __future__ import annotations

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db import Base, SessionLocal, engine
from app.models import Artifact, Clinic, Event, Highlight, Patient, User

from . import fixture
from .highlights import generate_highlights


def create_schema(target_engine=engine) -> None:
    Base.metadata.drop_all(target_engine)
    Base.metadata.create_all(target_engine)


def seed(db: Session) -> None:
    # Clear in FK-safe order, then insert the single source of truth.
    db.execute(delete(Highlight))
    db.execute(delete(Artifact))
    db.execute(delete(Event))
    db.execute(delete(Patient))
    db.execute(delete(User))
    db.execute(delete(Clinic))

    db.add(fixture.build_clinic())
    db.add_all(fixture.build_users())
    db.add(fixture.build_patient())
    db.add_all(fixture.build_events())
    db.add_all(fixture.build_artifacts())
    db.commit()

    generate_highlights(db)


def main() -> None:
    create_schema()
    with SessionLocal() as db:
        seed(db)
    print(f"Seeded M1 fixture into {engine.url}")


if __name__ == "__main__":
    main()
