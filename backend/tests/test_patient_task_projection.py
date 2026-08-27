from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.models import Task
from seed import fixture


PATIENT_TASK_KEYS = {
    "task_id",
    "title",
    "status",
    "due_at",
    "updated_at",
    "reported_done_at",
    "completed_at",
    "patient_visible",
}


def test_patient_task_response_exact_allowlist_and_sentinel_scan(patient_client, db_session):
    task = db_session.get(Task, fixture.TASK_BLOOD_TEST)
    task.description = "INTERNAL_DESCRIPTION_SENTINEL"
    db_session.commit()

    response = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/tasks")
    assert response.status_code == 200
    raw = json.dumps(response.json())
    assert "INTERNAL_DESCRIPTION_SENTINEL" not in raw
    for item in response.json():
        assert set(item) == PATIENT_TASK_KEYS
    for forbidden in (
        "description", "assigned_role", "assigned_user_id", "created_by",
        "source_artifact_id", "source_span", "audit", "risk_reason",
    ):
        assert forbidden not in raw


def test_patient_aggregate_has_exact_four_product_sections(patient_client):
    response = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "patient_id", "display_name", "today", "care_plan", "check_in", "visit_summaries"
    }
    assert set(body["today"]) == {"instruction", "tasks", "next_follow_up"}
    assert set(body["care_plan"]) == {"open", "in_progress", "reported_done", "completed"}
    assert set(body["check_in"]) == {"sessions"}
    assert set(body["visit_summaries"]) == {"summaries"}
    for group in body["care_plan"].values():
        for task in group:
            assert set(task) == PATIENT_TASK_KEYS


def test_patient_aggregate_never_infers_action_from_clinician_note(patient_client, db_session):
    from app.models import Artifact
    note = db_session.get(Artifact, fixture.ART_REVIEW_NOTE)
    note.content = {**note.content, "plan": "CLINICIAN_ACTION_SENTINEL do this now"}
    db_session.commit()
    raw = json.dumps(
        patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/patient-view").json()
    )
    assert "CLINICIAN_ACTION_SENTINEL" not in raw


def test_patient_frontend_uses_safe_aggregate_and_resets_drafts_on_identity_boundary():
    root = Path(__file__).parents[2] / "frontend" / "src"
    patient_page = (root / "pages" / "PatientViewPage.tsx").read_text(encoding="utf-8")
    api_source = (root / "api.ts").read_text(encoding="utf-8")
    assert "getPatientView" in patient_page
    for clinical_call in ("getComments", "getAudit", "getArtifacts", "getGlance", "getTasks"):
        assert f"api.{clinical_call}" not in patient_page
    assert "key={productKey}" in (root / "App.tsx").read_text(encoding="utf-8")
    assert "roleKey" in patient_page and "setMessage('')" in patient_page
    assert "/patient-view" in api_source
