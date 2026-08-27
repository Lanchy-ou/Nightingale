from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed import fixture


def _payload(**overrides):
    body = {
        "title": "Patient action",
        "description": "internal",
        "assigned_role": "patient",
        "assigned_user_id": fixture.USER_PATIENT_ID,
        "patient_visible": True,
        "due_at": None,
        "source_artifact_id": None,
        "source_span": None,
    }
    body.update(overrides)
    return body


def test_patient_cannot_create_task(patient_client):
    response = patient_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks", json=_payload()
    )
    assert response.status_code == 403


def test_staff_and_clinician_can_create_same_clinic_task(staff_client, clinician_client):
    assert staff_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json=_payload(title="Staff-created task"),
    ).status_code == 200
    assert clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json=_payload(title="Clinician-created task"),
    ).status_code == 200


def test_cross_clinic_and_absent_task_have_uniform_404(client, db_session):
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}) as other:
        cross_create = other.post(
            f"/api/events/{fixture.EVT_DOC_0821}/tasks",
            json=_payload(assigned_user_id="does-not-exist", assigned_role="unknown"),
        )
        cross_transition = other.post(
            f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
            json={"expected_status": "terminal-secret", "status": "open"},
        )
        absent = other.post(
            "/api/tasks/task-does-not-exist/transition",
            json={"expected_status": "terminal-secret", "status": "open"},
        )
    assert cross_create.status_code == cross_transition.status_code == absent.status_code == 404
    assert cross_transition.json() == absent.json()


def test_patient_only_operates_own_visible_assigned_task(clinician_client, patient_client):
    cases = [
        _payload(title="Invisible", patient_visible=False),
        _payload(title="Staff assigned", assigned_role="staff", assigned_user_id=fixture.USER_STAFF_ID),
        _payload(title="Other patient", assigned_user_id=fixture.USER_PATIENT_B_ID),
    ]
    for body in cases:
        created = clinician_client.post(
            f"/api/events/{fixture.EVT_DOC_0821}/tasks", json=body
        )
        if created.status_code == 200:
            transition = patient_client.post(
                f"/api/tasks/{created.json()['task_id']}/transition",
                json={"expected_status": "open", "status": "in_progress"},
            )
            assert transition.status_code == 404


def test_patient_cannot_complete_or_cancel(clinician_client, patient_client):
    created = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks", json=_payload(title="Authority boundary")
    ).json()
    patient_client.post(
        f"/api/tasks/{created['task_id']}/transition",
        json={"expected_status": "open", "status": "reported_done"},
    )
    assert patient_client.post(
        f"/api/tasks/{created['task_id']}/transition",
        json={"expected_status": "reported_done", "status": "completed"},
    ).status_code == 403
    assert patient_client.post(
        f"/api/tasks/{created['task_id']}/transition",
        json={
            "expected_status": "reported_done",
            "status": "completed",
            "assigned_user_id": fixture.USER_PATIENT_ID,
        },
    ).status_code == 422
    assert patient_client.post(
        f"/api/tasks/{created['task_id']}/transition",
        json={"expected_status": "reported_done", "status": "cancelled"},
    ).status_code == 403


def test_patient_list_filters_internal_and_unassigned_tasks(patient_client):
    response = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/tasks")
    assert response.status_code == 200
    ids = {task["task_id"] for task in response.json()}
    assert fixture.TASK_BLOOD_TEST in ids
    assert all(task["patient_visible"] is True for task in response.json())
