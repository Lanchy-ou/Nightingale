"""Database engine / session.

Unit tests keep the fast plain-SQLite path through ``NANTINGALE_DB_URL``.
The D5 single-machine deployment uses SQLCipher with a key supplied separately
through ``NANTINGALE_DB_KEY`` so credentials never have to appear in a URL,
command line, repository file or log.
"""
from __future__ import annotations

import json
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


def migrate_d2_schema(target_engine: Engine = engine) -> None:
    """Upgrade a pre-D2 demo schema with first-class Tasks and Glance linkage.

    Existing Highlight rows keep a NULL ``task_id``. The unique index enforces
    the permanent one-Task-to-one-Highlight contract without inventing links
    for historical data.
    """
    from . import models as _core_models  # noqa: F401
    from .models import Task

    inspector = inspect(target_engine)
    if "highlights" not in inspector.get_table_names():
        raise RuntimeError("highlights table is missing; initialize the demo schema first")
    Task.__table__.create(bind=target_engine, checkfirst=True)
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        existing = {column["name"] for column in inspector.get_columns("highlights")}
        if "task_id" not in existing:
            connection.execute(
                text(
                    "ALTER TABLE highlights ADD COLUMN task_id VARCHAR(64) "
                    "REFERENCES tasks (task_id)"
                )
            )
        unique_columns = {
            tuple(item.get("column_names") or [])
            for item in [
                *inspector.get_unique_constraints("highlights"),
                *[index for index in inspector.get_indexes("highlights") if index.get("unique")],
            ]
        }
        if ("task_id",) not in unique_columns:
            connection.execute(
                text(
                    "CREATE UNIQUE INDEX IF NOT EXISTS uq_highlight_task "
                    "ON highlights (task_id)"
                )
            )


def migrate_e2_schema(target_engine: Engine = engine) -> None:
    """Upgrade an existing SQLite/SQLCipher demo schema to E2 in place.

    ``create_all`` cannot add columns to an existing SQLite table. This small,
    idempotent migration preserves the existing final score as the E2 base and
    creates the append-only feedback table without reading clinical content.
    """
    migrate_d2_schema(target_engine)
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


def migrate_e3_schema(target_engine: Engine = engine) -> None:
    """Upgrade an E2 SQLite/SQLCipher demo schema to E3 in place.

    The migration is explicit because ``create_all`` does not alter existing
    schemas.  It only adds the shadow-state table; authoritative Artifact rows
    and all existing history remain untouched.
    """
    migrate_e2_schema(target_engine)
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        tables = set(inspector.get_table_names())
        if "artifacts" not in tables:
            raise RuntimeError("artifacts table is missing; initialize the demo schema first")
        connection.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS artifact_storage_state (
                    artifact_id VARCHAR(64) NOT NULL PRIMARY KEY,
                    tier VARCHAR(16) NOT NULL,
                    reason_codes JSON NOT NULL,
                    policy_version VARCHAR(32) NOT NULL,
                    evaluated_as_of DATETIME NOT NULL,
                    evaluated_at DATETIME NOT NULL,
                    source_sha256 VARCHAR(64),
                    codec VARCHAR(32),
                    compressed_payload BLOB,
                    original_bytes INTEGER,
                    compressed_bytes INTEGER,
                    roundtrip_verified_at DATETIME,
                    FOREIGN KEY(artifact_id) REFERENCES artifacts (artifact_id)
                )
                """
            )
        )
        connection.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_artifact_storage_state_tier "
                "ON artifact_storage_state (tier)"
            )
        )


def migrate_highlight_source_binding_schema(target_engine: Engine = engine) -> None:
    """Add immutable Highlight source-version/hash binding and backfill safely."""
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        if "highlights" not in inspector.get_table_names():
            raise RuntimeError("highlights table is missing; initialize the demo schema first")
        highlight_columns = {
            column["name"] for column in inspector.get_columns("highlights")
        }
        additions = {
            "source_artifact_version": "INTEGER",
            "source_quote_sha256": "VARCHAR(64)",
        }
        for column, ddl in additions.items():
            if column not in highlight_columns:
                connection.execute(
                    text(f"ALTER TABLE highlights ADD COLUMN {column} {ddl}")
                )

        # Some migration tests intentionally use skeletal legacy tables. Real
        # pre-migration databases have these source/content columns; only those
        # databases are eligible for deterministic in-place backfill.
        highlight_columns = {
            column["name"] for column in inspect(connection).get_columns("highlights")
        }
        artifact_columns = {
            column["name"] for column in inspect(connection).get_columns("artifacts")
        }
        if not {
            "source_artifact_id",
            "source_span",
            "source_artifact_version",
            "source_quote_sha256",
        }.issubset(highlight_columns) or not {
            "artifact_id",
            "content",
            "version",
        }.issubset(artifact_columns):
            return

        from .provenance_binding import quote_sha256
        from .tasks import resolve_exact_span

        rows = connection.execute(
            text(
                "SELECT highlight_id, source_artifact_id, source_span "
                "FROM highlights WHERE source_artifact_id IS NOT NULL "
                "AND source_span IS NOT NULL AND "
                "(source_artifact_version IS NULL OR source_quote_sha256 IS NULL)"
            )
        ).mappings()
        for row in rows:
            source = connection.execute(
                text(
                    "SELECT content, version FROM artifacts "
                    "WHERE artifact_id = :artifact_id"
                ),
                {"artifact_id": row["source_artifact_id"]},
            ).mappings().first()
            if source is None:
                continue
            content = source["content"]
            span = row["source_span"]
            if isinstance(content, str):
                content = json.loads(content)
            if isinstance(span, str):
                span = json.loads(span)
            quote = resolve_exact_span(content, span)
            if not quote:
                continue
            connection.execute(
                text(
                    "UPDATE highlights SET source_artifact_version = :version, "
                    "source_quote_sha256 = :quote_hash WHERE highlight_id = :highlight_id"
                ),
                {
                    "version": source["version"],
                    "quote_hash": quote_sha256(quote),
                    "highlight_id": row["highlight_id"],
                },
            )


def migrate_phase_e_schema(target_engine: Engine = engine) -> None:
    """Idempotently upgrade an existing synthetic Demo through E1-E4."""
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        if "users" not in inspector.get_table_names():
            raise RuntimeError("users table is missing; initialize the demo schema first")
        user_columns = {column["name"] for column in inspector.get_columns("users")}
        if "professional_title" not in user_columns:
            connection.execute(
                text("ALTER TABLE users ADD COLUMN professional_title VARCHAR(128)")
            )

    migrate_e3_schema(target_engine)
    migrate_highlight_source_binding_schema(target_engine)

    # Import only after Base exists so all FK target tables and the E4 table
    # are registered without creating a second metadata registry.
    from . import models as _core_models  # noqa: F401
    from .voice.models import VoiceCaptureRecord

    VoiceCaptureRecord.__table__.create(bind=target_engine, checkfirst=True)
    migrate_patient_checkin_schema(target_engine)
    migrate_system_settings_schema(target_engine)


def migrate_patient_checkin_schema(target_engine: Engine = engine) -> None:
    """Create the bounded Patient Check-in lifecycle tables idempotently."""
    from . import models as _core_models  # noqa: F401
    from .models import PatientCheckInMessage, PatientCheckInSession

    PatientCheckInSession.__table__.create(bind=target_engine, checkfirst=True)
    PatientCheckInMessage.__table__.create(bind=target_engine, checkfirst=True)


def migrate_system_settings_schema(target_engine: Engine = engine) -> None:
    """Create the device-level settings table without inventing a secret."""
    from . import models as _core_models  # noqa: F401
    from .models import SystemSettings

    SystemSettings.__table__.create(bind=target_engine, checkfirst=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
