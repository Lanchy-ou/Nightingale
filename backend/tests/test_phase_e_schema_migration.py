import hashlib
import json

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from app.db import migrate_highlight_source_binding_schema, migrate_phase_e_schema


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
        "source_artifact_version",
        "source_quote_sha256",
        "score_rule_version",
        "score_factors",
    }.issubset({column["name"] for column in schema.get_columns("highlights")})
    assert {
        "tasks",
        "importance_feedback",
        "artifact_storage_state",
        "voice_captures",
        "patient_checkin_sessions",
        "patient_checkin_messages",
        "system_settings",
        "glance_projections",
    }.issubset(
        set(schema.get_table_names())
    )
    assert {
        "task_kind",
        "workflow_id",
        "attention_class",
        "creation_method",
        "verification_outcome",
        "escalate_at",
        "escalated_at",
        "review_outcome",
        "time_sensitivity",
        "routing_metadata",
        "source_artifact_version",
        "source_quote_sha256",
    }.issubset({column["name"] for column in schema.get_columns("tasks")})

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


def test_source_binding_migration_backfills_version_and_quote_hash(tmp_path):
    target = create_engine(f"sqlite:///{tmp_path / 'provenance.db'}")
    content = {"assessment": "Penicillin allergy recorded."}
    span = {"kind": "section", "index": "assessment", "offset": [0, 18]}
    with target.begin() as connection:
        connection.execute(text(
            "CREATE TABLE artifacts (artifact_id VARCHAR(64) PRIMARY KEY, "
            "content JSON NOT NULL, version INTEGER NOT NULL)"
        ))
        connection.execute(text(
            "CREATE TABLE highlights (highlight_id VARCHAR(64) PRIMARY KEY, "
            "source_artifact_id VARCHAR(64), source_span JSON)"
        ))
        connection.execute(
            text("INSERT INTO artifacts VALUES (:id, :content, 3)"),
            {"id": "art_source", "content": json.dumps(content)},
        )
        connection.execute(
            text("INSERT INTO highlights VALUES (:id, :source, :span)"),
            {
                "id": "hl_bound",
                "source": "art_source",
                "span": json.dumps(span),
            },
        )

    migrate_highlight_source_binding_schema(target)
    migrate_highlight_source_binding_schema(target)
    with target.connect() as connection:
        row = connection.execute(text(
            "SELECT source_artifact_version, source_quote_sha256 "
            "FROM highlights WHERE highlight_id = 'hl_bound'"
        )).mappings().one()
    assert row["source_artifact_version"] == 3
    assert row["source_quote_sha256"] == hashlib.sha256(
        "Penicillin allergy".encode("utf-8")
    ).hexdigest()
