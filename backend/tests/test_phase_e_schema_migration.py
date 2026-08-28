import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import migrate_phase_e_schema


def test_phase_e_migration_upgrades_legacy_columns_and_tables_idempotently(tmp_path):
    target = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with target.begin() as connection:
        connection.execute(text("CREATE TABLE users (user_id VARCHAR(64) PRIMARY KEY)"))
        connection.execute(
            text(
                "CREATE TABLE highlights (highlight_id VARCHAR(64) PRIMARY KEY, "
                "importance_score INTEGER NOT NULL)"
            )
        )
        connection.execute(text("CREATE TABLE artifacts (artifact_id VARCHAR(64) PRIMARY KEY)"))

    migrate_phase_e_schema(target)
    migrate_phase_e_schema(target)

    schema = inspect(target)
    assert "professional_title" in {
        column["name"] for column in schema.get_columns("users")
    }
    assert {
        "base_importance_score",
        "adaptive_adjustment",
        "decay_adjustment",
        "learning_metadata",
        "task_id",
    }.issubset({column["name"] for column in schema.get_columns("highlights")})
    assert {
        "tasks",
        "importance_feedback",
        "artifact_storage_state",
        "voice_captures",
        "patient_checkin_sessions",
        "patient_checkin_messages",
        "system_settings",
    }.issubset(
        set(schema.get_table_names())
    )

    with target.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO highlights (highlight_id, importance_score, task_id) "
                "VALUES ('hl_one', 1, 'task_shared')"
            )
        )
    with pytest.raises(IntegrityError):
        with target.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO highlights (highlight_id, importance_score, task_id) "
                    "VALUES ('hl_two', 1, 'task_shared')"
                )
            )
