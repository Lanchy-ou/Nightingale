from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import AuditLog, Task
from seed import fixture


CREATE_URL = f"/api/events/{fixture.EVT_DOC_0821}/tasks"


def _create(client, **overrides):
    payload = {
        "title": "Complete blood test",
        "description": "Clinic-only coordination detail",
        "assigned_role": "patient",
        "assigned_user_id": fixture.USER_PATIENT_ID,
        "patient_visible": True,
        "due_at": "2026-08-28T17:00:00",
        "source_artifact_id": fixture.ART_DOC_TRANSCRIPT,
        "source_span": {"kind": "segment", "index": 16, "offset": [0, 61]},
    }
    payload.update(overrides)
    return client.post(CREATE_URL, json=payload)


def test_clinician_creates_first_class_task_with_metadata_only_audit(clinician_client, db_session):
    response = _create(clinician_client, title="Repeat blood test")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "open"
    assert body["event_id"] == fixture.EVT_DOC_0821
    assert body["created_by"] == fixture.USER_CLINICIAN_ID

    audit = db_session.scalar(
        select(AuditLog).where(
            AuditLog.action == "task_create",
            AuditLog.target_id == body["task_id"],
        )
    )
    assert audit is not None
    assert audit.actor_id == fixture.USER_CLINICIAN_ID
    assert audit.details == {"status": "open"}
    assert "Clinic-only" not in str(audit.details)


def test_patient_start_report_done_then_clinic_verifies(clinician_client, patient_client):
    task = _create(clinician_client, title="Bring symptom diary").json()
    started = patient_client.post(
        f"/api/tasks/{task['task_id']}/transition",
        json={"expected_status": "open", "status": "in_progress"},
    )
    assert started.status_code == 200
    assert started.json()["status"] == "in_progress"

    reported = patient_client.post(
        f"/api/tasks/{task['task_id']}/transition",
        json={"expected_status": "in_progress", "status": "reported_done"},
    )
    assert reported.status_code == 200
    assert reported.json()["status"] == "reported_done"
    assert reported.json()["reported_done_at"] is not None

    verified = clinician_client.post(
        f"/api/tasks/{task['task_id']}/transition",
        json={"expected_status": "reported_done", "status": "completed"},
    )
    assert verified.status_code == 200
    assert verified.json()["status"] == "completed"
    assert verified.json()["completed_by"] == fixture.USER_CLINICIAN_ID


def test_stale_expected_status_is_deterministic_409(clinician_client, patient_client):
    task = _create(clinician_client, title="Stale write task").json()
    first = patient_client.post(
        f"/api/tasks/{task['task_id']}/transition",
        json={"expected_status": "open", "status": "in_progress"},
    )
    stale = patient_client.post(
        f"/api/tasks/{task['task_id']}/transition",
        json={"expected_status": "open", "status": "reported_done"},
    )
    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "conflict"
    assert stale.json()["error"]["current_status"] == "in_progress"


def test_simultaneous_transitions_have_one_winner_and_one_409():
    barrier = Barrier(3)

    def transition(status: str):
        with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_ID}) as client:
            barrier.wait()
            return client.post(
                f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
                json={"expected_status": "open", "status": status},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(transition, "in_progress")
        second = pool.submit(transition, "reported_done")
        barrier.wait()
        responses = [first.result(), second.result()]

    assert sorted(response.status_code for response in responses) == [200, 409]
    conflict = next(response for response in responses if response.status_code == 409)
    assert conflict.json()["error"]["code"] == "conflict"
    assert conflict.json()["error"]["current_status"] in {"in_progress", "reported_done"}


def test_completed_and_cancelled_are_terminal(clinician_client, patient_client):
    completed = _create(clinician_client, title="Terminal complete").json()
    patient_client.post(
        f"/api/tasks/{completed['task_id']}/transition",
        json={"expected_status": "open", "status": "reported_done"},
    )
    clinician_client.post(
        f"/api/tasks/{completed['task_id']}/transition",
        json={"expected_status": "reported_done", "status": "completed"},
    )
    assert clinician_client.post(
        f"/api/tasks/{completed['task_id']}/transition",
        json={"expected_status": "completed", "status": "open"},
    ).status_code == 422

    cancelled = _create(clinician_client, title="Terminal cancelled").json()
    assert clinician_client.post(
        f"/api/tasks/{cancelled['task_id']}/transition",
        json={"expected_status": "open", "status": "cancelled"},
    ).status_code == 200
    assert clinician_client.post(
        f"/api/tasks/{cancelled['task_id']}/transition",
        json={"expected_status": "cancelled", "status": "in_progress"},
    ).status_code == 422


def test_fixture_contains_open_and_completed_longitudinal_tasks(db_session):
    tasks = {task.task_id: task for task in db_session.scalars(select(Task)).all()}
    assert tasks[fixture.TASK_BLOOD_TEST].status == "open"
    assert tasks[fixture.TASK_SYMPTOM_DIARY].status == "completed"
    history = db_session.scalars(
        select(AuditLog)
        .where(AuditLog.target_id == fixture.TASK_SYMPTOM_DIARY)
        .order_by(AuditLog.created_at)
    ).all()
    assert [row.details for row in history] == [
        {"status": "open"},
        {"from_status": "open", "to_status": "reported_done"},
        {"from_status": "reported_done", "to_status": "completed"},
    ]
