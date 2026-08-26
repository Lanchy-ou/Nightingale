"""M3 collaboration tests: anchors, replies, mentions, and resolution."""
from __future__ import annotations

from seed import fixture


def test_threaded_reply_preserves_anchor_and_mention(staff_client, clinician_client):
    root = staff_client.post(
        "/api/comments",
        json={
            "anchor_type": "event",
            "anchor_id": fixture.EVT_DOC_0821,
            "body": "Please review the follow-up plan.",
            "mentions": [fixture.USER_CLINICIAN_ID],
        },
    )
    assert root.status_code == 200
    root_body = root.json()
    assert root_body["mentions"] == [fixture.USER_CLINICIAN_ID]

    reply = clinician_client.post(
        "/api/comments",
        json={
            "anchor_type": root_body["anchor_type"],
            "anchor_id": root_body["anchor_id"],
            "parent_comment_id": root_body["comment_id"],
            "body": "Reviewed; follow-up remains scheduled.",
            "mentions": [],
        },
    )
    assert reply.status_code == 200
    assert reply.json()["parent_comment_id"] == root_body["comment_id"]

    listed = clinician_client.get(f"/api/events/{fixture.EVT_DOC_0821}/comments")
    assert listed.status_code == 200
    assert [c["comment_id"] for c in listed.json()] == [
        root_body["comment_id"],
        reply.json()["comment_id"],
    ]


def test_artifact_anchored_comment_is_in_event_feed(staff_client):
    created = staff_client.post(
        "/api/comments",
        json={
            "anchor_type": "artifact",
            "anchor_id": fixture.ART_DOC_SUMMARY,
            "body": "Please verify this AI-scribed summary.",
            "mentions": [],
        },
    )
    assert created.status_code == 200

    listed = staff_client.get(f"/api/events/{fixture.EVT_DOC_0821}/comments")
    assert any(
        c["comment_id"] == created.json()["comment_id"]
        and c["anchor_type"] == "artifact"
        for c in listed.json()
    )


def test_comment_resolve_and_unresolve_are_audited(staff_client, clinician_client):
    created = staff_client.post(
        "/api/comments",
        json={
            "anchor_type": "event",
            "anchor_id": fixture.EVT_DOC_0821,
            "body": "Please resolve after review.",
            "mentions": [],
        },
    ).json()

    resolved = clinician_client.post(f"/api/comments/{created['comment_id']}/resolve", json={})
    assert resolved.status_code == 200
    assert resolved.json()["resolved"] is True
    assert resolved.json()["resolved_by"] == fixture.USER_CLINICIAN_ID

    reopened = clinician_client.post(f"/api/comments/{created['comment_id']}/unresolve", json={})
    assert reopened.status_code == 200
    assert reopened.json()["resolved"] is False

    audit = clinician_client.get(f"/api/events/{fixture.EVT_DOC_0821}/audit").json()
    actions = [row["action"] for row in audit]
    assert "resolve" in actions and "unresolve" in actions


def test_reply_must_share_parent_anchor(staff_client):
    root = staff_client.post(
        "/api/comments",
        json={
            "anchor_type": "event",
            "anchor_id": fixture.EVT_DOC_0821,
            "body": "Root",
            "mentions": [],
        },
    ).json()
    bad_reply = staff_client.post(
        "/api/comments",
        json={
            "anchor_type": "artifact",
            "anchor_id": fixture.ART_DOC_SUMMARY,
            "parent_comment_id": root["comment_id"],
            "body": "Wrong anchor",
            "mentions": [],
        },
    )
    assert bad_reply.status_code == 422
