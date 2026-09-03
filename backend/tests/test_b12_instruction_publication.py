"""B12 clinician publication/correction/withdrawal lifecycle contract."""
from __future__ import annotations

from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db import Base, migrate_b12_schema
from app.main import app
from app.models import (
    Artifact,
    AuditLog,
    Clinic,
    Event,
    Patient,
    PatientInstructionPublication,
    PatientInstructionReceipt,
    User,
)
from seed import fixture


EVENT_ID = fixture.EVT_REVIEW_0826
PV_URL = f"/api/patients/{fixture.PATIENT_ID}/patient-view"


def _create_draft(clinician_client, instruction="Take the updated medicine as discussed."):
    response = clinician_client.post(
        f"/api/events/{EVENT_ID}/notes",
        json={
            "artifact_type": "patient_instruction",
            "content": {
                "instruction": instruction,
                "follow_up": "Review at the next appointment.",
            },
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _patient_instruction_ids(patient_client):
    body = patient_client.get(PV_URL).json()
    return {
        row["artifact_id"]
        for row in body["visit_summaries"]["summaries"]
    }


def _publish(clinician_client, artifact_id):
    return clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/publish",
        json={"expected_state": "draft"},
    )


def test_new_instruction_is_draft_and_hidden_until_published(
    clinician_client, patient_client, db_session
):
    draft = _create_draft(clinician_client)
    artifact_id = draft["artifact_id"]

    publication = clinician_client.get(
        f"/api/patient-instructions/{artifact_id}/publication"
    )
    assert publication.status_code == 200
    assert publication.json()["state"] == "draft"
    assert artifact_id not in _patient_instruction_ids(patient_client)
    patient_artifacts = patient_client.get(
        f"/api/events/{EVENT_ID}/artifacts"
    ).json()
    assert artifact_id not in {row["artifact_id"] for row in patient_artifacts}
    event_row = next(
        row
        for row in patient_client.get(
            f"/api/patients/{fixture.PATIENT_ID}/events"
        ).json()
        if row["event_id"] == EVENT_ID
    )
    assert event_row["artifact_count"] == 1
    assert db_session.scalar(
        select(PatientInstructionReceipt).where(
            PatientInstructionReceipt.instruction_artifact_id == artifact_id
        )
    ) is None


def test_publish_is_idempotent_and_creates_unviewed_receipt(
    clinician_client, patient_client, db_session
):
    artifact_id = _create_draft(clinician_client)["artifact_id"]

    first = _publish(clinician_client, artifact_id)
    second = _publish(clinician_client, artifact_id)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["state"] == "published"
    assert first.json()["lineage_revision"] == 1
    assert artifact_id in _patient_instruction_ids(patient_client)
    receipt = db_session.scalar(
        select(PatientInstructionReceipt).where(
            PatientInstructionReceipt.instruction_artifact_id == artifact_id
        )
    )
    assert receipt is not None and receipt.state == "available"
    audits = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == artifact_id,
        AuditLog.action == "instruction_published",
    )))
    assert len(audits) == 1


def test_only_same_clinic_clinician_can_publish(
    clinician_client, patient_client, staff_client, admin_client
):
    artifact_id = _create_draft(clinician_client)["artifact_id"]
    url = f"/api/patient-instructions/{artifact_id}/publish"
    payload = {"expected_state": "draft"}

    assert patient_client.post(url, json=payload).status_code == 403
    assert staff_client.post(url, json=payload).status_code == 403
    assert admin_client.post(url, json=payload).status_code == 403
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}) as other_clinic:
        assert other_clinic.post(url, json=payload).status_code == 404


def test_publication_read_is_clinical_and_all_mutations_are_clinician_only(
    clinician_client, patient_client, staff_client, admin_client
):
    artifact_id = _create_draft(clinician_client)["artifact_id"]
    _publish(clinician_client, artifact_id)
    read_url = f"/api/patient-instructions/{artifact_id}/publication"
    correct_url = f"/api/patient-instructions/{artifact_id}/correct"
    withdraw_url = f"/api/patient-instructions/{artifact_id}/withdraw"
    correction = {
        "expected_state": "published",
        "correction_id": "unauthorized-correction",
        "content": {"instruction": "Unauthorized change", "follow_up": None},
    }
    withdrawal = {"expected_state": "published", "reason_code": "entered_in_error"}

    assert staff_client.get(read_url).status_code == 200
    assert patient_client.get(read_url).status_code == 403
    assert admin_client.get(read_url).status_code == 403
    for caller in (patient_client, staff_client, admin_client):
        assert caller.post(correct_url, json=correction).status_code == 403
        assert caller.post(withdraw_url, json=withdrawal).status_code == 403
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}) as other_clinic:
        assert other_clinic.post(correct_url, json=correction).status_code == 404
        assert other_clinic.post(withdraw_url, json=withdrawal).status_code == 404


def test_mismatched_publication_ownership_fails_closed(
    clinician_client, patient_client, db_session
):
    artifact_id = _create_draft(clinician_client)["artifact_id"]
    publication = db_session.scalar(select(PatientInstructionPublication).where(
        PatientInstructionPublication.instruction_artifact_id == artifact_id
    ))
    publication.patient_id = fixture.PATIENT_B_ID
    db_session.commit()

    assert clinician_client.get(
        f"/api/patient-instructions/{artifact_id}/publication"
    ).status_code == 404
    assert _publish(clinician_client, artifact_id).status_code == 404
    assert artifact_id not in _patient_instruction_ids(patient_client)


def test_correction_supersedes_without_rewriting_and_starts_new_receipt(
    clinician_client, patient_client, db_session
):
    artifact_id = _create_draft(clinician_client, "Take one tablet each morning.")["artifact_id"]
    assert _publish(clinician_client, artifact_id).status_code == 200
    assert patient_client.post(
        f"/api/patient-instructions/{artifact_id}/versions/1/open"
    ).status_code == 200
    assert patient_client.post(
        f"/api/patient-instructions/{artifact_id}/versions/1/acknowledge"
    ).status_code == 200

    correction = {
        "expected_state": "published",
        "correction_id": "correction-001",
        "content": {
            "instruction": "Take one tablet each evening.",
            "follow_up": "Review at the next appointment.",
        },
    }
    first = clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/correct", json=correction
    )
    second = clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/correct", json=correction
    )

    assert first.status_code == 200, first.text
    assert second.status_code == 200
    assert first.json() == second.json()
    new_id = first.json()["artifact_id"]
    assert new_id != artifact_id
    assert first.json()["state"] == "published"
    assert first.json()["lineage_revision"] == 2
    assert db_session.get(Artifact, artifact_id).content["instruction"] == "Take one tablet each morning."
    assert db_session.get(Artifact, new_id).content["instruction"] == "Take one tablet each evening."

    old = clinician_client.get(
        f"/api/patient-instructions/{artifact_id}/publication"
    ).json()
    assert old["state"] == "superseded"
    assert old["superseded_by_artifact_id"] == new_id
    visible = _patient_instruction_ids(patient_client)
    assert new_id in visible and artifact_id not in visible
    receipts = {
        row.instruction_artifact_id: row.state
        for row in db_session.scalars(select(PatientInstructionReceipt)).all()
    }
    assert receipts[artifact_id] == "acknowledged"
    assert receipts[new_id] == "available"

    changed_replay = clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/correct",
        json={**correction, "content": {**correction["content"], "instruction": "Different replay"}},
    )
    assert changed_replay.status_code == 409


def test_withdraw_hides_content_but_preserves_acknowledgement_and_history(
    clinician_client, patient_client, db_session
):
    artifact_id = _create_draft(clinician_client)["artifact_id"]
    _publish(clinician_client, artifact_id)
    patient_client.post(f"/api/patient-instructions/{artifact_id}/versions/1/open")
    patient_client.post(f"/api/patient-instructions/{artifact_id}/versions/1/acknowledge")

    url = f"/api/patient-instructions/{artifact_id}/withdraw"
    payload = {"expected_state": "published", "reason_code": "no_longer_applicable"}
    first = clinician_client.post(url, json=payload)
    second = clinician_client.post(url, json=payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["state"] == "withdrawn"
    assert first.json()["withdrawal_reason_code"] == "no_longer_applicable"
    assert artifact_id not in _patient_instruction_ids(patient_client)
    assert db_session.get(Artifact, artifact_id) is not None
    receipt = db_session.scalar(select(PatientInstructionReceipt).where(
        PatientInstructionReceipt.instruction_artifact_id == artifact_id
    ))
    assert receipt.state == "acknowledged"
    audits = list(db_session.scalars(select(AuditLog).where(
        AuditLog.target_id == artifact_id,
        AuditLog.action == "instruction_withdrawn",
    )))
    assert len(audits) == 1
    assert "Take the updated medicine" not in str(audits[0].details)


def test_withdraw_before_open_preserves_available_receipt(
    clinician_client, patient_client, db_session
):
    artifact_id = _create_draft(clinician_client)["artifact_id"]
    _publish(clinician_client, artifact_id)

    response = clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/withdraw",
        json={"expected_state": "published", "reason_code": "entered_in_error"},
    )

    assert response.status_code == 200
    assert artifact_id not in _patient_instruction_ids(patient_client)
    receipt = db_session.scalar(select(PatientInstructionReceipt).where(
        PatientInstructionReceipt.instruction_artifact_id == artifact_id
    ))
    assert receipt is not None and receipt.state == "available"
    assert patient_client.post(
        f"/api/patient-instructions/{artifact_id}/versions/1/open"
    ).status_code == 404


def test_invalid_transition_and_withdrawal_reason_fail_closed(clinician_client):
    artifact_id = _create_draft(clinician_client)["artifact_id"]
    early = clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/withdraw",
        json={"expected_state": "published", "reason_code": "entered_in_error"},
    )
    assert early.status_code == 409
    _publish(clinician_client, artifact_id)
    invalid = clinician_client.post(
        f"/api/patient-instructions/{artifact_id}/withdraw",
        json={"expected_state": "published", "reason_code": "free text is forbidden"},
    )
    assert invalid.status_code == 422


def test_b12_migration_is_idempotent_and_backfills_legacy_visible_instruction(tmp_path):
    target = create_engine(f"sqlite:///{tmp_path / 'b12-legacy.db'}", future=True)
    Base.metadata.create_all(target)
    PatientInstructionPublication.__table__.drop(target)
    with Session(target) as db:
        db.add(Clinic(clinic_id="clinic_b12", name="B12 Clinic"))
        db.add(Patient(patient_id="patient_b12", clinic_id="clinic_b12", name="Patient B12"))
        db.add(User(
            user_id="clinician_b12", clinic_id="clinic_b12", name="Clinician B12",
            role="clinician", professional_title=None, patient_id=None,
        ))
        db.add(Event(
            event_id="event_b12", patient_id="patient_b12", clinic_id="clinic_b12",
            event_type="clinician_review", encounter_id=None,
            started_at=datetime(2026, 9, 2, 10, 0), ended_at=None,
            created_at=datetime(2026, 9, 2, 10, 0),
        ))
        db.add(Artifact(
            artifact_id="instruction_b12", event_id="event_b12",
            artifact_type="patient_instruction", author_role="clinician",
            author_id="clinician_b12", content={"instruction": "Legacy instruction."},
            created_at=datetime(2026, 9, 2, 10, 5), version=1,
            provenance_pointer=None,
        ))
        db.commit()

    migrate_b12_schema(target)
    migrate_b12_schema(target)

    with Session(target) as db:
        rows = list(db.scalars(select(PatientInstructionPublication)))
        assert len(rows) == 1
        assert rows[0].instruction_artifact_id == "instruction_b12"
        assert rows[0].state == "published"
        assert rows[0].lineage_revision == 1
