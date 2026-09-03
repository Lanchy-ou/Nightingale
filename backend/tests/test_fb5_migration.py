from __future__ import annotations

from datetime import datetime

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import Base, migrate_fb5_schema
from app.models import (
    ClinicSettings,
    PatientExternalIdentity,
    PatientImportBatch,
)
from app.onboarding import issue_onboarding_token
from seed import fixture


def test_fb5_migration_is_idempotent_and_backfills_existing_clinics(tmp_path):
    target = create_engine(f"sqlite:///{tmp_path / 'legacy-fb5.db'}", future=True)
    with target.begin() as connection:
        connection.execute(text("CREATE TABLE clinics (clinic_id VARCHAR(64) PRIMARY KEY, name VARCHAR(255) NOT NULL)"))
        connection.execute(text("CREATE TABLE patients (patient_id VARCHAR(64) PRIMARY KEY, clinic_id VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL)"))
        connection.execute(text("CREATE TABLE users (user_id VARCHAR(64) PRIMARY KEY, clinic_id VARCHAR(64) NOT NULL, name VARCHAR(255) NOT NULL, role VARCHAR(32) NOT NULL, patient_id VARCHAR(64), professional_title VARCHAR(128))"))
        connection.execute(text("INSERT INTO clinics VALUES ('clinic_legacy', 'Legacy Clinic')"))

    migrate_fb5_schema(target)
    migrate_fb5_schema(target)

    tables = set(inspect(target).get_table_names())
    assert {
        "clinic_onboarding_tokens",
        "clinic_settings",
        "patient_external_identities",
        "patient_import_batches",
        "patient_import_rows",
    } <= tables
    with target.connect() as connection:
        row = connection.execute(
            text("SELECT clinic_id, ai_mode_override, voice_enabled_override, version FROM clinic_settings")
        ).one()
        assert tuple(row) == ("clinic_legacy", None, None, 1)


def test_clean_schema_can_issue_onboarding_without_seed(tmp_path):
    target = create_engine(f"sqlite:///{tmp_path / 'clean-fb5.db'}", future=True)
    Base.metadata.create_all(target)
    migrate_fb5_schema(target)
    with Session(target) as db:
        assert db.execute(text("SELECT COUNT(*) FROM clinics")).scalar_one() == 0
        issued = issue_onboarding_token(db, base_url="http://localhost:5173")
        assert "/setup#token=" in issued.setup_link
        assert db.execute(text("SELECT COUNT(*) FROM clinics")).scalar_one() == 0


def test_fb5_ownership_triggers_reject_cross_clinic_links(db_session):
    db_session.add(
        PatientExternalIdentity(
            external_identity_id="pei_bad_scope",
            clinic_id=fixture.CLINIC_B_ID,
            patient_id=fixture.PATIENT_ID,
            source_system="legacy",
            external_patient_id="P-1",
            name_sha256="0" * 64,
            created_at=datetime.now(),
        )
    )
    with pytest.raises(IntegrityError, match="patient_external_scope"):
        db_session.flush()
    db_session.rollback()

    db_session.add(
        PatientImportBatch(
            batch_id="pib_bad_scope",
            clinic_id=fixture.CLINIC_ID,
            source_system="legacy",
            content_sha256="1" * 64,
            status="previewed",
            total_rows=1,
            created_by=fixture.USER_CLINICIAN_B_ID,
            created_at=datetime.now(),
            committed_at=None,
        )
    )
    with pytest.raises(IntegrityError, match="patient_import_batch_scope"):
        db_session.flush()
    db_session.rollback()

    db_session.add(
        ClinicSettings(
            clinic_id=fixture.CLINIC_ID,
            ai_mode_override=None,
            voice_enabled_override=None,
            version=1,
            updated_by=fixture.USER_CLINICIAN_B_ID,
            updated_at=datetime.now(),
        )
    )
    with pytest.raises(IntegrityError, match="clinic_settings_scope"):
        db_session.flush()
