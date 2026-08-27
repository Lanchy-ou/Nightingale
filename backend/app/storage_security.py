"""SQLCipher database, backup and restore primitives for the D5 demo.

Keys are accepted only as in-memory arguments supplied by callers from the
environment.  They use the same safely quoted passphrase form as SQLAlchemy's
SQLCipher dialect and are never printed.
"""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def _driver():
    try:
        import sqlcipher3
    except ImportError as exc:  # pragma: no cover - deployment dependency gate
        raise RuntimeError("sqlcipher3 is required for encrypted storage") from exc
    return sqlcipher3


def _require_key(key: str, label: str) -> None:
    if len(key) < 32:
        raise ValueError(f"{label} must contain at least 32 characters")


def validate_distinct_keys(*named_keys: tuple[str, str]) -> None:
    """Require non-empty, strong and pairwise-distinct storage keys."""
    for label, key in named_keys:
        _require_key(key, label)
    if len({key for _, key in named_keys}) != len(named_keys):
        labels = ", ".join(label for label, _ in named_keys)
        raise ValueError(f"Storage keys must be pairwise distinct: {labels}")


def _passphrase_literal(key: str) -> str:
    # Match SQLAlchemy's pysqlcipher dialect: a double-quoted SQLite token with
    # embedded double quotes doubled.  The value is never logged or returned.
    return '"' + key.replace('"', '""') + '"'


@contextmanager
def open_sqlcipher(path: Path | str, key: str) -> Iterator[object]:
    _require_key(key, "SQLCipher key")
    connection = _driver().connect(str(Path(path).resolve()))
    try:
        connection.execute(f"PRAGMA key = {_passphrase_literal(key)}")
        # Force the first page read now so a wrong key fails at this boundary.
        connection.execute("SELECT count(*) FROM sqlite_master").fetchone()
        yield connection
    finally:
        connection.close()


def assert_sqlcipher_file(path: Path | str, key: str) -> dict[str, object]:
    target = Path(path).resolve()
    if not target.is_file():
        raise FileNotFoundError(target)
    if target.stat().st_size < 16:
        raise RuntimeError("Encrypted database file is unexpectedly small")
    if target.read_bytes()[:16] == b"SQLite format 3\x00":
        raise RuntimeError("Database has a plaintext SQLite header")

    # A normal sqlite3 reader must not be able to inspect the schema.
    try:
        with sqlite3.connect(target) as plain:
            plain.execute("SELECT name FROM sqlite_master").fetchall()
    except sqlite3.DatabaseError:
        plain_reader_blocked = True
    else:
        plain_reader_blocked = False
    if not plain_reader_blocked:
        raise RuntimeError("Database schema was readable without the SQLCipher key")

    with open_sqlcipher(target, key) as encrypted:
        cipher_version = encrypted.execute("PRAGMA cipher_version").fetchone()[0]
        table_count = encrypted.execute(
            "SELECT count(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    if not cipher_version:
        raise RuntimeError("SQLCipher runtime did not report a cipher version")
    return {
        "cipher_version": cipher_version,
        "table_count": table_count,
        "plaintext_header": False,
        "plain_reader_blocked": True,
    }


def _encrypted_export(
    source_path: Path,
    source_key: str,
    target_path: Path,
    target_key: str,
) -> None:
    _require_key(source_key, "Source SQLCipher key")
    _require_key(target_key, "Target SQLCipher key")
    if source_path.resolve() == target_path.resolve():
        raise ValueError("Source and target database paths must differ")
    if target_path.exists():
        raise FileExistsError(target_path)
    if not source_path.is_file():
        raise FileNotFoundError(source_path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open_sqlcipher(source_path, source_key) as connection:
            connection.execute(
                f"ATTACH DATABASE ? AS secured_export KEY {_passphrase_literal(target_key)}",
                (str(target_path.resolve()),),
            )
            try:
                connection.execute("SELECT sqlcipher_export('secured_export')").fetchone()
            finally:
                connection.execute("DETACH DATABASE secured_export")
    except Exception:
        # Only the one explicit output path can have been created by this call.
        if target_path.exists():
            target_path.unlink()
        raise

    assert_sqlcipher_file(target_path, target_key)


def create_encrypted_backup(
    database_path: Path | str,
    database_key: str,
    backup_path: Path | str,
    backup_key: str,
) -> None:
    validate_distinct_keys(
        ("Database key", database_key),
        ("Backup key", backup_key),
    )
    _encrypted_export(
        Path(database_path).resolve(),
        database_key,
        Path(backup_path).resolve(),
        backup_key,
    )


def restore_encrypted_backup(
    backup_path: Path | str,
    backup_key: str,
    restored_database_path: Path | str,
    restored_database_key: str,
    original_database_key: str,
) -> None:
    validate_distinct_keys(
        ("Original database key", original_database_key),
        ("Backup key", backup_key),
        ("Restored database key", restored_database_key),
    )
    _encrypted_export(
        Path(backup_path).resolve(),
        backup_key,
        Path(restored_database_path).resolve(),
        restored_database_key,
    )
