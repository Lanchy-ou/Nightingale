"""Database engine / session.

Unit tests keep the fast plain-SQLite path through ``NANTINGALE_DB_URL``.
The D5 single-machine deployment uses SQLCipher with a key supplied separately
through ``NANTINGALE_DB_KEY`` so credentials never have to appear in a URL,
command line, repository file or log.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL, create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

_DB_PATH = Path(__file__).resolve().parent.parent / "nantingale.db"
_ENCRYPTED_DB_PATH = Path(__file__).resolve().parent.parent / "nantingale.encrypted.db"

DATABASE_KEY = os.environ.get("NANTINGALE_DB_KEY", "")
_explicit_url = os.environ.get("NANTINGALE_DB_URL")
_requested_mode = os.environ.get("NANTINGALE_DATABASE_MODE", "sqlite").strip().lower()

if _explicit_url:
    DATABASE_URL: str | URL = _explicit_url
    DATABASE_MODE = (
        "sqlcipher" if _explicit_url.startswith("sqlite+pysqlcipher:") else "sqlite"
    )
elif _requested_mode == "sqlcipher":
    if not DATABASE_KEY:
        raise RuntimeError("NANTINGALE_DB_KEY is required for SQLCipher mode")
    encrypted_path = Path(
        os.environ.get("NANTINGALE_DB_PATH", str(_ENCRYPTED_DB_PATH))
    ).resolve()
    DATABASE_URL = URL.create(
        "sqlite+pysqlcipher",
        username="",
        password=DATABASE_KEY,
        database=str(encrypted_path),
    )
    DATABASE_MODE = "sqlcipher"
elif _requested_mode == "sqlite":
    DATABASE_URL = f"sqlite:///{_DB_PATH}"
    DATABASE_MODE = "sqlite"
else:
    raise RuntimeError("NANTINGALE_DATABASE_MODE must be sqlite or sqlcipher")

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
