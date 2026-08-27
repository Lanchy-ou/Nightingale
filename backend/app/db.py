"""Database engine / session.

Unit tests keep the fast plain-SQLite path through ``NANTINGALE_DB_URL``.
The D5 single-machine deployment uses SQLCipher with a key supplied separately
through ``NANTINGALE_DB_KEY`` so credentials never have to appear in a URL,
command line, repository file or log.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL, create_engine, inspect, text
from sqlalchemy.engine import Engine
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


def migrate_e2_schema(target_engine: Engine = engine) -> None:
    """Upgrade an existing SQLite/SQLCipher demo schema to E2 in place.

    ``create_all`` cannot add columns to an existing SQLite table. This small,
    idempotent migration preserves the existing final score as the E2 base and
    creates the append-only feedback table without reading clinical content.
    """
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        if "highlights" not in inspector.get_table_names():
            raise RuntimeError("highlights table is missing; initialize the demo schema first")

        existing = {column["name"] for column in inspector.get_columns("highlights")}
        additions = {
            "base_importance_score": "INTEGER NOT NULL DEFAULT 0",
            "adaptive_adjustment": "INTEGER NOT NULL DEFAULT 0",
            "decay_adjustment": "INTEGER NOT NULL DEFAULT 0",
            "learning_metadata": "JSON NOT NULL DEFAULT '{}'",
        }
        added_base = "base_importance_score" not in existing
        for column, ddl in additions.items():
            if column not in existing:
                connection.execute(text(f"ALTER TABLE highlights ADD COLUMN {column} {ddl}"))

        if added_base:
            connection.execute(
                text("UPDATE highlights SET base_importance_score = importance_score")
            )

        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS importance_feedback (
                    feedback_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    highlight_id VARCHAR(64) NOT NULL,
                    clinic_id VARCHAR(64) NOT NULL,
                    actor_id VARCHAR(64) NOT NULL,
                    actor_role VARCHAR(32) NOT NULL,
                    feedback_key VARCHAR(32) NOT NULL,
                    status VARCHAR(16) NOT NULL,
                    signal_value INTEGER NOT NULL,
                    created_at DATETIME NOT NULL,
                    FOREIGN KEY(highlight_id) REFERENCES highlights (highlight_id),
                    FOREIGN KEY(clinic_id) REFERENCES clinics (clinic_id),
                    FOREIGN KEY(actor_id) REFERENCES users (user_id)
                )
                """
            )
        )
        for name, column in (
            ("ix_importance_feedback_highlight_id", "highlight_id"),
            ("ix_importance_feedback_clinic_id", "clinic_id"),
            ("ix_importance_feedback_actor_id", "actor_id"),
            ("ix_importance_feedback_feedback_key", "feedback_key"),
        ):
            connection.execute(
                text(f"CREATE INDEX IF NOT EXISTS {name} ON importance_feedback ({column})")
            )


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
