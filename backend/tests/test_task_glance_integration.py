from __future__ import annotations

from app.highlights import WEIGHTS
from app.models import Highlight
from seed import fixture


def test_seed_unresolved_task_is_structural_not_fixed_false(db_session):
    highlight = db_session.get(Highlight, "hl_blood_test_pending")
    assert highlight.feature_flags["unresolved_task"] is True


def test_terminal_transition_removes_unresolved_weight_deterministically(
    clinician_client, patient_client, db_session
):
    before = db_session.get(Highlight, "hl_blood_test_pending")
    before_score = before.importance_score
    patient_client.post(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
        json={"expected_status": "open", "status": "reported_done"},
    )
    completed = clinician_client.post(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
        json={"expected_status": "reported_done", "status": "completed"},
    )
    assert completed.status_code == 200
    db_session.expire_all()
    after = db_session.get(Highlight, "hl_blood_test_pending")
    assert after.feature_flags["unresolved_task"] is False
    assert after.importance_score == before_score - WEIGHTS["unresolved_task"]


def test_new_unresolved_task_updates_existing_task_highlight_write_path(
    clinician_client, patient_client, db_session
):
    patient_client.post(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
        json={"expected_status": "open", "status": "reported_done"},
    )
    clinician_client.post(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
        json={"expected_status": "reported_done", "status": "completed"},
    )
    db_session.expire_all()
    assert db_session.get(Highlight, "hl_blood_test_pending").feature_flags["unresolved_task"] is False

    created = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json={
            "title": "Repeat blood test follow-up",
            "description": "internal",
            "assigned_role": "patient",
            "assigned_user_id": fixture.USER_PATIENT_ID,
            "patient_visible": True,
            "due_at": None,
            "source_artifact_id": fixture.ART_DOC_TRANSCRIPT,
            "source_span": {"kind": "segment", "index": 16, "offset": [0, 61]},
        },
    )
    assert created.status_code == 200
    db_session.expire_all()
    assert db_session.get(Highlight, "hl_blood_test_pending").feature_flags["unresolved_task"] is True
