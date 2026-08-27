from __future__ import annotations

from sqlalchemy import select

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


def test_new_task_with_matching_span_gets_own_highlight_and_never_steals_owned(
    clinician_client, patient_client, db_session
):
    # Terminate the seed blood-test task so its owned highlight clears.
    patient_client.post(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
        json={"expected_status": "open", "status": "reported_done"},
    )
    clinician_client.post(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/transition",
        json={"expected_status": "reported_done", "status": "completed"},
    )
    db_session.expire_all()
    owned = db_session.get(Highlight, "hl_blood_test_pending")
    assert owned.feature_flags["unresolved_task"] is False

    # A NEW task with the same exact provenance must not reactivate or steal
    # the highlight owned by the completed task: the mapping is explicit 1:1.
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
    task_id = created.json()["task_id"]

    db_session.expire_all()
    owned = db_session.get(Highlight, "hl_blood_test_pending")
    assert owned.feature_flags["unresolved_task"] is False
    assert owned.task_id == fixture.TASK_BLOOD_TEST  # still owned by the seed task

    own = db_session.scalars(
        select(Highlight).where(Highlight.task_id == task_id)
    ).all()
    assert len(own) == 1
    assert own[0].feature_flags["unresolved_task"] is True
    assert own[0].source_artifact_id == fixture.ART_DOC_TRANSCRIPT
    assert own[0].source_span == {"kind": "segment", "index": 16, "offset": [0, 61]}


def test_event_only_task_never_flags_unrelated_highlights_in_same_event(
    clinician_client, db_session
):
    review_hl = db_session.get(Highlight, "hl_blood_test_review")
    assert review_hl.feature_flags["unresolved_task"] is False

    created = clinician_client.post(
        f"/api/events/{fixture.EVT_REVIEW_0826}/tasks",
        json={
            "title": "Call lab about result",
            "description": "internal",
            "assigned_role": "staff",
            "assigned_user_id": None,
            "patient_visible": False,
            "due_at": None,
            "source_artifact_id": None,
            "source_span": None,
        },
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    db_session.expire_all()
    # The unrelated task-type highlight in the same Event stays untouched.
    review_hl = db_session.get(Highlight, "hl_blood_test_review")
    assert review_hl.feature_flags["unresolved_task"] is False
    # The event-only task gets its own dedicated Glance row.
    own = db_session.scalars(
        select(Highlight).where(Highlight.task_id == task_id)
    ).all()
    assert len(own) == 1
    assert own[0].feature_flags["unresolved_task"] is True
    assert own[0].source_artifact_id is None
    assert own[0].source_span is None


def test_event_only_task_enters_glance_without_any_existing_highlight(
    clinician_client, db_session
):
    from datetime import datetime

    from app.models import Event

    db_session.add(
        Event(
            event_id="evt_ben_task_origin",
            patient_id=fixture.PATIENT_B_ID,
            clinic_id=fixture.CLINIC_ID,
            event_type="doctor_consult",
            started_at=datetime(2026, 8, 27, 9, 0),
            ended_at=None,
            created_at=datetime(2026, 8, 27, 9, 5),
        )
    )
    db_session.commit()

    created = clinician_client.post(
        "/api/events/evt_ben_task_origin/tasks",
        json={
            "title": "Attend physiotherapy",
            "description": "internal",
            "assigned_role": "patient",
            "assigned_user_id": None,
            "patient_visible": True,
            "due_at": None,
            "source_artifact_id": None,
            "source_span": None,
        },
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]

    db_session.expire_all()
    hl = db_session.scalar(
        select(Highlight).where(Highlight.task_id == task_id)
    )
    assert hl is not None
    assert hl.feature_flags["unresolved_task"] is True

    glance = clinician_client.get(f"/api/patients/{fixture.PATIENT_B_ID}/glance")
    assert glance.status_code == 200
    assert hl.highlight_id in {h["highlight_id"] for h in glance.json()["highlights"]}
    assert all(h["task_id"] == task_id for h in glance.json()["highlights"] if h["highlight_id"] == hl.highlight_id)


def test_cancel_deterministically_clears_own_highlight(clinician_client, db_session):
    created = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json={
            "title": "Pick up medication refill",
            "description": "internal",
            "assigned_role": "patient",
            "assigned_user_id": fixture.USER_PATIENT_ID,
            "patient_visible": True,
            "due_at": None,
            "source_artifact_id": None,
            "source_span": None,
        },
    )
    assert created.status_code == 200
    task_id = created.json()["task_id"]
    db_session.expire_all()
    before = db_session.scalar(
        select(Highlight).where(Highlight.task_id == task_id)
    )
    assert before.feature_flags["unresolved_task"] is True
    before_score = before.importance_score

    cancelled = clinician_client.post(
        f"/api/tasks/{task_id}/transition",
        json={"expected_status": "open", "status": "cancelled"},
    )
    assert cancelled.status_code == 200

    db_session.expire_all()
    after = db_session.scalar(select(Highlight).where(Highlight.task_id == task_id))
    assert after.feature_flags["unresolved_task"] is False
    assert after.importance_score == before_score - WEIGHTS["unresolved_task"]


def test_exact_matching_unowned_highlight_is_adopted_not_duplicated(
    clinician_client, db_session
):
    from datetime import datetime

    now = datetime.now()
    db_session.add(
        Highlight(
            highlight_id="hl_unowned_task",
            patient_id=fixture.PATIENT_ID,
            event_id=fixture.EVT_DOC_0821,
            artifact_id=fixture.ART_DOC_TRANSCRIPT,
            source_artifact_id=fixture.ART_DOC_TRANSCRIPT,
            source_span={"kind": "segment", "index": 16, "offset": [0, 61]},
            task_id=None,
            text="Blood test ordered - pending",
            risk_reason="AI-derived pending item",
            feature_flags={
                "recency": False,
                "explicit_risk": False,
                "unresolved_task": False,
                "clinician_confirmed": False,
                "symptom_change": False,
                "repeated_mentions": False,
            },
            importance_score=0,
            status="suggested",
            status_history=[],
            created_at=now,
            updated_at=now,
            entity_type="task",
            entity_key="task:blood test",
            assertion_value="pending",
            conflict_with_artifact_id=None,
            review_status=None,
        )
    )
    db_session.commit()

    created = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json={
            "title": "Adopt the AI pending item",
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
    task_id = created.json()["task_id"]

    db_session.expire_all()
    adopted = db_session.get(Highlight, "hl_unowned_task")
    assert adopted.task_id == task_id
    assert adopted.feature_flags["unresolved_task"] is True
    own = db_session.scalars(
        select(Highlight).where(Highlight.task_id == task_id)
    ).all()
    assert len(own) == 1  # adopted, not duplicated
