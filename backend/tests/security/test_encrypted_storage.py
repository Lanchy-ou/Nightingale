from __future__ import annotations

import sqlite3
from datetime import datetime

import pytest
from sqlalchemy import URL, create_engine, text

from app.db import Base
from app.voice.models import VoiceCaptureRecord  # noqa: F401 - register table in Base metadata
from app.storage_security import (
    assert_sqlcipher_file,
    create_encrypted_backup,
    open_sqlcipher,
    restore_encrypted_backup,
)


DB_KEY = "database-key-for-d5-tests-32-bytes-minimum"
BACKUP_KEY = "backup-key-for-d5-tests-separate-and-long"
RESTORE_KEY = "restored-database-key-for-d5-tests-long"


def _engine(path, key):
    return create_engine(
        URL.create(
            "sqlite+pysqlcipher",
            username="",
            password=key,
            database=str(path),
        ),
        connect_args={"check_same_thread": False},
    )


def test_database_backup_and_restore_are_really_encrypted(tmp_path):
    database = tmp_path / "demo.encrypted.db"
    backup = tmp_path / "demo.backup.encrypted.db"
    restored = tmp_path / "demo.restored.encrypted.db"

    engine = _engine(database, DB_KEY)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO clinics (clinic_id, name) VALUES (:id, :name)"),
            {"id": "cln_storage_probe", "name": "Encrypted demo clinic"},
        )
        connection.execute(
            text(
                "INSERT INTO patients (patient_id, clinic_id, name) VALUES "
                "('pat_storage_probe', 'cln_storage_probe', 'Synthetic Patient')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO events (event_id, patient_id, clinic_id, event_type, "
                "started_at, created_at) VALUES "
                "('evt_storage_probe', 'pat_storage_probe', 'cln_storage_probe', "
                "'historical_review', '2025-01-01 00:00:00', '2025-01-01 00:00:00')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO artifacts (artifact_id, event_id, artifact_type, "
                "author_role, content, created_at, version) VALUES "
                "('art_storage_probe', 'evt_storage_probe', 'clinician_note', "
                "'clinician', :content, '2025-01-01 00:00:00', 1)"
            ),
            {"content": '{"probe":true}'},
        )
        connection.execute(
            text(
                "INSERT INTO artifact_storage_state "
                "(artifact_id, tier, reason_codes, policy_version, evaluated_as_of, "
                "evaluated_at, source_sha256, codec, compressed_payload, original_bytes, "
                "compressed_bytes, roundtrip_verified_at) VALUES "
                "('art_storage_probe', 'cold', '[\"cold_age\"]', 'decay-v1', "
                "'2026-08-26 23:59:59', '2026-08-27 08:00:00', "
                "'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa', "
                "'zlib-json-v1', :payload, 14, 12, '2026-08-27 08:00:00')"
            ),
            {"payload": b"shadow-proof"},
        )
        tables = {
            row[0]
            for row in connection.execute(
                text("SELECT name FROM sqlite_master WHERE type='table'")
            )
        }
        assert "artifact_storage_state" in tables
        connection.execute(
            text(
                "INSERT INTO patients (patient_id, clinic_id, name) "
                "VALUES (:patient_id, :clinic_id, :name)"
            ),
            {
                "patient_id": "pat_voice_storage",
                "clinic_id": "cln_storage_probe",
                "name": "Synthetic Voice Patient",
            },
        )
        connection.execute(
            text(
                "INSERT INTO users (user_id, clinic_id, name, role, patient_id) "
                "VALUES (:user_id, :clinic_id, :name, :role, NULL)"
            ),
            {
                "user_id": "usr_voice_storage",
                "clinic_id": "cln_storage_probe",
                "name": "Synthetic Voice Clinician",
                "role": "clinician",
            },
        )
        connection.execute(
            text(
                "INSERT INTO voice_captures "
                "(capture_id, clinic_id, patient_id, created_by, capture_mode, "
                "event_type, idempotency_key, status, revision, started_at, "
                "created_at, updated_at, mime_type, byte_length, audio_sha256, "
                "audio_bytes) VALUES "
                "(:capture_id, :clinic_id, :patient_id, :created_by, :capture_mode, "
                ":event_type, :idempotency_key, :status, :revision, :started_at, "
                ":created_at, :updated_at, :mime_type, :byte_length, :audio_sha256, "
                ":audio_bytes)"
            ),
            {
                "capture_id": "vc_storage_probe",
                "clinic_id": "cln_storage_probe",
                "patient_id": "pat_voice_storage",
                "created_by": "usr_voice_storage",
                "capture_mode": "doctor_consult",
                "event_type": "doctor_consult",
                "idempotency_key": "storage-probe",
                "status": "uploaded",
                "revision": 2,
                "started_at": datetime(2026, 8, 27, 10, 0),
                "created_at": datetime(2026, 8, 27, 10, 0),
                "updated_at": datetime(2026, 8, 27, 10, 1),
                "mime_type": "audio/wav",
                "byte_length": 22,
                "audio_sha256": "0" * 64,
                "audio_bytes": b"synthetic-audio-bytes",
            },
        )
    engine.dispose()

    assert_sqlcipher_file(database, DB_KEY)
    assert database.read_bytes()[:16] != b"SQLite format 3\x00"
    with pytest.raises(sqlite3.DatabaseError):
        with sqlite3.connect(database) as plain:
            plain.execute("SELECT name FROM sqlite_master").fetchall()

    create_encrypted_backup(database, DB_KEY, backup, BACKUP_KEY)
    assert_sqlcipher_file(backup, BACKUP_KEY)
    with pytest.raises(Exception):
        with open_sqlcipher(backup, "wrong-key-that-is-also-long-enough") as wrong:
            wrong.execute("SELECT name FROM sqlite_master").fetchall()

    restore_encrypted_backup(backup, BACKUP_KEY, restored, RESTORE_KEY, DB_KEY)
    assert_sqlcipher_file(restored, RESTORE_KEY)
    with open_sqlcipher(restored, RESTORE_KEY) as connection:
        row = connection.execute(
            "SELECT clinic_id, name FROM clinics WHERE clinic_id = ?",
            ("cln_storage_probe",),
        ).fetchone()
        restored_tables = {
            item[0]
            for item in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        storage_row = connection.execute(
            "SELECT artifact_id, tier, policy_version, compressed_payload "
            "FROM artifact_storage_state WHERE artifact_id = ?",
            ("art_storage_probe",),
        ).fetchone()
        voice_row = connection.execute(
            "SELECT capture_id, audio_bytes FROM voice_captures WHERE capture_id = ?",
            ("vc_storage_probe",),
        ).fetchone()
    assert row == ("cln_storage_probe", "Encrypted demo clinic")
    assert "artifact_storage_state" in restored_tables
    assert storage_row == (
        "art_storage_probe",
        "cold",
        "decay-v1",
        b"shadow-proof",
    )
    assert voice_row == ("vc_storage_probe", b"synthetic-audio-bytes")


def test_backup_and_restore_refuse_to_overwrite_explicit_files(tmp_path):
    source = tmp_path / "source.db"
    output = tmp_path / "existing.db"
    output.write_bytes(b"do-not-overwrite")

    with pytest.raises(FileExistsError):
        create_encrypted_backup(source, DB_KEY, output, BACKUP_KEY)
    assert output.read_bytes() == b"do-not-overwrite"

    with pytest.raises(FileExistsError):
        restore_encrypted_backup(source, BACKUP_KEY, output, RESTORE_KEY, DB_KEY)
    assert output.read_bytes() == b"do-not-overwrite"


def test_wrong_source_or_backup_key_fails_closed_without_output(tmp_path):
    database = tmp_path / "source.encrypted.db"
    backup = tmp_path / "valid.backup.db"
    wrong_backup_output = tmp_path / "wrong-key.backup.db"
    wrong_restore_output = tmp_path / "wrong-key.restore.db"

    engine = _engine(database, DB_KEY)
    Base.metadata.create_all(engine)
    engine.dispose()
    create_encrypted_backup(database, DB_KEY, backup, BACKUP_KEY)

    with pytest.raises(Exception):
        create_encrypted_backup(
            database,
            "wrong-database-key-that-is-long-enough-123",
            wrong_backup_output,
            BACKUP_KEY,
        )
    assert not wrong_backup_output.exists()

    with pytest.raises(Exception):
        restore_encrypted_backup(
            backup,
            "wrong-backup-key-that-is-long-enough-12345",
            wrong_restore_output,
            RESTORE_KEY,
            DB_KEY,
        )
    assert not wrong_restore_output.exists()


def test_same_storage_keys_are_rejected_before_any_output(tmp_path):
    database = tmp_path / "source.encrypted.db"
    backup = tmp_path / "same-key.backup.db"
    restored = tmp_path / "same-key.restore.db"

    engine = _engine(database, DB_KEY)
    Base.metadata.create_all(engine)
    engine.dispose()

    with pytest.raises(ValueError, match="pairwise distinct"):
        create_encrypted_backup(database, DB_KEY, backup, DB_KEY)
    assert not backup.exists()

    create_encrypted_backup(database, DB_KEY, backup, BACKUP_KEY)
    with pytest.raises(ValueError, match="pairwise distinct"):
        restore_encrypted_backup(backup, BACKUP_KEY, restored, DB_KEY, DB_KEY)
    assert not restored.exists()

    with pytest.raises(ValueError, match="pairwise distinct"):
        restore_encrypted_backup(
            backup,
            BACKUP_KEY,
            restored,
            BACKUP_KEY,
            DB_KEY,
        )
    assert not restored.exists()
