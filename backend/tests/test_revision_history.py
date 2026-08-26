"""Required test: revision history (version, revert, audit metadata)."""
from __future__ import annotations

from app.models import ArtifactVersion
from seed import fixture


def test_editable_notes_have_v1_snapshot(db_session):
    versions = db_session.query(ArtifactVersion).filter(
        ArtifactVersion.artifact_id == fixture.ART_DOC_NOTE
    ).all()
    assert [v.version for v in versions] == [1]


def test_edit_increments_version_and_keeps_old(clinician_client):
    r = clinician_client.patch(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}",
        json={"content": {"assessment": "updated"}, "expected_version": 1},
    )
    assert r.status_code == 200
    assert r.json()["version"] == 2

    rv = clinician_client.get(f"/api/artifacts/{fixture.ART_DOC_NOTE}/versions")
    assert rv.status_code == 200
    vs = rv.json()
    assert [v["version"] for v in vs] == [1, 2]
    assert vs[0]["content"].get("plan") is not None  # v1 unchanged


def test_revert_restores_content_and_creates_new_version(clinician_client):
    clinician_client.patch(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}",
        json={"content": {"assessment": "updated"}, "expected_version": 1},
    )
    r = clinician_client.post(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}/revert",
        json={"to_version": 1, "expected_version": 2},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["version"] == 3
    assert body["content"]["assessment"] == (
        "Near-daily tension-type headaches with morning nausea, onset over two weeks. "
        "Elevated BP 158/96. No red-flag neurological symptoms."
    )

    rv = clinician_client.get(f"/api/artifacts/{fixture.ART_DOC_NOTE}/versions")
    assert [v["version"] for v in rv.json()] == [1, 2, 3]


def test_revert_stale_expected_version_409(clinician_client):
    r = clinician_client.post(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}/revert",
        json={"to_version": 1, "expected_version": 99},
    )
    assert r.status_code == 409


def test_audit_log_metadata_only(clinician_client):
    clinician_client.patch(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}",
        json={"content": {"assessment": "edited"}, "expected_version": 1},
    )
    r = clinician_client.get(f"/api/events/{fixture.EVT_DOC_0821}/audit")
    assert r.status_code == 200
    logs = r.json()
    edits = [l for l in logs if l["action"] == "edit_note"]
    assert edits
    edit = edits[0]
    assert edit["actor_id"] == fixture.USER_CLINICIAN_ID
    assert edit["to_version"] == 2
    # metadata only: no raw clinical content in the audit record
    assert "content" not in edit and "body" not in edit
