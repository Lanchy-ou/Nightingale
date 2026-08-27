from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import URL, create_engine, text

from app.db import Base
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
    assert row == ("cln_storage_probe", "Encrypted demo clinic")


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
