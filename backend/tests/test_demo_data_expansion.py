"""Purpose-built synthetic demo expansion: API-level acceptance."""
from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from seed import fixture


def test_primary_clinic_directory_has_sparse_task_and_dense_patients(clinician_client):
    response = clinician_client.get("/api/patients")
    assert response.status_code == 200
    rows = response.json()
    assert [row["name"] for row in rows] == [
        fixture.PATIENT_NAME,
        fixture.PATIENT_B_NAME,
        fixture.PATIENT_DENSE_NAME,
        fixture.PATIENT_TASK_NAME,
    ]


def test_maya_glance_tasks_patient_projection_and_comments(clinician_client):
    glance = clinician_client.get(f"/api/patients/{fixture.PATIENT_TASK_ID}/glance")
    assert glance.status_code == 200
    assert {item["highlight_id"] for item in glance.json()["highlights"]} == {
        "hl_maya_lightheaded",
    }
    comments = clinician_client.get(f"/api/events/{fixture.EVT_MAYA_DOCTOR}/comments")
    assert comments.status_code == 200
    assert {item["comment_id"] for item in comments.json()} == {
        "comment_maya_staff_handoff",
        "comment_maya_clinician_reply",
    }

    with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_TASK_ID}) as patient:
        view = patient.get(f"/api/patients/{fixture.PATIENT_TASK_ID}/patient-view")
    assert view.status_code == 200
    body = view.json()
    assert body["today"]["instruction"]["artifact_id"] == fixture.ART_MAYA_REVIEW_INSTRUCTION
    assert [task["task_id"] for task in body["care_plan"]["reported_done"]] == [
        fixture.TASK_MAYA_BP_LOG
    ]
    assert fixture.TASK_MAYA_LAB_REVIEW not in str(body)


def test_daniel_dense_history_and_open_action(clinician_client):
    events = clinician_client.get(f"/api/patients/{fixture.PATIENT_DENSE_ID}/events")
    assert events.status_code == 200
    rows = events.json()
    assert len(rows) == 12
    assert [row["started_at"] for row in rows] == sorted(row["started_at"] for row in rows)
    latest_doctor = next(row for row in rows if row["event_id"] == fixture.EVT_DANIEL_LATEST_DOCTOR)
    assert latest_doctor["artifact_count"] == 4

    glance = clinician_client.get(f"/api/patients/{fixture.PATIENT_DENSE_ID}/glance")
    assert glance.status_code == 200
    assert {item["highlight_id"] for item in glance.json()["highlights"]} == {
        "hl_daniel_walking_discomfort",
    }


def test_other_clinic_directory_and_cross_clinic_404(clinician_client):
    with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}) as other:
        directory = other.get("/api/patients")
        own = other.get(f"/api/patients/{fixture.PATIENT_OTHER_ID}/events")
    assert directory.status_code == 200
    assert [row["patient_id"] for row in directory.json()] == [fixture.PATIENT_OTHER_ID]
    assert own.status_code == 200 and len(own.json()) == 3

    cross = clinician_client.get(f"/api/patients/{fixture.PATIENT_OTHER_ID}")
    absent = clinician_client.get("/api/patients/pat_absent")
    assert cross.status_code == absent.status_code == 404
    assert cross.json() == absent.json()
