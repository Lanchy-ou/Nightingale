from __future__ import annotations

from sqlalchemy import select

from app.models import Artifact, Highlight
from app.tasks import resolve_exact_span
from seed import fixture


def _create(client, span):
    return client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json={
            "title": "Evidence-bound blood test",
            "description": "internal",
            "assigned_role": "patient",
            "assigned_user_id": fixture.USER_PATIENT_ID,
            "patient_visible": True,
            "due_at": None,
            "source_artifact_id": fixture.ART_DOC_TRANSCRIPT,
            "source_span": span,
        },
    )


def test_task_provenance_resolves_event_artifact_and_exact_span(clinician_client):
    created = _create(
        clinician_client,
        {"kind": "segment", "index": 16, "offset": [0, 61]},
    )
    assert created.status_code == 200
    resolved = clinician_client.get(
        f"/api/tasks/{created.json()['task_id']}/provenance"
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["event"]["event_id"] == fixture.EVT_DOC_0821
    assert body["source_artifact"]["artifact_id"] == fixture.ART_DOC_TRANSCRIPT
    assert body["quote"] == "I'm ordering a blood test to check for any underlying causes."


def test_invalid_or_mismatched_span_fails_closed(clinician_client):
    for span in (
        {"kind": "segment", "index": 999, "offset": [0, 5]},
        {"kind": "segment", "index": 16, "offset": [0, 9999]},
        {"kind": "unknown", "index": 16, "offset": [0, 5]},
    ):
        response = _create(clinician_client, span)
        assert response.status_code == 422


def test_artifact_and_span_must_be_supplied_together(clinician_client):
    body = {
        "title": "Bad partial provenance",
        "description": "internal",
        "assigned_role": "patient",
        "assigned_user_id": fixture.USER_PATIENT_ID,
        "patient_visible": True,
        "due_at": None,
        "source_artifact_id": fixture.ART_DOC_TRANSCRIPT,
        "source_span": None,
    }
    assert clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks", json=body
    ).status_code == 422


def test_task_provenance_is_not_available_to_patient(patient_client):
    assert patient_client.get(
        f"/api/tasks/{fixture.TASK_BLOOD_TEST}/provenance"
    ).status_code == 403


def test_event_level_task_provenance_resolves_without_artifact(clinician_client):
    created = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json={
            "title": "Event-only action",
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
    resolved = clinician_client.get(
        f"/api/tasks/{created.json()['task_id']}/provenance"
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["event"]["event_id"] == fixture.EVT_DOC_0821
    assert body["source_artifact"] is None
    assert body["span"] is None
    assert body["quote"] is None


# --- resolve_exact_span hardening: any abnormal structure must fail closed ---
VALID_SPAN = {"kind": "segment", "index": 16, "offset": [0, 61]}


def test_resolve_exact_span_rejects_malformed_content():  # noqa: PLR0915
    assert resolve_exact_span(None, VALID_SPAN) is None
    assert resolve_exact_span("text", VALID_SPAN) is None
    assert resolve_exact_span([], VALID_SPAN) is None
    assert resolve_exact_span(42, VALID_SPAN) is None
    # segments must be a list when present; members must be dicts
    assert resolve_exact_span({"segments": "oops"}, VALID_SPAN) is None
    assert resolve_exact_span({"segments": {"0": 1}}, VALID_SPAN) is None
    assert resolve_exact_span({"segments": ["text"]}, VALID_SPAN) is None
    assert resolve_exact_span({"segments": [None]}, VALID_SPAN) is None
    assert resolve_exact_span({"segments": [{"index": "16", "text": "x"}]}, VALID_SPAN) is None
    assert (
        resolve_exact_span({"segments": [{"index": 16, "text": 5}]}, VALID_SPAN)
        is None
    )
    assert (
        resolve_exact_span(
            {"segments": [{"index": True, "text": "x"}]},
            {"kind": "segment", "index": True, "offset": [0, 1]},
        )
        is None
    )
    # messages must be a list; members must be dicts with string text
    message_span = {"kind": "message", "index": 1, "offset": [0, 1]}
    assert resolve_exact_span({"messages": "oops"}, message_span) is None
    assert resolve_exact_span({"messages": ["text"]}, message_span) is None
    assert (
        resolve_exact_span({"messages": [{"text": 5}]}, message_span) is None
    )
    assert (
        resolve_exact_span({"messages": []}, {"kind": "message", "index": 0, "offset": [0, 1]})
        is None
    )
    # section index must be a string and the value must be a string
    section_span = {"kind": "section", "index": "plan", "offset": [0, 1]}
    assert resolve_exact_span({"plan": 5}, section_span) is None
    assert (
        resolve_exact_span({"plan": "x"}, {"kind": "section", "index": 5, "offset": [0, 1]})
        is None
    )


def test_resolve_exact_span_rejects_malformed_spans():
    content = {
        "segments": [{"index": 16, "text": "I'm ordering a blood test."}]
    }
    assert resolve_exact_span(content, None) is None
    assert resolve_exact_span(content, []) is None
    assert resolve_exact_span(content, {"kind": "segment"}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [0, 5], "extra": 1}) is None
    assert resolve_exact_span(content, {"kind": "bogus", "index": 16, "offset": [0, 5]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": "0-5"}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [0]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [0.5, 5]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [0, 5, 9]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [True, 5]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [-1, 5]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [5, 5]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [5, 4]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 999, "offset": [0, 5]}) is None
    assert resolve_exact_span(content, {"kind": "segment", "index": 16, "offset": [0, 999]}) is None


def test_malformed_artifact_content_fails_closed_with_422_not_500(
    clinician_client, db_session
):
    from datetime import datetime

    db_session.add(
        Artifact(
            artifact_id="art_malformed_task_source",
            event_id=fixture.EVT_DOC_0821,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content={"segments": "not-a-list"},  # structurally broken content
            created_at=datetime(2026, 8, 27, 8, 0),
            version=1,
            provenance_pointer=None,
            ingestion_key=None,
            generation_metadata=None,
        )
    )
    db_session.commit()

    response = clinician_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/tasks",
        json={
            "title": "Task against broken content",
            "description": "internal",
            "assigned_role": "patient",
            "assigned_user_id": fixture.USER_PATIENT_ID,
            "patient_visible": True,
            "due_at": None,
            "source_artifact_id": "art_malformed_task_source",
            "source_span": {"kind": "segment", "index": 0, "offset": [0, 5]},
        },
    )
    # Fail closed as a validation error — never a 500 crash.
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
