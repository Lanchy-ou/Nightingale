"""The work inbox is a scoped projection of existing actionable tasks."""
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Task
from seed import fixture as f

URL = "/api/work-inbox"


def test_inbox_requires_clinical_identity(client, patient_client, admin_client):
    assert client.get(URL).status_code == 401
    assert patient_client.get(URL).status_code == 403
    assert admin_client.get(URL).status_code == 403


def test_role_queue_and_verification_projection(clinician_client, staff_client, db_session):
    patient_task = db_session.get(Task, f.TASK_BLOOD_TEST)
    patient_task.status = "reported_done"
    db_session.commit()
    for client, role in [(clinician_client, "clinician"), (staff_client, "staff")]:
        response = client.get(URL)
        assert response.status_code == 200, response.text
        rows = response.json()["items"]
        assert f.TASK_BLOOD_TEST in {row["task_id"] for row in rows}
        assert all(row["actionable"] for row in rows)
        assert all(row["assigned_role"] == role or (row["assigned_role"] == "patient" and row["status"] == "reported_done") for row in rows)
        assert all(set(row) == {"task_id", "patient_id", "patient_name", "event_id", "title", "task_kind", "status", "assigned_role", "assigned_user_id", "due_at", "overdue", "actionable", "has_exact_source"} for row in rows)


def test_clinic_queue_excludes_finished_and_other_clinic(clinician_client, db_session):
    finished = db_session.get(Task, f.TASK_BLOOD_TEST)
    finished.status = "completed"
    db_session.commit()
    result = clinician_client.get(URL + "?view=clinic&limit=100").json()
    ids = {row["task_id"] for row in result["items"]}
    expected = {task.task_id for task in db_session.scalars(select(Task).where(Task.clinic_id == f.CLINIC_ID, Task.status.in_(["open", "in_progress", "reported_done"])))}
    assert ids == expected
    assert f.TASK_BLOOD_TEST not in ids
    with TestClient(app, headers={"X-User-Id": f.USER_CLINICIAN_B_ID}) as other:
        other_rows = other.get(URL + "?view=clinic").json()["items"]
        assert not ids.intersection(row["task_id"] for row in other_rows)


def test_named_assignment_is_excluded_from_colleagues_mine(clinician_client, db_session):
    task = db_session.get(Task, f.TASK_MAYA_LAB_REVIEW)
    task.assigned_role = "clinician"
    task.assigned_user_id = f.USER_CLINICIAN_2_ID
    task.status = "open"
    db_session.commit()
    assert task.task_id not in {row["task_id"] for row in clinician_client.get(URL).json()["items"]}
    clinic = clinician_client.get(URL + "?view=clinic").json()["items"]
    assert next(row for row in clinic if row["task_id"] == task.task_id)["actionable"] is False


def test_pagination_is_stable_and_bounded(clinician_client):
    all_rows = clinician_client.get(URL + "?view=clinic&limit=100").json()["items"]
    pages = [clinician_client.get(URL + f"?view=clinic&limit=1&offset={index}").json()["items"][0] for index in range(len(all_rows))]
    assert [row["task_id"] for row in pages] == [row["task_id"] for row in all_rows]
    for params in ["limit=101", "offset=-1", "view=unknown"]:
        assert clinician_client.get(URL + "?" + params).status_code == 422


def test_priority_review_precedes_verification_and_overdue_work(clinician_client, db_session):
    review = db_session.get(Task, f.TASK_MAYA_LAB_REVIEW)
    review.task_kind = "clinician_priority_review"
    review.assigned_role = "clinician"
    review.assigned_user_id = None
    review.status = "open"
    verification = db_session.get(Task, f.TASK_MAYA_BP_LOG)
    verification.status = "reported_done"
    db_session.commit()
    rows = clinician_client.get(URL + "?view=clinic").json()["items"]
    assert [row["task_id"] for row in rows[:2]] == [review.task_id, verification.task_id]


def test_unsubmitted_checkin_is_hidden_from_inbox_and_drafts(clinician_client, db_session):
    from datetime import datetime
    from app.models import PatientCheckInSession
    now = datetime(2026, 9, 5)
    db_session.add(PatientCheckInSession(session_id="hidden-test", event_id=f.EVT_DOC_0821,
        raw_artifact_id=f.ART_DOC_TRANSCRIPT, patient_id=f.PATIENT_ID, clinic_id=f.CLINIC_ID,
        patient_user_id=f.USER_PATIENT_ID, status="active", started_at=now, created_at=now, updated_at=now))
    db_session.commit()
    rows = clinician_client.get(URL + "?view=clinic").json()["items"]
    assert all(row["event_id"] != f.EVT_DOC_0821 for row in rows)
    draft_url = f"/api/events/{f.EVT_DOC_0821}/note-drafts/new"
    assert clinician_client.get(draft_url).status_code == 404
    assert clinician_client.put(draft_url, json={"expected_revision": 0, "base_version": 0, "fields": {"body": "private"}}).status_code == 404
