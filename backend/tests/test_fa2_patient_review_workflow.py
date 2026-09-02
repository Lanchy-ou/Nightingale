from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select

from app.attention_items import build_attention_items
from app.models import GlanceProjection, LearningSignal, PatientReviewItem, Task, WorkflowLink
from app.patient_review import materialize_due_escalations, review_window_minutes
from seed import fixture


def _submit(patient_client, session_id: str, text: str):
    started = patient_client.post(
        f"/api/patients/{fixture.PATIENT_ID}/check-ins", json={"session_id": session_id}
    )
    assert started.status_code == 200, started.text
    for index, (intent, message) in enumerate(
        (("answer", text), ("no_more", "")), start=1
    ):
        response = patient_client.post(
            f"/api/check-ins/{session_id}/messages",
            json={
                "message_id": f"{session_id}-msg-{index}",
                "intent": intent,
                "text": message,
            },
        )
        assert response.status_code == 200, response.text
        if response.json()["status"] == "awaiting_confirmation":
            break
    submitted = patient_client.post(
        f"/api/check-ins/{session_id}/submit",
        json={"expected_status": "awaiting_confirmation"},
    )
    assert submitted.status_code == 200, submitted.text
    return submitted


def _workflow_tasks(db_session, event_id: str):
    return db_session.scalars(
        select(Task).where(Task.event_id == event_id).order_by(Task.task_kind)
    ).all()


def _review_all_candidates(staff_client, task_id: str, *, outcome: str = "verified"):
    context = staff_client.get(f"/api/tasks/{task_id}/review-context")
    assert context.status_code == 200, context.text
    items = context.json()["candidates"]
    assert items
    for item in items:
        response = staff_client.post(
            f"/api/tasks/{task_id}/review-items/{item['review_item_id']}",
            json={
                "expected_outcome": "pending",
                "outcome": outcome,
                "correction_artifact_id": None,
            },
        )
        assert response.status_code == 200, response.text
    return items


def test_every_submitted_checkin_creates_one_staff_review_task_and_is_idempotent(
    patient_client, staff_client, clinician_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES", "5")
    submitted = _submit(
        patient_client,
        "fa2-routine-review-001",
        "Nausea is still present but I have no urgent concern.",
    )
    event_id = submitted.json()["event_id"]
    db_session.expire_all()
    tasks = _workflow_tasks(db_session, event_id)
    assert [(task.task_kind, task.assigned_role) for task in tasks] == [
        ("patient_report_review", "staff")
    ]
    task = tasks[0]
    assert task.creation_method == "system_routed"
    assert task.attention_class == "routine"
    assert task.verification_outcome == "pending"
    assert task.due_at == task.escalate_at
    assert task.due_at - task.created_at == timedelta(minutes=5)

    staff_glance = staff_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").json()
    clinician_glance = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").json()
    assert task.task_id in {item["task_id"] for item in staff_glance["highlights"]}
    assert task.task_id not in {item["task_id"] for item in clinician_glance["highlights"]}

    retried = patient_client.post(
        "/api/check-ins/fa2-routine-review-001/submit",
        json={"expected_status": "submitted"},
    )
    assert retried.status_code == 200
    db_session.expire_all()
    assert len(_workflow_tasks(db_session, event_id)) == 1
    assert db_session.query(PatientReviewItem).filter_by(workflow_id=task.workflow_id).count() >= 1


def test_priority_patient_report_routes_to_both_roles_and_records_two_axis_label(
    patient_client, staff_client, clinician_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    submitted = _submit(
        patient_client,
        "fa2-priority-review-001",
        "My headache is getting much worse and the pain is severe.",
    )
    event_id = submitted.json()["event_id"]
    db_session.expire_all()
    tasks = _workflow_tasks(db_session, event_id)
    assert {(task.task_kind, task.assigned_role) for task in tasks} == {
        ("patient_report_review", "staff"),
        ("clinician_priority_review", "clinician"),
    }
    staff_task = next(task for task in tasks if task.assigned_role == "staff")
    clinician_task = next(task for task in tasks if task.assigned_role == "clinician")
    assert staff_task.routing_metadata["reason_codes"] == [
        "patient_explicit_severe_intensity",
        "patient_explicit_worsening",
    ]
    role_items = build_attention_items(
        db_session,
        patient_id=fixture.PATIENT_ID,
        viewer_role="clinician",
        as_of=datetime.now(),
    )
    workflow_items = [item for item in role_items if item.workflow_id == staff_task.workflow_id]
    assert len(workflow_items) >= 2
    assert {item.workflow_group_key for item in workflow_items} == {
        f"workflow:{staff_task.workflow_id}"
    }
    assert len({item.independence_key for item in workflow_items}) == len(workflow_items)
    assert all(
        item.source_binding_status == "not_applicable"
        for item in workflow_items
        if item.source_kind == "task" and item.exact_span_available is False
    )

    _review_all_candidates(staff_client, staff_task.task_id)

    verified = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/verify-patient-report",
        json={
            "expected_status": "open",
            "verification_outcome": "verified",
            "next_route": "clinician_review",
        },
    )
    assert verified.status_code == 200, verified.text
    db_session.expire_all()
    assert db_session.get(Task, staff_task.task_id).status == "completed"
    assert db_session.get(Task, clinician_task.task_id).verification_outcome == "verified"
    clinician_item = next(
        item
        for item in build_attention_items(
            db_session,
            patient_id=fixture.PATIENT_ID,
            viewer_role="clinician",
            as_of=datetime.now(),
        )
        if item.source_id == clinician_task.task_id
    )
    assert clinician_item.upstream_verification_known is True
    assert clinician_item.upstream_verification_outcome == "verified"
    assert "verification_updates" in clinician_item.inbound_relation_types

    invalid = clinician_client.post(
        f"/api/tasks/{clinician_task.task_id}/complete-clinician-review",
        json={
            "expected_status": "open",
            "review_outcome": "no_action",
            "time_sensitivity": "time_sensitive",
        },
    )
    assert invalid.status_code == 422
    missing_follow_up = clinician_client.post(
        f"/api/tasks/{clinician_task.task_id}/complete-clinician-review",
        json={
            "expected_status": "open",
            "review_outcome": "action_required",
            "time_sensitivity": "time_sensitive",
            "follow_up_task_id": None,
        },
    )
    assert missing_follow_up.status_code == 422
    follow_up = clinician_client.post(
        f"/api/events/{event_id}/tasks",
        json={
            "title": "Call patient about worsening headache",
            "description": "Nurse to confirm current symptoms and relay the result.",
            "assigned_role": "staff",
            "assigned_user_id": None,
            "patient_visible": False,
            "due_at": "2026-09-02T18:00:00",
            "source_artifact_id": None,
            "source_span": None,
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    completed = clinician_client.post(
        f"/api/tasks/{clinician_task.task_id}/complete-clinician-review",
        json={
            "expected_status": "open",
            "review_outcome": "action_required",
            "time_sensitivity": "time_sensitive",
            "follow_up_task_id": follow_up.json()["task_id"],
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["routing_metadata"]["attention_label_grade"] == 3
    assert completed.json()["routing_metadata"]["attention_label_version"] == "attention-label-v1"
    assert completed.json()["follow_up_task_id"] == follow_up.json()["task_id"]
    db_session.expire_all()
    linked_follow_up = db_session.get(Task, follow_up.json()["task_id"])
    assert linked_follow_up.workflow_id == clinician_task.workflow_id
    assert db_session.scalar(
        select(WorkflowLink).where(
            WorkflowLink.workflow_id == clinician_task.workflow_id,
            WorkflowLink.from_id == clinician_task.task_id,
            WorkflowLink.relation_type == "requires_action",
            WorkflowLink.to_id == linked_follow_up.task_id,
        )
    ) is not None
    outcome = db_session.scalar(
        select(LearningSignal).where(
            LearningSignal.signal_type == "outcome_label",
            LearningSignal.actor_id == fixture.USER_CLINICIAN_ID,
        )
    )
    assert outcome is not None
    assert outcome.signal_value == 3
    assert outcome.eligible_for_shadow is False
    glance = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance").json()
    assert clinician_task.task_id not in {item["task_id"] for item in glance["highlights"]}


def test_candidate_review_is_itemized_and_corrected_requires_staff_note(
    patient_client, staff_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    submitted = _submit(
        patient_client,
        "fa2-itemized-review-001",
        "My headache is getting much worse and the pain is severe.",
    )
    event_id = submitted.json()["event_id"]
    db_session.expire_all()
    staff_task = next(
        task for task in _workflow_tasks(db_session, event_id) if task.assigned_role == "staff"
    )
    context = staff_client.get(f"/api/tasks/{staff_task.task_id}/review-context")
    assert context.status_code == 200, context.text
    patient_denied = patient_client.get(f"/api/tasks/{staff_task.task_id}/review-context")
    assert patient_denied.status_code == 403
    candidates = context.json()["candidates"]
    assert candidates
    assert all(item["review_outcome"] == "pending" for item in candidates)

    premature = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/verify-patient-report",
        json={
            "expected_status": "open",
            "verification_outcome": "verified",
            "next_route": "clinician_review",
        },
    )
    assert premature.status_code == 422

    first = candidates[0]
    no_note = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/review-items/{first['review_item_id']}",
        json={
            "expected_outcome": "pending",
            "outcome": "corrected",
            "correction_artifact_id": None,
        },
    )
    assert no_note.status_code == 422
    note = staff_client.post(
        f"/api/events/{event_id}/notes",
        json={
            "artifact_type": "staff_note",
            "content": {"note": "Patient clarified that the severe pain referred to yesterday, not today."},
        },
    )
    assert note.status_code == 200, note.text
    corrected = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/review-items/{first['review_item_id']}",
        json={
            "expected_outcome": "pending",
            "outcome": "corrected",
            "correction_artifact_id": note.json()["artifact_id"],
        },
    )
    assert corrected.status_code == 200, corrected.text
    for item in candidates[1:]:
        verified = staff_client.post(
            f"/api/tasks/{staff_task.task_id}/review-items/{item['review_item_id']}",
            json={
                "expected_outcome": "pending",
                "outcome": "verified",
                "correction_artifact_id": None,
            },
        )
        assert verified.status_code == 200, verified.text

    wrong_aggregate = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/verify-patient-report",
        json={
            "expected_status": "open",
            "verification_outcome": "verified",
            "next_route": "clinician_review",
        },
    )
    assert wrong_aggregate.status_code == 422
    closed = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/verify-patient-report",
        json={
            "expected_status": "open",
            "verification_outcome": "corrected",
            "next_route": "clinician_review",
        },
    )
    assert closed.status_code == 200, closed.text

    refreshed = staff_client.get(f"/api/tasks/{staff_task.task_id}/review-context").json()
    persisted = next(item for item in refreshed["candidates"] if item["review_item_id"] == first["review_item_id"])
    assert persisted["review_outcome"] == "corrected"
    assert persisted["correction_artifact_id"] == note.json()["artifact_id"]
    db_session.expire_all()
    clinician_task = db_session.scalar(
        select(Task).where(
            Task.workflow_id == staff_task.workflow_id,
            Task.task_kind == "clinician_priority_review",
        )
    )
    clinician_item = next(
        item
        for item in build_attention_items(
            db_session,
            patient_id=fixture.PATIENT_ID,
            viewer_role="clinician",
            as_of=datetime.now(),
        )
        if item.source_id == clinician_task.task_id
    )
    assert clinician_item.upstream_verification_outcome == "corrected"


def test_time_sensitive_follow_up_must_have_due_time(
    patient_client, staff_client, clinician_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    submitted = _submit(
        patient_client,
        "fa2-follow-up-due-001",
        "My headache is getting much worse.",
    )
    event_id = submitted.json()["event_id"]
    db_session.expire_all()
    tasks = _workflow_tasks(db_session, event_id)
    staff_task = next(task for task in tasks if task.assigned_role == "staff")
    clinician_task = next(task for task in tasks if task.assigned_role == "clinician")
    _review_all_candidates(staff_client, staff_task.task_id)
    verified = staff_client.post(
        f"/api/tasks/{staff_task.task_id}/verify-patient-report",
        json={
            "expected_status": "open",
            "verification_outcome": "verified",
            "next_route": "clinician_review",
        },
    )
    assert verified.status_code == 200, verified.text
    follow_up = clinician_client.post(
        f"/api/events/{event_id}/tasks",
        json={
            "title": "Clinician follow-up",
            "description": "Review the patient report.",
            "assigned_role": "clinician",
            "assigned_user_id": fixture.USER_CLINICIAN_ID,
            "patient_visible": False,
            "due_at": None,
            "source_artifact_id": None,
            "source_span": None,
        },
    )
    assert follow_up.status_code == 200, follow_up.text
    completion = clinician_client.post(
        f"/api/tasks/{clinician_task.task_id}/complete-clinician-review",
        json={
            "expected_status": "open",
            "review_outcome": "action_required",
            "time_sensitivity": "time_sensitive",
            "follow_up_task_id": follow_up.json()["task_id"],
        },
    )
    assert completion.status_code == 422
    dated_follow_up = clinician_client.post(
        f"/api/events/{event_id}/tasks",
        json={
            "title": "Clinician-owned dated follow-up",
            "description": "Review the patient report by the explicit due time.",
            "assigned_role": "clinician",
            "assigned_user_id": fixture.USER_CLINICIAN_ID,
            "patient_visible": False,
            "due_at": "2026-09-03T09:00:00",
            "source_artifact_id": None,
            "source_span": None,
        },
    )
    assert dated_follow_up.status_code == 200, dated_follow_up.text
    completed = clinician_client.post(
        f"/api/tasks/{clinician_task.task_id}/complete-clinician-review",
        json={
            "expected_status": "open",
            "review_outcome": "action_required",
            "time_sensitivity": "time_sensitive",
            "follow_up_task_id": dated_follow_up.json()["task_id"],
        },
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["follow_up_task_id"] == dated_follow_up.json()["task_id"]


def test_five_minute_policy_escalates_at_boundary_once(
    patient_client, db_session, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES", "5")
    submitted = _submit(
        patient_client,
        "fa2-overdue-review-001",
        "Nausea is still present.",
    )
    event_id = submitted.json()["event_id"]
    db_session.expire_all()
    staff_task = _workflow_tasks(db_session, event_id)[0]
    assert materialize_due_escalations(
        db_session, as_of=staff_task.escalate_at - timedelta(seconds=1)
    ) == 0
    assert materialize_due_escalations(db_session, as_of=staff_task.escalate_at) == 1
    db_session.commit()
    assert materialize_due_escalations(
        db_session, as_of=staff_task.escalate_at + timedelta(minutes=1)
    ) == 0
    db_session.commit()
    db_session.expire_all()
    tasks = _workflow_tasks(db_session, event_id)
    assert sum(task.task_kind == "clinician_priority_review" for task in tasks) == 1
    projections = db_session.scalars(
        select(GlanceProjection).where(
            GlanceProjection.patient_id == fixture.PATIENT_ID,
            GlanceProjection.viewer_role == "clinician",
        )
    ).all()
    assert any(row.priority_band <= 3 and row.eligible for row in projections)


def test_production_review_window_default_is_720(monkeypatch):
    monkeypatch.delenv("NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES", raising=False)
    assert review_window_minutes() == 720
