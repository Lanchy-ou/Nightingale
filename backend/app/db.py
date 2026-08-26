"""Database engine / session. SQLite file lives at backend/nantingale.db (gitignored).

Tests override the location via the NANTINGALE_DB_URL environment variable,
which must be set BEFORE importing this module.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DB_PATH = Path(__file__).resolve().parent.parent / "nantingale.db"
DATABASE_URL = os.environ.get("NANTINGALE_DB_URL", f"sqlite:///{_DB_PATH}")

# check_same_thread=False so the TestClient (threaded) and SQLite play nice.
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
