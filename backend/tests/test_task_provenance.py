from __future__ import annotations

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
