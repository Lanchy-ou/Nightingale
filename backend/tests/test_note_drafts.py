"""Private drafts never become clinical content without an explicit note write."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app
from app.models import Artifact, ArtifactVersion, NoteDraft, User
from seed import fixture as f

URL = f"/api/events/{f.EVT_DOC_0821}/note-drafts/new"
EDIT_URL = f"/api/events/{f.EVT_DOC_0821}/note-drafts/{f.ART_DOC_NOTE}"


def payload(revision=0, fields=None, base=0):
    return {"expected_revision": revision, "base_version": base, "fields": fields or {"body": "PRIVATE_DRAFT_SENTINEL"}}


def test_saved_draft_resumes_without_changing_record(clinician_client, patient_client):
    artifacts_url = f"/api/events/{f.EVT_DOC_0821}/artifacts"
    audit_url = f"/api/events/{f.EVT_DOC_0821}/audit"
    before = clinician_client.get(artifacts_url).json()
    audit_before = clinician_client.get(audit_url).json()
    assert clinician_client.get(URL).json()["fields"] is None
    saved = clinician_client.put(URL, json=payload())
    assert saved.status_code == 200, saved.text
    assert saved.json()["revision"] == 1
    assert clinician_client.get(URL).json() == saved.json()
    assert clinician_client.get(artifacts_url).json() == before
    assert clinician_client.get(audit_url).json() == audit_before
    assert "PRIVATE_DRAFT_SENTINEL" not in patient_client.get(f"/api/patients/{f.PATIENT_ID}/patient-view").text
    assert "PRIVATE_DRAFT_SENTINEL" not in clinician_client.get(f"/api/patients/{f.PATIENT_ID}/glance").text


def test_private_drafts_are_owner_and_role_isolated(clinician_client, staff_client, db_session):
    assert clinician_client.put(URL, json=payload()).status_code == 200
    with TestClient(app, headers={"X-User-Id": f.USER_CLINICIAN_2_ID}) as other:
        assert other.get(URL).json()["fields"] is None
        assert other.put(URL, json=payload(fields={"body": "Other owner"})).status_code == 200
    assert staff_client.get(URL).json()["fields"] is None
    assert staff_client.put(URL, json=payload(fields={"body": "Staff private"})).status_code == 200
    assert clinician_client.get(URL).json()["fields"]["body"] == "PRIVATE_DRAFT_SENTINEL"
    user = db_session.get(User, f.USER_CLINICIAN_ID)
    user.role = "staff"
    db_session.commit()
    assert clinician_client.get(URL).json()["fields"] is None


@pytest.mark.parametrize("role", ["patient", "admin"])
def test_non_authors_cannot_read_or_write_drafts(role):
    with TestClient(app, headers={"X-User-Id": f"usr_{role}_01"}) as client:
        assert client.get(URL).status_code == 403
        assert client.put(URL, json=payload()).status_code == 403


def test_scope_and_section_permissions(client, staff_client, clinician_client):
    assert client.get(URL).status_code == 401
    assert staff_client.get(EDIT_URL).status_code == 403
    assert staff_client.put(EDIT_URL, json=payload()).status_code == 403
    with TestClient(app, headers={"X-User-Id": f.USER_CLINICIAN_B_ID}) as other:
        missing = other.get("/api/events/missing/note-drafts/new")
        assert other.get(URL).status_code == 404
        assert other.get(URL).json() == missing.json()
        assert other.put(URL, json=payload()).status_code == 404
    assert clinician_client.get(f"/api/events/{f.EVT_DOC_0821}/note-drafts/{f.ART_DOC_TRANSCRIPT}").status_code == 403


def test_clear_retains_revision_and_rejects_stale_aba_write(clinician_client):
    assert clinician_client.put(URL, json=payload()).status_code == 200
    assert clinician_client.put(URL, json=payload()).status_code == 409
    clear = clinician_client.put(URL, json={"expected_revision": 1, "base_version": 0, "fields": None})
    assert clear.status_code == 200
    assert clear.json()["revision"] == 2 and clear.json()["fields"] is None
    assert clinician_client.put(URL, json=payload()).status_code == 409
    assert clinician_client.put(URL, json=payload(1)).status_code == 409
    assert clinician_client.put(URL, json=payload(2)).json()["revision"] == 3


def test_two_first_saves_have_exactly_one_winner():
    barrier = Barrier(2)
    def save(text):
        with TestClient(app, headers={"X-User-Id": f.USER_CLINICIAN_ID}) as client:
            barrier.wait()
            return client.put(URL, json=payload(fields={"body": text})).status_code
    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(save, ["First", "Second"])) == [200, 409]


def test_edit_draft_keeps_original_version_and_full_snapshot(clinician_client, db_session):
    artifact = db_session.get(Artifact, f.ART_DOC_NOTE)
    original = {**artifact.content, "structured": {"preserve": True}}
    artifact.content = original
    snapshot = db_session.scalar(select(ArtifactVersion).where(ArtifactVersion.artifact_id == f.ART_DOC_NOTE, ArtifactVersion.version == 1))
    snapshot.content = original
    db_session.commit()
    fields = {key: value for key, value in original.items() if isinstance(value, str)}
    fields["assessment"] = "Private pending correction"
    saved = clinician_client.put(EDIT_URL, json=payload(fields=fields, base=1))
    assert saved.status_code == 200, saved.text
    assert clinician_client.patch(f"/api/artifacts/{f.ART_DOC_NOTE}", json={"expected_version": 1, "content": {**original, "assessment": "Other final edit"}}).status_code == 200
    restored = clinician_client.get(EDIT_URL).json()
    assert restored["base_version"] == 1
    assert restored["base_content"] == original
    assert restored["fields"]["assessment"] == "Private pending correction"
    assert clinician_client.patch(f"/api/artifacts/{f.ART_DOC_NOTE}", json={"expected_version": 1, "content": fields}).status_code == 409


@pytest.mark.parametrize("body", [payload(base=1), payload(fields={"assessment": "wrong section"}), payload(fields={"body": "x" * 100001}), {**payload(), "owner_id": "someone"}, {**payload(), "expected_revision": -1}])
def test_invalid_drafts_fail_closed(clinician_client, body, db_session):
    assert clinician_client.put(URL, json=body).status_code == 422
    assert db_session.scalar(select(NoteDraft)) is None
