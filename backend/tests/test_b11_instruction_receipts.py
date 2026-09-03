"""B11 patient-portal instruction acknowledgement contract.

The receipt is bound to one patient-facing instruction Artifact version.  A
normal Patient View read is never evidence that the patient opened it, and an
acknowledgement means only "I have read this".
"""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base, migrate_b11_schema, migrate_b12_schema
from app.main import app
from app.models import (
    AUDIT_ACTIONS,
    Artifact,
    AuditLog,
    Clinic,
    Event,
    Patient,
    PatientInstructionReceipt,
    User,
)
from seed import fixture


ARTIFACT_ID = fixture.ART_REVIEW_INSTRUCTION
VERSION = 1
BASE = f"/api/patient-instructions/{ARTIFACT_ID}/versions/{VERSION}"


def test_receipt_actions_are_registered_for_audit_review():
    assert {"instruction_opened", "instruction_acknowledged"} <= set(AUDIT_ACTIONS)


def test_patient_view_read_does_not_mark_instruction_viewed(patient_client, db_session):
    before = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == ARTIFACT_ID,
        AuditLog.action.in_({"instruction_opened", "instruction_acknowledged"}),
    )))

    response = patient_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/patient-view"
    )

    assert response.status_code == 200
    instruction = response.json()["today"]["instruction"]
    assert instruction["artifact_version"] == VERSION
    assert instruction["receipt"] == {
        "status": "not_viewed",
        "opened_at": None,
        "acknowledged_at": None,
    }
    db_session.expire_all()
    after = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == ARTIFACT_ID,
        AuditLog.action.in_({"instruction_opened", "instruction_acknowledged"}),
    )))
    assert len(after) == len(before)


def test_open_is_explicit_and_idempotent(patient_client, db_session):
    first = patient_client.post(f"{BASE}/open")
    second = patient_client.post(f"{BASE}/open")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "viewed"
    assert second.json() == first.json()

    db_session.expire_all()
    audits = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == ARTIFACT_ID,
        AuditLog.action == "instruction_opened",
    )))
    assert len(audits) == 1
    assert audits[0].details == {"artifact_version": VERSION}


def test_acknowledge_requires_open_then_is_idempotent(patient_client, db_session):
    too_early = patient_client.post(f"{BASE}/acknowledge")
    assert too_early.status_code == 409

    patient_client.post(f"{BASE}/open")
    first = patient_client.post(f"{BASE}/acknowledge")
    second = patient_client.post(f"{BASE}/acknowledge")

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["status"] == "acknowledged"
    assert first.json()["acknowledged_at"] is not None
    assert second.json() == first.json()

    db_session.expire_all()
    audits = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == ARTIFACT_ID,
        AuditLog.action == "instruction_acknowledged",
    )))
    assert len(audits) == 1
    assert audits[0].details == {"artifact_version": VERSION}


def test_receipt_scope_and_role_boundaries(
    patient_client, clinician_client, staff_client, admin_client
):
    with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_B_ID}) as other_patient:
        assert other_patient.post(f"{BASE}/open").status_code == 404
    with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_OTHER_ID}) as other_clinic:
        assert other_clinic.post(f"{BASE}/open").status_code == 404

    assert clinician_client.post(f"{BASE}/open").status_code == 403
    assert staff_client.post(f"{BASE}/open").status_code == 403
    assert admin_client.get(f"/api/patient-instructions/{ARTIFACT_ID}/receipts").status_code == 403

    assert clinician_client.get(
        f"/api/patient-instructions/{ARTIFACT_ID}/receipts"
    ).status_code == 200
    assert staff_client.get(
        f"/api/patient-instructions/{ARTIFACT_ID}/receipts"
    ).status_code == 200


def test_receipt_audit_contains_no_instruction_text(patient_client, db_session):
    patient_client.post(f"{BASE}/open")
    patient_client.post(f"{BASE}/acknowledge")

    db_session.expire_all()
    rows = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == ARTIFACT_ID,
        AuditLog.action.in_({"instruction_opened", "instruction_acknowledged"}),
    )))
    serialized = " ".join(str(row.details) for row in rows)
    instruction_text = db_session.get(Artifact, ARTIFACT_ID).content["instruction"]
    assert instruction_text not in serialized


def test_new_version_starts_unviewed_and_keeps_old_history(
    patient_client, clinician_client, db_session
):
    patient_client.post(f"{BASE}/open")
    patient_client.post(f"{BASE}/acknowledge")

    correction = clinician_client.post(
        f"/api/patient-instructions/{ARTIFACT_ID}/correct",
        json={
            "expected_state": "published",
            "correction_id": "b11-new-receipt-target",
            "content": {
                "instruction": "Continue the updated plan from your care team.",
                "follow_up": "Review at the next visit.",
            },
        },
    )
    assert correction.status_code == 200
    new_artifact_id = correction.json()["artifact_id"]

    view = patient_client.get(
        f"/api/patients/{fixture.PATIENT_ID}/patient-view"
    ).json()["today"]["instruction"]
    assert view["artifact_id"] == new_artifact_id
    assert view["artifact_version"] == 1
    assert view["receipt"]["status"] == "not_viewed"
    assert patient_client.post(f"{BASE}/open").status_code == 404

    history = clinician_client.get(
        f"/api/patient-instructions/{new_artifact_id}/receipts"
    ).json()
    assert [(row["artifact_version"], row["status"]) for row in history] == [(1, "not_viewed")]
    old_history = clinician_client.get(
        f"/api/patient-instructions/{ARTIFACT_ID}/receipts"
    ).json()
    assert [(row["artifact_version"], row["status"]) for row in old_history] == [(1, "acknowledged")]


def test_b11_migration_is_idempotent_and_backfills_existing_instruction(tmp_path):
    target = create_engine(f"sqlite:///{tmp_path / 'b11-legacy.db'}", future=True)
    Base.metadata.create_all(target)
    PatientInstructionReceipt.__table__.drop(target)
    with Session(target) as db:
        db.add(Clinic(clinic_id="clinic_b11", name="B11 Clinic"))
        db.add(Patient(patient_id="patient_b11", clinic_id="clinic_b11", name="Patient B11"))
        db.add(User(
            user_id="clinician_b11", clinic_id="clinic_b11", name="Clinician B11",
            role="clinician", professional_title=None, patient_id=None,
        ))
        db.add(Event(
            event_id="event_b11", patient_id="patient_b11", clinic_id="clinic_b11",
            event_type="clinician_review", encounter_id=None,
            started_at=datetime(2026, 9, 2, 10, 0),
            ended_at=None, created_at=datetime(2026, 9, 2, 10, 0),
        ))
        db.add(Artifact(
            artifact_id="instruction_b11", event_id="event_b11",
            artifact_type="patient_instruction", author_role="clinician",
            author_id="clinician_b11", content={"instruction": "Read this instruction."},
            created_at=datetime(2026, 9, 2, 10, 5), version=1,
            provenance_pointer=None,
        ))
        db.commit()

    migrate_b12_schema(target)
    migrate_b11_schema(target)
    migrate_b12_schema(target)
    migrate_b11_schema(target)

    with Session(target) as db:
        rows = list(db.scalars(select(PatientInstructionReceipt)))
        assert len(rows) == 1
        assert rows[0].instruction_artifact_id == "instruction_b11"
        assert rows[0].artifact_version == 1
        assert rows[0].state == "available"
