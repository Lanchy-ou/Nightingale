"""M7: Glance ordering determinism + write-after-read + status concurrency.

H1 — final `highlight_id` tiebreak makes identical rows deterministic;
H2 — accept/pin recomputes `clinician_confirmed` score and is visible in the
     very next Glance read on the same connection lifecycle;
H3 — concurrent highlight status mutations resolve deterministically via an
     optimistic lock (never a silent last-write-wins overwrite).
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from threading import Barrier

from fastapi.testclient import TestClient

from app.main import app
from app.models import Highlight
from seed import fixture

# Global conftest autouse fixture re-seeds before every test, so status
# mutations never leak between tests.

TIE_CREATED_AT = datetime(2026, 8, 26, 12, 0)


def _insert_highlight(
    db,
    hid: str,
    status: str = "suggested",
    score: int = 1,
    review_status: str | None = None,
) -> None:
    db.add(
        Highlight(
            highlight_id=hid,
            patient_id=fixture.PATIENT_B_ID,
            event_id="evt_tie",
            artifact_id="art_tie",
            source_artifact_id="art_tie",
            source_span={"kind": "section", "index": "probe"},
            text=f"probe {hid}",
            risk_reason="tiebreak probe",
            feature_flags={},
            importance_score=score,
            status=status,
            status_history=[],
            created_at=TIE_CREATED_AT,
            updated_at=TIE_CREATED_AT,
            entity_type=None,
            entity_key=None,
            assertion_value=None,
            conflict_with_artifact_id=None,
            review_status=review_status,
        )
    )
    db.commit()


def test_glance_tiebreak_orders_by_highlight_id(clinician_client, db_session):
    # Same score, same pinned state, same created_at — insertion order must not
    # leak through; the deterministic final key is highlight_id.
    for hid in ["z_last", "a_first", "m_mid"]:
        _insert_highlight(db_session, hid)

    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_B_ID}/glance")
    assert r.status_code == 200
    ids = [h["highlight_id"] for h in r.json()["highlights"]]
    assert ids == ["a_first", "m_mid", "z_last"]


def test_glance_pinned_priority_unaffected_by_tiebreak(clinician_client, db_session):
    _insert_highlight(db_session, "b_second", status="suggested")
    _insert_highlight(db_session, "a_first", status="suggested")
    _insert_highlight(db_session, "pinned_one", status="pinned")

    r = clinician_client.get(f"/api/patients/{fixture.PATIENT_B_ID}/glance")
    ids = [h["highlight_id"] for h in r.json()["highlights"]]
    assert ids[0] == "pinned_one"  # pinned wins even at equal score
    assert ids[1:] == ["a_first", "b_second"]  # tiebreak still holds within a group


def test_needs_review_surfaces_ahead_of_normal_suggestions(clinician_client, db_session):
    for index in range(6):
        _insert_highlight(db_session, f"normal_{index}", score=10 - index)
    _insert_highlight(
        db_session,
        "allergy_conflict",
        score=0,
        review_status="needs_review",
    )

    response = clinician_client.get(f"/api/patients/{fixture.PATIENT_B_ID}/glance")
    assert response.status_code == 200
    ids = [item["highlight_id"] for item in response.json()["highlights"]]
    assert "allergy_conflict" in ids
    assert ids[0] == "allergy_conflict"


def test_accept_recomputes_score_and_is_immediately_visible(clinician_client, db_session):
    before = db_session.get(Highlight, "hl_bp_elevated")
    before_score = before.importance_score

    r = clinician_client.post(
        "/api/highlights/hl_bp_elevated/status", json={"status": "accepted"}
    )
    assert r.status_code == 200
    assert r.json()["feature_flags"]["clinician_confirmed"] is True
    assert r.json()["importance_score"] == before_score + 2

    # Write-after-read: the same workflow's next GET reflects the new score.
    glance = clinician_client.get(f"/api/patients/{fixture.PATIENT_ID}/glance")
    accepted = next(
        h for h in glance.json()["highlights"] if h["highlight_id"] == "hl_bp_elevated"
    )
    assert accepted["importance_score"] == before_score + 2
    assert accepted["feature_flags"]["clinician_confirmed"] is True


def test_concurrent_highlight_status_is_deterministic(db_session):
    before = db_session.get(Highlight, "hl_bp_elevated")
    before_score = before.importance_score

    barrier = Barrier(3)

    def accept():
        with TestClient(app, headers={"X-User-Id": fixture.USER_CLINICIAN_ID}) as client:
            barrier.wait()
            return client.post(
                "/api/highlights/hl_bp_elevated/status", json={"status": "accepted"}
            )

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(accept)
        second = pool.submit(accept)
        barrier.wait()
        responses = [first.result(), second.result()]

    # At least one writer must win; the loser is either an idempotent no-op
    # (sequential) or a deterministic 409 conflict (true overlap). Never 422/500.
    codes = sorted(r.status_code for r in responses)
    assert codes[0] == 200
    assert codes[1] in (200, 409)
    for r in responses:
        if r.status_code == 409:
            body = r.json()["error"]
            assert body["code"] == "conflict"
            assert body["current_status"] == "accepted"

    # Final state is exactly one transition — no duplicated history, no silent
    # score/status merge from the losing writer.
    db_session.expire_all()
    hl = db_session.get(Highlight, "hl_bp_elevated")
    assert hl.status == "accepted"
    assert hl.feature_flags["clinician_confirmed"] is True
    assert hl.importance_score == before_score + 2
    assert len(hl.status_history) == 1
    assert hl.status_history[0]["from"] == "suggested"
    assert hl.status_history[0]["to"] == "accepted"
