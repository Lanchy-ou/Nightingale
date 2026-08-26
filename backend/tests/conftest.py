"""Shared test setup.

Sets NANTINGALE_DB_URL to a throwaway SQLite file BEFORE importing app modules,
so the engine never touches the real backend/nantingale.db.
"""
from __future__ import annotations

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["NANTINGALE_DB_URL"] = f"sqlite:///{_tmp.name}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from seed.seed import create_schema, seed  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _db():
    create_schema(engine)
    with SessionLocal() as db:
        seed(db)
    yield


@pytest.fixture()
def db_session():
    with SessionLocal() as db:
        yield db


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c
