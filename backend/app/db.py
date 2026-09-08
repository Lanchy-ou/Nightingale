"""Database engine / session.

Unit tests keep the fast plain-SQLite path through ``NANTINGALE_DB_URL``.
The D5 single-machine deployment uses SQLCipher with a key supplied separately
through ``NANTINGALE_DB_KEY`` so credentials never have to appear in a URL,
command line, repository file or log.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import URL, create_engine, event as sqlalchemy_event
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


def __getattr__(name):
    # Lazy compatibility exports avoid cycles while models import Base.
    if name.startswith("migrate_") or name == "install_clinic_isolation_schema" or name.startswith("_A3_"):
        from . import schema_migrations
        return getattr(schema_migrations, name)
    raise AttributeError(name)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
