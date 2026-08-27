from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient

from app.main import app
from app.security import reset_rate_limits
from seed import fixture


ORIGIN = "https://127.0.0.1:8443"
PASSWORD = "D5-journey-password!"


def _client() -> TestClient:
    return TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN})


def _login(client: TestClient, email: str, password: str):
    return client.post("/api/auth/login", json={"email": email, "password": password})


def _token(invite_link: str) -> str:
    return parse_qs(urlparse(invite_link).query)["token"][0]


def test_new_clinician_account_completes_full_journey_in_one_cookie_session(monkeypatch):
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)
    monkeypatch.setenv("NANTINGALE_SECURITY_MODE", "strict")
    monkeypatch.setenv("NANTINGALE_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("NANTINGALE_SECURE_COOKIES", "true")
    monkeypatch.setenv("NANTINGALE_AUTH_RATE_LIMIT", "20")
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "deepseek")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    reset_rate_limits()

    with _client() as admin, _client() as clinician:
        assert _login(
            admin,
            fixture.DEMO_EMAILS[fixture.USER_ADMIN_ID],
            fixture.DEMO_PASSWORD,
        ).status_code == 200
        invite = admin.post(
            "/api/auth/invites",
            json={"email": "d5-clinician@demo.clinic", "role": "clinician"},
        )
        assert invite.status_code == 200, invite.text

        registered = clinician.post(
            "/api/auth/register",
            json={
                "token": _token(invite.json()["invite_link"]),
                "password": PASSWORD,
                "name": "Dr. D5 Journey",
            },
        )
        assert registered.status_code == 201, registered.text
        assert registered.json()["role"] == "clinician"
        clinician_user_id = registered.json()["user_id"]

        login = _login(clinician, "d5-clinician@demo.clinic", PASSWORD)
        assert login.status_code == 200, login.text
        assert login.json()["role"] == "clinician"
        session_cookie = clinician.cookies.get("nantingale_session")
        assert session_cookie
        directory = clinician.get("/api/patients")
        assert directory.status_code == 200
        assert fixture.PATIENT_ID in {row["patient_id"] for row in directory.json()}
        glance = clinician.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
        assert glance.status_code == 200

        raw = "CONSULTANT: What changed?\nPATIENT: The headache is worse this week."
        preview = clinician.post(
            "/api/transcripts/normalize", json={"raw_text": raw}
        )
        assert preview.status_code == 200
        assert preview.json()["outcome"] == "NEEDS_REVIEW"
        assert preview.json()["segments"][0]["speaker_candidate"] is None

        confirmed = clinician.post(
            f"/api/patients/{fixture.PATIENT_ID}/doctor-consults",
            json={
                "consult_id": "d5-new-clinician-journey",
                "ingestion_key": "d5-new-clinician-journey-submit",
                "started_at": "2026-08-27T14:00:00",
                "ended_at": None,
                "content": {
                    "segments": [
                        {"index": 0, "speaker": "doctor", "text": "What changed?"},
                        {
                            "index": 1,
                            "speaker": "patient",
                            "text": "The headache is worse this week.",
                        },
                    ]
                },
            },
        )
        assert confirmed.status_code == 200, confirmed.text
        result = confirmed.json()
        assert result["ai_summary_artifact_id"] != result["source_artifact_id"]
        assert result["highlight_ids"]

        provenance = clinician.get(
            f"/api/highlights/{result['highlight_ids'][0]}/provenance"
        )
        assert provenance.status_code == 200, provenance.text
        assert provenance.json()["source_artifact"]["artifact_id"] == result[
            "source_artifact_id"
        ]
        assert provenance.json()["quote"] == "The headache is worse this week."

        event_id = result["event"]["event_id"]
        note = clinician.post(
            f"/api/events/{event_id}/notes",
            json={
                "artifact_type": "clinician_note",
                "content": {
                    "assessment": "Headache frequency has worsened.",
                    "plan": "Continue monitoring and complete follow-up.",
                },
            },
        )
        assert note.status_code == 200, note.text
        assert note.json()["author_id"] == clinician_user_id

        task = clinician.post(
            f"/api/events/{event_id}/tasks",
            json={
                "title": "Submit symptom check-in",
                "description": "Review symptom pattern before follow-up.",
                "assigned_role": "patient",
                "assigned_user_id": fixture.USER_PATIENT_ID,
                "patient_visible": True,
                "due_at": "2026-08-28T12:00:00",
                "source_artifact_id": result["source_artifact_id"],
                "source_span": provenance.json()["span"],
            },
        )
        assert task.status_code == 200, task.text
        assert task.json()["created_by"] == clinician_user_id

        instruction = clinician.post(
            f"/api/events/{event_id}/notes",
            json={
                "artifact_type": "patient_instruction",
                "content": {
                    "instruction": "Record headache changes before your follow-up.",
                    "follow_up": "Clinic review on 28 August.",
                },
            },
        )
        assert instruction.status_code == 200, instruction.text
        assert instruction.json()["author_id"] == clinician_user_id
        assert clinician.cookies.get("nantingale_session") == session_cookie

        assert clinician.post("/api/auth/logout").status_code == 200
        assert clinician.get(f"/api/events/{event_id}/artifacts").status_code == 401
