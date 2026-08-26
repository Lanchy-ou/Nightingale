"""Required test: concurrent edits have deterministic behavior."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from fastapi.testclient import TestClient

from app.main import app
from seed import fixture


def test_different_sections_do_not_overwrite(staff_client, clinician_client):
    r = staff_client.post(
        f"/api/events/{fixture.EVT_DOC_0821}/notes",
        json={"artifact_type": "staff_note", "content": {"note": "initial staff note"}},
    )
    assert r.status_code == 200
    staff_art = r.json()["artifact_id"]

    r1 = staff_client.patch(
        f"/api/artifacts/{staff_art}",
        json={"content": {"note": "staff v2"}, "expected_version": 1},
    )
    r2 = clinician_client.patch(
        f"/api/artifacts/{fixture.ART_DOC_NOTE}",
        json={"content": {"assessment": "clinician v2"}, "expected_version": 1},
    )
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["content"]["note"] == "staff v2"
    assert r2.json()["content"]["assessment"] == "clinician v2"


def test_same_section_conflict_is_deterministic(clinician_client):
    art = fixture.ART_DOC_NOTE
    # Bring the artifact to v3 (v1 -> v2 -> v3).
    clinician_client.patch(
        f"/api/artifacts/{art}",
        json={"content": {"assessment": "v2"}, "expected_version": 1},
    )
    clinician_client.patch(
        f"/api/artifacts/{art}",
        json={"content": {"assessment": "v3"}, "expected_version": 2},
    )

    # Two writers both hold expected_version=3.
    r1 = clinician_client.patch(
        f"/api/artifacts/{art}",
        json={"content": {"assessment": "writer A"}, "expected_version": 3},
    )
    assert r1.status_code == 200
    assert r1.json()["version"] == 4

    r2 = clinician_client.patch(
        f"/api/artifacts/{art}",
        json={"content": {"assessment": "writer B"}, "expected_version": 3},
    )
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "conflict"

    # The conflict must be recorded in the audit log.
    r3 = clinician_client.get(f"/api/events/{fixture.EVT_DOC_0821}/audit")
    assert any(l["action"] == "conflict" for l in r3.json())


def test_simultaneous_same_section_writes_yield_one_success_and_one_conflict():
    barrier = Barrier(3)

    def write(content: str):
        with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as client:
            barrier.wait()
            return client.patch(
                f"/api/artifacts/{fixture.ART_DOC_NOTE}",
                json={"content": {"assessment": content}, "expected_version": 1},
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(write, "simultaneous writer A")
        second = pool.submit(write, "simultaneous writer B")
        barrier.wait()
        responses = [first.result(), second.result()]

    assert sorted(r.status_code for r in responses) == [200, 409]
    winner = next(r for r in responses if r.status_code == 200)
    conflict = next(r for r in responses if r.status_code == 409)
    assert winner.json()["version"] == 2
    assert conflict.json()["error"]["current_version"] == 2
