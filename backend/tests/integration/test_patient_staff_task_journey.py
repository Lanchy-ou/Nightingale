from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.security import reset_rate_limits
from seed import fixture


ORIGIN = "https://127.0.0.1:8443"
PASSWORD = "D5-patient-journey-password!"


def _client() -> TestClient:
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def _login(client: TestClient, email: str, password: str):
    response = client.post(
        "/api/auth/login", json={"email": email, "password": password}
    )
    assert response.status_code == 200, response.text
    return response


def test_patient_reports_done_staff_verifies_comments_and_glance_updates(monkeypatch):
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)
    monkeypatch.setenv("NANTINGALE_SECURITY_MODE", "strict")
    monkeypatch.setenv("NANTINGALE_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("NANTINGALE_SECURE_COOKIES", "true")
    monkeypatch.setenv("NANTINGALE_AUTH_RATE_LIMIT", "30")
    reset_rate_limits()

    with _client() as admin, _client() as clinician, _client() as patient, _client() as staff:
        _login(admin, fixture.DEMO_EMAILS[fixture.USER_ADMIN_ID], fixture.DEMO_PASSWORD)
        patient_invite = admin.post(
            "/api/auth/invites",
            json={
                "email": "d5-patient@demo.clinic",
                "role": "patient",
                "patient_id": fixture.PATIENT_ID,
            },
        )
        assert patient_invite.status_code == 200, patient_invite.text
        token = parse_qs(
            urlparse(patient_invite.json()["invite_link"]).query
        )["token"][0]
        registered = patient.post(
            "/api/auth/register", json={"token": token, "password": PASSWORD}
        )
        assert registered.status_code == 201, registered.text
        patient_user_id = registered.json()["user_id"]
        _login(patient, "d5-patient@demo.clinic", PASSWORD)

        _login(
            clinician,
            fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            fixture.DEMO_PASSWORD,
        )
        task = clinician.post(
            f"/api/events/{fixture.EVT_REVIEW_0826}/tasks",
            json={
                "title": "Send evening symptom check-in",
                "description": "Clinic reviews the check-in after patient submission.",
                "assigned_role": "patient",
                "assigned_user_id": patient_user_id,
                "patient_visible": True,
                "due_at": "2026-08-28T18:00:00",
                "source_artifact_id": None,
                "source_span": None,
            },
        )
        assert task.status_code == 200, task.text
        task_id = task.json()["task_id"]

        today = patient.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view")
        assert today.status_code == 200
        assert task_id in {row["task_id"] for row in today.json()["today"]["tasks"]}
        started = patient.post(
            f"/api/tasks/{task_id}/transition",
            json={"expected_status": "open", "status": "in_progress"},
        )
        assert started.status_code == 200
        reported = patient.post(
            f"/api/tasks/{task_id}/transition",
            json={"expected_status": "in_progress", "status": "reported_done"},
        )
        assert reported.status_code == 200
        assert reported.json()["status"] == "reported_done"

        check_in = patient.post(
            f"/api/patients/{fixture.PATIENT_ID}/sessions",
            json={
                "session_id": "d5-evening-check-in",
                "event_type": "patient_followup",
                "started_at": "2026-08-27T18:00:00",
                "content": {
                    "messages": [
                        {
                            "id": "m1",
                            "speaker": "patient",
                            "text": "The headache is better this evening.",
                        }
                    ]
                },
            },
        )
        assert check_in.status_code == 200, check_in.text
        refreshed = patient.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view")
        assert refreshed.status_code == 200
        assert refreshed.json()["visit_summaries"]["summaries"]

        _login(staff, fixture.DEMO_EMAILS[fixture.USER_STAFF_ID], fixture.DEMO_PASSWORD)
        queue = staff.get(f"/api/patients/{fixture.PATIENT_ID}/tasks")
        assert queue.status_code == 200
        queued = next(row for row in queue.json() if row["task_id"] == task_id)
        assert queued["status"] == "reported_done"
        verified = staff.post(
            f"/api/tasks/{task_id}/transition",
            json={"expected_status": "reported_done", "status": "completed"},
        )
        assert verified.status_code == 200, verified.text
        assert verified.json()["completed_by"] == fixture.USER_STAFF_ID

        comment = staff.post(
            "/api/comments",
            json={
                "anchor_type": "event",
                "anchor_id": fixture.EVT_REVIEW_0826,
                "body": "Patient check-in verified; clinician review requested.",
                "mentions": [fixture.USER_CLINICIAN_ID],
            },
        )
        assert comment.status_code == 200, comment.text

        glance = staff.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
        assert glance.status_code == 200
        linked = [row for row in glance.json()["highlights"] if row["task_id"] == task_id]
        assert all(row["feature_flags"]["unresolved_task"] is False for row in linked)

        assert patient.post("/api/auth/logout").status_code == 200
        assert staff.post("/api/auth/logout").status_code == 200
        assert patient.get(
            f"/api/patients/{fixture.PATIENT_ID}/patient-view"
        ).status_code == 401
        assert staff.get(f"/api/patients/{fixture.PATIENT_ID}/tasks").status_code == 401
