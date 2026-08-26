"""Shared test setup.

Sets NANTINGALE_DB_URL to a throwaway SQLite file BEFORE importing app modules,
so the engine never touches the real backend/nantingale.db.

Isolation: the schema is created once per session; the fixture is re-seeded
before EVERY test, so write tests never depend on execution order.
"""
from __future__ import annotations

import os
import tempfile

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
os.environ["NANTINGALE_DB_URL"] = f"sqlite:///{_tmp.name}"
# Legacy X-User-Id/X-Role header auth is a test/development aid. D1 gates it
# behind NANTINGALE_DEMO_AUTH (default off); the existing header-based
# fixtures need it explicitly enabled. Session/cookie tests do not use it.
os.environ["NANTINGALE_DEMO_AUTH"] = "true"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from seed.seed import create_schema, seed  # noqa: E402

USER_IDS = {
    "clinician": "usr_clinician_01",
    "staff": "usr_staff_01",
    "patient": "usr_patient_01",
    "admin": "usr_admin_01",
    "clinician_other_clinic": "usr_clinician_02",
}


@pytest.fixture(scope="session", autouse=True)
def _schema():
    create_schema(engine)
    yield


@pytest.fixture(autouse=True)
def _seed_each_test():
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


def _authed_client(user_id: str):
    return TestClient(app, headers={"X-User-Id": user_id})


@pytest.fixture()
def clinician_client():
    with _authed_client(USER_IDS["clinician"]) as c:
        yield c


@pytest.fixture()
def staff_client():
    with _authed_client(USER_IDS["staff"]) as c:
        yield c


@pytest.fixture()
def patient_client():
    with _authed_client(USER_IDS["patient"]) as c:
        yield c


@pytest.fixture()
def admin_client():
    with _authed_client(USER_IDS["admin"]) as c:
        yield c
