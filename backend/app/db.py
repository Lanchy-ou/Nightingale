"""Database engine / session.

Unit tests keep the fast plain-SQLite path through ``NANTINGALE_DB_URL``.
The D5 single-machine deployment uses SQLCipher with a key supplied separately
through ``NANTINGALE_DB_KEY`` so credentials never have to appear in a URL,
command line, repository file or log.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from sqlalchemy import URL, create_engine, event as sqlalchemy_event, inspect, select, text
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


@sqlalchemy_event.listens_for(engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    """SQLite/SQLCipher must enforce the foreign keys declared by the models."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        cursor.close()


@sqlalchemy_event.listens_for(engine, "begin")
def _defer_sqlite_foreign_keys(connection) -> None:
    """Keep FKs mandatory at commit while allowing ordered staging in one transaction."""
    connection.exec_driver_sql("PRAGMA defer_foreign_keys=ON")


@sqlalchemy_event.listens_for(engine, "checkout")
def _prepare_sqlite_transaction(dbapi_connection, _record, _proxy) -> None:
    """Set FK deferral before SQLAlchemy starts the next transaction."""
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA defer_foreign_keys=ON")
    finally:
        cursor.close()

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
    migrate_fa2_schema(target_engine)
    migrate_fa1_schema(target_engine)
    install_clinic_isolation_schema(target_engine)


def migrate_fa2_schema(target_engine: Engine = engine) -> None:
    """Add deterministic patient-review workflow and role Glance projections."""
    from . import models as _core_models  # noqa: F401
    from .models import GlanceProjection, PatientReviewItem

    GlanceProjection.__table__.create(bind=target_engine, checkfirst=True)
    with target_engine.begin() as connection:
        inspector = inspect(connection)
        if "tasks" not in inspector.get_table_names() or "highlights" not in inspector.get_table_names():
            raise RuntimeError("tasks/highlights tables are missing; initialize the demo schema first")
        task_columns = {column["name"] for column in inspector.get_columns("tasks")}
        task_additions = {
            "task_kind": "VARCHAR(32) NOT NULL DEFAULT 'care_action'",
            "workflow_id": "VARCHAR(64)",
            "attention_class": "VARCHAR(32) NOT NULL DEFAULT 'routine'",
            "creation_method": "VARCHAR(32) NOT NULL DEFAULT 'human'",
            "verification_outcome": "VARCHAR(32) NOT NULL DEFAULT 'not_required'",
            "escalate_at": "DATETIME",
            "escalated_at": "DATETIME",
            "review_outcome": "VARCHAR(32)",
            "time_sensitivity": "VARCHAR(32)",
            "follow_up_task_id": "VARCHAR(64)",
            "routing_metadata": "JSON NOT NULL DEFAULT '{}'",
            "source_artifact_version": "INTEGER",
            "source_quote_sha256": "VARCHAR(64)",
        }
        for column, ddl in task_additions.items():
            if column not in task_columns:
                connection.execute(text(f"ALTER TABLE tasks ADD COLUMN {column} {ddl}"))
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_task_workflow_role "
                "ON tasks (workflow_id, task_kind, assigned_role)"
            )
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tasks_workflow_id ON tasks (workflow_id)")
        )
        connection.execute(
            text("CREATE INDEX IF NOT EXISTS ix_tasks_escalate_at ON tasks (escalate_at)")
        )

        highlight_columns = {
            column["name"] for column in inspect(connection).get_columns("highlights")
        }
        highlight_additions = {
            "score_rule_version": "VARCHAR(32) NOT NULL DEFAULT 'importance-v1'",
            "score_factors": "JSON NOT NULL DEFAULT '{}'",
        }
        for column, ddl in highlight_additions.items():
            if column not in highlight_columns:
                connection.execute(text(f"ALTER TABLE highlights ADD COLUMN {column} {ddl}"))
    PatientReviewItem.__table__.create(bind=target_engine, checkfirst=True)


def migrate_fa1_schema(target_engine: Engine = engine) -> None:
    """Add content-free Shadow Learning records and force base-only serving."""
    from . import models as _core_models  # noqa: F401
    from .models import (
        LearningEvaluation,
        LearningPolicyVersion,
        LearningSignal,
        RankingDecision,
        RankingRun,
    )

    for table in (
        RankingRun,
        RankingDecision,
        LearningSignal,
        LearningPolicyVersion,
        LearningEvaluation,
    ):
        table.__table__.create(bind=target_engine, checkfirst=True)
    from sqlalchemy.orm import Session
    from .models import Clinic, Patient
    from .shadow_learning import capture_ranking_runs, ensure_learning_policies

    existing_tables = set(inspect(target_engine).get_table_names())
    can_capture = {"clinics", "patients", "glance_projections", "tasks", "artifacts"} <= existing_tables
    if can_capture:
        with Session(target_engine) as db:
            for clinic_id in db.scalars(select(Clinic.clinic_id)).all():
                ensure_learning_policies(db, clinic_id)
            for patient_id in db.scalars(select(Patient.patient_id)).all():
                capture_ranking_runs(
                    db, patient_id, evaluated_at=datetime.now(), legacy_snapshot=True
                )
            db.commit()
    with target_engine.begin() as connection:
        tables = inspect(connection).get_table_names()
        if "highlights" not in tables:
            raise RuntimeError("highlights table is missing; initialize the demo schema first")
        connection.execute(
            text(
                "UPDATE highlights SET adaptive_adjustment = 0, "
                "importance_score = base_importance_score + decay_adjustment "
                "WHERE adaptive_adjustment != 0"
            )
        )
    from .glance_projection import rebuild_glance_projections

    if can_capture:
        with Session(target_engine) as db:
            for patient_id in db.scalars(select(Patient.patient_id)).all():
                rebuild_glance_projections(db, patient_id)
            db.commit()


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


_A3_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS ix_events_scope_timeline ON events (clinic_id, patient_id, started_at, event_id)",
    "CREATE INDEX IF NOT EXISTS ix_highlights_patient_event ON highlights (patient_id, event_id, highlight_id)",
    "CREATE INDEX IF NOT EXISTS ix_tasks_scope_list ON tasks (clinic_id, patient_id, created_at, task_id)",
    "CREATE INDEX IF NOT EXISTS ix_glance_scope_read ON glance_projections (clinic_id, patient_id, viewer_role, eligible, priority_band, final_score)",
    "CREATE INDEX IF NOT EXISTS ix_ranking_runs_scope_latest ON ranking_runs (clinic_id, patient_id, viewer_role, evaluated_at, run_id)",
    "CREATE INDEX IF NOT EXISTS ix_learning_signals_scope_decision ON learning_signals (clinic_id, decision_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_checkins_scope_direct ON patient_checkin_sessions (clinic_id, patient_id, session_id)",
    "CREATE INDEX IF NOT EXISTS ix_voice_scope_direct ON voice_captures (clinic_id, patient_id, capture_id)",
)


_A3_TRIGGER_DDL = (
    """
    CREATE TRIGGER IF NOT EXISTS a3_event_scope_insert
    BEFORE INSERT ON events
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:event_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_event_scope_update
    BEFORE UPDATE OF patient_id, clinic_id ON events
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:event_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_user_patient_scope_insert
    BEFORE INSERT ON users
    WHEN NEW.patient_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM patients p
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:user_patient_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_user_patient_scope_update
    BEFORE UPDATE OF patient_id, clinic_id ON users
    WHEN NEW.patient_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM patients p
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:user_patient_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_artifact_scope_insert
    BEFORE INSERT ON artifacts
    WHEN NEW.author_id IS NOT NULL
      AND EXISTS (SELECT 1 FROM events e WHERE e.event_id = NEW.event_id)
      AND NOT EXISTS (
        SELECT 1 FROM events e JOIN users u ON u.user_id = NEW.author_id
        WHERE e.event_id = NEW.event_id AND u.clinic_id = e.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:artifact_author_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_artifact_scope_update
    BEFORE UPDATE OF event_id, author_id ON artifacts
    WHEN NEW.author_id IS NOT NULL
      AND EXISTS (SELECT 1 FROM events e WHERE e.event_id = NEW.event_id)
      AND NOT EXISTS (
        SELECT 1 FROM events e JOIN users u ON u.user_id = NEW.author_id
        WHERE e.event_id = NEW.event_id AND u.clinic_id = e.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:artifact_author_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_highlight_scope_insert
    BEFORE INSERT ON highlights
    WHEN NOT EXISTS (
        SELECT 1 FROM events e
        WHERE e.event_id = NEW.event_id AND e.patient_id = NEW.patient_id
    ) OR (NEW.artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a WHERE a.artifact_id = NEW.artifact_id AND a.event_id = NEW.event_id
    )) OR (NEW.source_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a WHERE a.artifact_id = NEW.source_artifact_id AND a.event_id = NEW.event_id
    )) OR (NEW.conflict_with_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a
        JOIN events conflict_event ON conflict_event.event_id = a.event_id
        JOIN events highlight_event ON highlight_event.event_id = NEW.event_id
        WHERE a.artifact_id = NEW.conflict_with_artifact_id
          AND conflict_event.patient_id = highlight_event.patient_id
          AND conflict_event.clinic_id = highlight_event.clinic_id
    )) OR (NEW.task_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM tasks t WHERE t.task_id = NEW.task_id AND t.event_id = NEW.event_id AND t.patient_id = NEW.patient_id
    ))
    BEGIN SELECT RAISE(ABORT, 'ownership:highlight_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_highlight_scope_update
    BEFORE UPDATE OF patient_id, event_id, artifact_id, source_artifact_id, conflict_with_artifact_id, task_id ON highlights
    WHEN NOT EXISTS (
        SELECT 1 FROM events e
        WHERE e.event_id = NEW.event_id AND e.patient_id = NEW.patient_id
    ) OR (NEW.artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a WHERE a.artifact_id = NEW.artifact_id AND a.event_id = NEW.event_id
    )) OR (NEW.source_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a WHERE a.artifact_id = NEW.source_artifact_id AND a.event_id = NEW.event_id
    )) OR (NEW.conflict_with_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a
        JOIN events conflict_event ON conflict_event.event_id = a.event_id
        JOIN events highlight_event ON highlight_event.event_id = NEW.event_id
        WHERE a.artifact_id = NEW.conflict_with_artifact_id
          AND conflict_event.patient_id = highlight_event.patient_id
          AND conflict_event.clinic_id = highlight_event.clinic_id
    )) OR (NEW.task_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM tasks t WHERE t.task_id = NEW.task_id AND t.event_id = NEW.event_id AND t.patient_id = NEW.patient_id
    ))
    BEGIN SELECT RAISE(ABORT, 'ownership:highlight_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_task_scope_insert
    BEFORE INSERT ON tasks
    WHEN NOT EXISTS (
        SELECT 1 FROM events e
        WHERE e.event_id = NEW.event_id AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    ) OR (NEW.source_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a WHERE a.artifact_id = NEW.source_artifact_id AND a.event_id = NEW.event_id
    )) OR NOT EXISTS (
        SELECT 1 FROM users u WHERE u.user_id = NEW.created_by AND u.clinic_id = NEW.clinic_id
    ) OR (NEW.assigned_user_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM users u WHERE u.user_id = NEW.assigned_user_id AND u.clinic_id = NEW.clinic_id
          AND u.role = NEW.assigned_role
          AND (NEW.assigned_role != 'patient' OR u.patient_id = NEW.patient_id)
    )) OR (NEW.follow_up_task_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM tasks t WHERE t.task_id = NEW.follow_up_task_id AND t.patient_id = NEW.patient_id AND t.clinic_id = NEW.clinic_id
    ))
    BEGIN SELECT RAISE(ABORT, 'ownership:task_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_task_scope_update
    BEFORE UPDATE OF patient_id, clinic_id, event_id, source_artifact_id, assigned_role, assigned_user_id, created_by, follow_up_task_id ON tasks
    WHEN NOT EXISTS (
        SELECT 1 FROM events e
        WHERE e.event_id = NEW.event_id AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    ) OR (NEW.source_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a WHERE a.artifact_id = NEW.source_artifact_id AND a.event_id = NEW.event_id
    )) OR NOT EXISTS (
        SELECT 1 FROM users u WHERE u.user_id = NEW.created_by AND u.clinic_id = NEW.clinic_id
    ) OR (NEW.assigned_user_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM users u WHERE u.user_id = NEW.assigned_user_id AND u.clinic_id = NEW.clinic_id
          AND u.role = NEW.assigned_role
          AND (NEW.assigned_role != 'patient' OR u.patient_id = NEW.patient_id)
    )) OR (NEW.follow_up_task_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM tasks t WHERE t.task_id = NEW.follow_up_task_id AND t.patient_id = NEW.patient_id AND t.clinic_id = NEW.clinic_id
    ))
    BEGIN SELECT RAISE(ABORT, 'ownership:task_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_ranking_run_scope_insert
    BEFORE INSERT ON ranking_runs
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:ranking_run_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_ranking_run_scope_update
    BEFORE UPDATE OF patient_id, clinic_id ON ranking_runs
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:ranking_run_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_ranking_decision_scope_insert
    BEFORE INSERT ON ranking_decisions
    WHEN NOT EXISTS (
        SELECT 1 FROM ranking_runs r
        JOIN highlights h ON h.highlight_id = NEW.highlight_id
        JOIN events e ON e.event_id = h.event_id
        WHERE r.run_id = NEW.run_id AND h.patient_id = r.patient_id
          AND e.patient_id = r.patient_id AND e.clinic_id = r.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:ranking_decision_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_ranking_decision_scope_update
    BEFORE UPDATE OF run_id, highlight_id ON ranking_decisions
    WHEN NOT EXISTS (
        SELECT 1 FROM ranking_runs r
        JOIN highlights h ON h.highlight_id = NEW.highlight_id
        JOIN events e ON e.event_id = h.event_id
        WHERE r.run_id = NEW.run_id AND h.patient_id = r.patient_id
          AND e.patient_id = r.patient_id AND e.clinic_id = r.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:ranking_decision_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_learning_signal_scope_insert
    BEFORE INSERT ON learning_signals
    WHEN NOT EXISTS (
        SELECT 1 FROM ranking_decisions d
        JOIN ranking_runs r ON r.run_id = d.run_id
        JOIN users u ON u.user_id = NEW.actor_id
        WHERE d.decision_id = NEW.decision_id AND r.clinic_id = NEW.clinic_id
          AND u.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:learning_signal_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_learning_signal_scope_update
    BEFORE UPDATE OF decision_id, clinic_id, actor_id ON learning_signals
    WHEN NOT EXISTS (
        SELECT 1 FROM ranking_decisions d
        JOIN ranking_runs r ON r.run_id = d.run_id
        JOIN users u ON u.user_id = NEW.actor_id
        WHERE d.decision_id = NEW.decision_id AND r.clinic_id = NEW.clinic_id
          AND u.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:learning_signal_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_glance_projection_scope_insert
    BEFORE INSERT ON glance_projections
    WHEN NOT EXISTS (
        SELECT 1 FROM highlights h JOIN events e ON e.event_id = h.event_id
        WHERE h.highlight_id = NEW.highlight_id AND h.patient_id = NEW.patient_id
          AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:glance_projection_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_glance_projection_scope_update
    BEFORE UPDATE OF highlight_id, patient_id, clinic_id ON glance_projections
    WHEN NOT EXISTS (
        SELECT 1 FROM highlights h JOIN events e ON e.event_id = h.event_id
        WHERE h.highlight_id = NEW.highlight_id AND h.patient_id = NEW.patient_id
          AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:glance_projection_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_checkin_scope_insert
    BEFORE INSERT ON patient_checkin_sessions
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p JOIN events e ON e.patient_id = p.patient_id
        JOIN artifacts a ON a.event_id = e.event_id
        JOIN users u ON u.user_id = NEW.patient_user_id
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
          AND e.event_id = NEW.event_id AND e.clinic_id = NEW.clinic_id
          AND a.artifact_id = NEW.raw_artifact_id
          AND u.clinic_id = NEW.clinic_id AND u.patient_id = NEW.patient_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:checkin_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_checkin_scope_update
    BEFORE UPDATE OF event_id, raw_artifact_id, patient_id, clinic_id, patient_user_id ON patient_checkin_sessions
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p JOIN events e ON e.patient_id = p.patient_id
        JOIN artifacts a ON a.event_id = e.event_id
        JOIN users u ON u.user_id = NEW.patient_user_id
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
          AND e.event_id = NEW.event_id AND e.clinic_id = NEW.clinic_id
          AND a.artifact_id = NEW.raw_artifact_id
          AND u.clinic_id = NEW.clinic_id AND u.patient_id = NEW.patient_id
    )
    BEGIN SELECT RAISE(ABORT, 'ownership:checkin_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_voice_scope_insert
    BEFORE INSERT ON voice_captures
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p JOIN users u ON u.user_id = NEW.created_by
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
          AND u.clinic_id = NEW.clinic_id
    ) OR (NEW.event_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM events e WHERE e.event_id = NEW.event_id
          AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    )) OR (NEW.transcript_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a JOIN events e ON e.event_id = a.event_id
        WHERE a.artifact_id = NEW.transcript_artifact_id
          AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    ))
    BEGIN SELECT RAISE(ABORT, 'ownership:voice_scope'); END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS a3_voice_scope_update
    BEFORE UPDATE OF clinic_id, patient_id, created_by, event_id, transcript_artifact_id ON voice_captures
    WHEN NOT EXISTS (
        SELECT 1 FROM patients p JOIN users u ON u.user_id = NEW.created_by
        WHERE p.patient_id = NEW.patient_id AND p.clinic_id = NEW.clinic_id
          AND u.clinic_id = NEW.clinic_id
    ) OR (NEW.event_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM events e WHERE e.event_id = NEW.event_id
          AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    )) OR (NEW.transcript_artifact_id IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM artifacts a JOIN events e ON e.event_id = a.event_id
        WHERE a.artifact_id = NEW.transcript_artifact_id
          AND e.patient_id = NEW.patient_id AND e.clinic_id = NEW.clinic_id
    ))
    BEGIN SELECT RAISE(ABORT, 'ownership:voice_scope'); END
    """,
)


_A3_PREFLIGHT = {
    "event_scope": "SELECT COUNT(*) FROM events e LEFT JOIN patients p ON p.patient_id=e.patient_id AND p.clinic_id=e.clinic_id WHERE p.patient_id IS NULL",
    "user_patient_scope": "SELECT COUNT(*) FROM users u LEFT JOIN patients p ON p.patient_id=u.patient_id AND p.clinic_id=u.clinic_id WHERE u.patient_id IS NOT NULL AND p.patient_id IS NULL",
    "artifact_author_scope": "SELECT COUNT(*) FROM artifacts a JOIN events e ON e.event_id=a.event_id LEFT JOIN users u ON u.user_id=a.author_id AND u.clinic_id=e.clinic_id WHERE a.author_id IS NOT NULL AND u.user_id IS NULL",
    "highlight_scope": "SELECT COUNT(*) FROM highlights h LEFT JOIN events e ON e.event_id=h.event_id AND e.patient_id=h.patient_id WHERE e.event_id IS NULL",
    "highlight_reference_scope": "SELECT COUNT(*) FROM highlights h JOIN events he ON he.event_id=h.event_id LEFT JOIN artifacts d ON d.artifact_id=h.artifact_id AND d.event_id=h.event_id LEFT JOIN artifacts s ON s.artifact_id=h.source_artifact_id AND s.event_id=h.event_id LEFT JOIN artifacts c ON c.artifact_id=h.conflict_with_artifact_id LEFT JOIN events ce ON ce.event_id=c.event_id AND ce.patient_id=he.patient_id AND ce.clinic_id=he.clinic_id LEFT JOIN tasks t ON t.task_id=h.task_id AND t.event_id=h.event_id AND t.patient_id=h.patient_id WHERE (h.artifact_id IS NOT NULL AND d.artifact_id IS NULL) OR (h.source_artifact_id IS NOT NULL AND s.artifact_id IS NULL) OR (h.conflict_with_artifact_id IS NOT NULL AND ce.event_id IS NULL) OR (h.task_id IS NOT NULL AND t.task_id IS NULL)",
    "task_scope": "SELECT COUNT(*) FROM tasks t LEFT JOIN events e ON e.event_id=t.event_id AND e.patient_id=t.patient_id AND e.clinic_id=t.clinic_id WHERE e.event_id IS NULL",
    "task_reference_scope": "SELECT COUNT(*) FROM tasks t LEFT JOIN artifacts a ON a.artifact_id=t.source_artifact_id AND a.event_id=t.event_id LEFT JOIN users c ON c.user_id=t.created_by AND c.clinic_id=t.clinic_id LEFT JOIN users u ON u.user_id=t.assigned_user_id AND u.clinic_id=t.clinic_id AND u.role=t.assigned_role AND (t.assigned_role!='patient' OR u.patient_id=t.patient_id) LEFT JOIN tasks f ON f.task_id=t.follow_up_task_id AND f.patient_id=t.patient_id AND f.clinic_id=t.clinic_id WHERE (t.source_artifact_id IS NOT NULL AND a.artifact_id IS NULL) OR c.user_id IS NULL OR (t.assigned_user_id IS NOT NULL AND u.user_id IS NULL) OR (t.follow_up_task_id IS NOT NULL AND f.task_id IS NULL)",
    "ranking_run_scope": "SELECT COUNT(*) FROM ranking_runs r LEFT JOIN patients p ON p.patient_id=r.patient_id AND p.clinic_id=r.clinic_id WHERE p.patient_id IS NULL",
    "ranking_decision_scope": "SELECT COUNT(*) FROM ranking_decisions d LEFT JOIN ranking_runs r ON r.run_id=d.run_id LEFT JOIN highlights h ON h.highlight_id=d.highlight_id LEFT JOIN events e ON e.event_id=h.event_id WHERE r.run_id IS NULL OR h.highlight_id IS NULL OR e.event_id IS NULL OR h.patient_id!=r.patient_id OR e.patient_id!=r.patient_id OR e.clinic_id!=r.clinic_id",
    "learning_signal_scope": "SELECT COUNT(*) FROM learning_signals s LEFT JOIN ranking_decisions d ON d.decision_id=s.decision_id LEFT JOIN ranking_runs r ON r.run_id=d.run_id LEFT JOIN users u ON u.user_id=s.actor_id WHERE d.decision_id IS NULL OR r.run_id IS NULL OR u.user_id IS NULL OR s.clinic_id!=r.clinic_id OR u.clinic_id!=s.clinic_id",
    "glance_projection_scope": "SELECT COUNT(*) FROM glance_projections g LEFT JOIN highlights h ON h.highlight_id=g.highlight_id AND h.patient_id=g.patient_id LEFT JOIN events e ON e.event_id=h.event_id AND e.patient_id=g.patient_id AND e.clinic_id=g.clinic_id WHERE h.highlight_id IS NULL OR e.event_id IS NULL",
    "checkin_scope": "SELECT COUNT(*) FROM patient_checkin_sessions s LEFT JOIN patients p ON p.patient_id=s.patient_id AND p.clinic_id=s.clinic_id LEFT JOIN events e ON e.event_id=s.event_id AND e.patient_id=s.patient_id AND e.clinic_id=s.clinic_id LEFT JOIN artifacts a ON a.artifact_id=s.raw_artifact_id AND a.event_id=s.event_id LEFT JOIN users u ON u.user_id=s.patient_user_id AND u.patient_id=s.patient_id AND u.clinic_id=s.clinic_id WHERE p.patient_id IS NULL OR e.event_id IS NULL OR a.artifact_id IS NULL OR u.user_id IS NULL",
    "voice_scope": "SELECT COUNT(*) FROM voice_captures v LEFT JOIN patients p ON p.patient_id=v.patient_id AND p.clinic_id=v.clinic_id LEFT JOIN users u ON u.user_id=v.created_by AND u.clinic_id=v.clinic_id LEFT JOIN events e ON e.event_id=v.event_id AND e.patient_id=v.patient_id AND e.clinic_id=v.clinic_id LEFT JOIN artifacts a ON a.artifact_id=v.transcript_artifact_id LEFT JOIN events ae ON ae.event_id=a.event_id AND ae.patient_id=v.patient_id AND ae.clinic_id=v.clinic_id WHERE p.patient_id IS NULL OR u.user_id IS NULL OR (v.event_id IS NOT NULL AND e.event_id IS NULL) OR (v.transcript_artifact_id IS NOT NULL AND (a.artifact_id IS NULL OR ae.event_id IS NULL))",
}


def install_clinic_isolation_schema(target_engine: Engine = engine) -> None:
    """Install A3 ownership-only indexes/triggers after a metadata-only preflight.

    This is deliberately SQLite/SQLCipher defense in depth, not Row-Level
    Security. Trigger predicates read identifiers and ownership keys only;
    clinical content and ranking arithmetic are never inspected.
    """
    if target_engine.dialect.name != "sqlite":
        raise RuntimeError("A3 clinic-isolation schema currently supports SQLite/SQLCipher only")
    with target_engine.begin() as connection:
        tables = set(inspect(connection).get_table_names())
        required = {
            "patients", "users", "events", "artifacts", "highlights", "tasks",
            "glance_projections", "ranking_runs", "ranking_decisions",
            "learning_signals", "patient_checkin_sessions", "voice_captures",
        }
        if not required <= tables:
            return
        violations = {
            code: int(connection.execute(text(sql)).scalar() or 0)
            for code, sql in _A3_PREFLIGHT.items()
        }
        violations = {code: count for code, count in violations.items() if count}
        if violations:
            summary = ", ".join(f"{code}={count}" for code, count in sorted(violations.items()))
            raise RuntimeError(f"A3 ownership preflight failed: {summary}")
        for ddl in _A3_INDEX_DDL:
            connection.exec_driver_sql(ddl)
        for ddl in _A3_TRIGGER_DDL:
            connection.exec_driver_sql(ddl)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
