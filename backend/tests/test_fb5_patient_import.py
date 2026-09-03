from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from hashlib import sha256

from sqlalchemy import select
from fastapi.testclient import TestClient

from app.ids import new_id
from app.main import app
from app.models import (
    AuditLog,
    Patient,
    PatientExternalIdentity,
    PatientImportBatch,
    User,
)
from seed import fixture


CSV = "external_patient_id,name\nP-100,Jordan Lee\nP-101,Samira Noor\n"


def _preview(client, content: bytes | str, source: str = "legacy_ehr"):
    return client.post(
        f"/api/admin/patient-imports/preview?source_system={source}",
        content=content,
        headers={"Content-Type": "text/csv"},
    )


def test_preview_is_non_mutating_and_reports_invalid_duplicate_and_name_conflict(
    admin_client, db_session
):
    before = db_session.query(Patient).count()
    csv_text = (
        "external_patient_id,name\n"
        "P-100,Jordan Lee\n"
        "P-100,Jordan Lee\n"
        "P-101,\n"
        "P-102,Alice Tan\n"
        "P-103,Samira Noor\n"
    )
    response = _preview(admin_client, csv_text)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "previewed"
    statuses = {row["row_number"]: (row["status"], row["error_code"]) for row in body["rows"]}
    assert statuses == {
        2: ("invalid", "duplicate_external_id"),
        3: ("invalid", "duplicate_external_id"),
        4: ("invalid", "name_required"),
        5: ("conflict", "possible_existing_patient"),
        6: ("ready", None),
    }
    assert body["counts"] == {
        "ready": 1,
        "imported": 0,
        "unchanged": 0,
        "invalid": 3,
        "conflict": 1,
    }
    db_session.expire_all()
    assert db_session.query(Patient).count() == before


def test_commit_writes_valid_rows_atomically_and_replay_is_idempotent(
    admin_client, db_session
):
    preview = _preview(admin_client, CSV)
    assert preview.status_code == 200
    batch_id = preview.json()["batch_id"]

    first = admin_client.post(f"/api/admin/patient-imports/{batch_id}/commit")
    assert first.status_code == 200, first.text
    assert first.json()["status"] == "committed"
    assert first.json()["counts"]["imported"] == 2

    db_session.expire_all()
    imported = db_session.scalars(
        select(Patient).where(Patient.name.in_(["Jordan Lee", "Samira Noor"]))
    ).all()
    assert len(imported) == 2
    identities = db_session.scalars(
        select(PatientExternalIdentity).where(
            PatientExternalIdentity.clinic_id == fixture.CLINIC_ID,
            PatientExternalIdentity.source_system == "legacy_ehr",
        )
    ).all()
    assert {row.external_patient_id for row in identities} == {"P-100", "P-101"}

    second = admin_client.post(f"/api/admin/patient-imports/{batch_id}/commit")
    assert second.status_code == 200
    assert second.json() == first.json()
    db_session.expire_all()
    assert db_session.query(PatientExternalIdentity).filter_by(
        clinic_id=fixture.CLINIC_ID, source_system="legacy_ehr"
    ).count() == 2

    replay_preview = _preview(admin_client, CSV)
    assert replay_preview.status_code == 200
    assert replay_preview.json()["batch_id"] == batch_id
    assert replay_preview.json()["status"] == "committed"


def test_existing_external_identity_is_unchanged_or_conflict_without_overwrite(
    admin_client, db_session
):
    patient = Patient(
        patient_id=new_id("pat"), clinic_id=fixture.CLINIC_ID, name="Jordan Lee"
    )
    db_session.add(patient)
    db_session.flush()
    db_session.add(
        PatientExternalIdentity(
            external_identity_id=new_id("pei"),
            clinic_id=fixture.CLINIC_ID,
            patient_id=patient.patient_id,
            source_system="legacy_ehr",
            external_patient_id="P-100",
            name_sha256=sha256("Jordan Lee".encode()).hexdigest(),
            created_at=datetime(2026, 9, 2, 12, 0),
        )
    )
    db_session.commit()

    same = _preview(admin_client, "external_patient_id,name\nP-100,Jordan Lee\n")
    assert same.json()["rows"][0]["status"] == "unchanged"

    changed = _preview(admin_client, "external_patient_id,name\nP-100,Jordan Lim\n")
    assert changed.json()["rows"][0]["status"] == "conflict"
    assert changed.json()["rows"][0]["error_code"] == "external_identity_mismatch"
    committed = admin_client.post(
        f"/api/admin/patient-imports/{changed.json()['batch_id']}/commit"
    )
    assert committed.status_code == 200
    db_session.expire_all()
    assert db_session.get(Patient, patient.patient_id).name == "Jordan Lee"


def test_import_scope_roles_and_audit_are_clinic_safe(
    admin_client, clinician_client, client, db_session
):
    assert _preview(clinician_client, CSV).status_code == 403
    created = _preview(admin_client, CSV).json()
    batch_id = created["batch_id"]
    clinic_b_admin_id = "usr_admin_fb5_clinic_b"
    db_session.add(
        User(
            user_id=clinic_b_admin_id,
            clinic_id=fixture.CLINIC_B_ID,
            name="Other Clinic Admin",
            role="admin",
            patient_id=None,
        )
    )
    db_session.commit()

    cross = client.post(
        f"/api/admin/patient-imports/{batch_id}/commit",
        headers={"X-User-Id": clinic_b_admin_id},
    )
    missing = client.post(
        "/api/admin/patient-imports/pib_missing/commit",
        headers={"X-User-Id": clinic_b_admin_id},
    )
    assert cross.status_code == missing.status_code == 404
    assert cross.json() == missing.json()

    admin_client.post(f"/api/admin/patient-imports/{batch_id}/commit")
    audits = db_session.scalars(
        select(AuditLog).where(AuditLog.target_id == batch_id)
    ).all()
    assert [row.action for row in audits] == [
        "patient_import_previewed",
        "patient_import_committed",
    ]
    blob = repr([row.details for row in audits])
    assert "Jordan Lee" not in blob
    assert "Samira Noor" not in blob


def test_import_rejects_bad_encoding_headers_source_and_size(admin_client):
    assert admin_client.post(
        "/api/admin/patient-imports/preview?source_system=legacy",
        json={"external_patient_id": "P-1", "name": "Jordan"},
    ).status_code == 415
    assert _preview(admin_client, b"\xff\xfe\x00").status_code == 422
    assert _preview(admin_client, "id,name\n1,Jordan\n").status_code == 422
    assert _preview(admin_client, CSV, source="bad source!").status_code == 422
    assert _preview(admin_client, b"x" * (1_048_576 + 1)).status_code == 413

    too_many = "external_patient_id,name\n" + "".join(
        f"P-{index},Patient {index}\n" for index in range(1001)
    )
    assert _preview(admin_client, too_many).status_code == 422


def test_concurrent_commit_is_idempotent(admin_client, db_session):
    batch_id = _preview(admin_client, CSV).json()["batch_id"]

    def commit_once():
        with TestClient(app, headers={"X-User-Id": fixture.USER_ADMIN_ID}) as contender:
            response = contender.post(f"/api/admin/patient-imports/{batch_id}/commit")
            return response.status_code, response.json()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _index: commit_once(), range(2)))

    assert [status for status, _body in results] == [200, 200]
    assert results[0][1] == results[1][1]
    db_session.expire_all()
    assert db_session.query(PatientExternalIdentity).filter_by(
        clinic_id=fixture.CLINIC_ID, source_system="legacy_ehr"
    ).count() == 2
