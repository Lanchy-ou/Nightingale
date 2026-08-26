"""M6 required tests: Patient View server-side visibility contract.

Every assertion hits the API directly. The patient-view response must be a
minimal, explicit projection of clinician-confirmed `patient_instruction`
artifacts only — never internal clinician/staff notes, AI summaries, highlights,
comments, provenance internals or scoring metadata.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi.testclient import TestClient

from app.ids import new_id
from app.main import app
from app.models import Artifact, Comment, Event, Highlight
from seed import fixture

PV_URL = f"/api/patients/{fixture.PATIENT_ID}/patient-view"

TOP_KEYS = {"patient_id", "display_name", "current_summary", "instructions", "upcoming", "sessions"}
SUMMARY_KEYS = {"source_artifact_id", "event_id", "event_time", "instruction", "follow_up"}
INSTRUCTION_KEYS = {"artifact_id", "event_id", "event_time", "instruction", "follow_up"}
UPCOMING_KEYS = {"source_artifact_id", "event_id", "event_time", "kind", "text"}
SESSION_KEYS = {"event_id", "event_type", "started_at", "ended_at"}


# --- helpers ---------------------------------------------------------------
def _add_artifact(
    db,
    *,
    event_id,
    artifact_type,
    author_role,
    content,
    created_at=None,
    author_id=None,
    artifact_id=None,
):
    a = Artifact(
        artifact_id=artifact_id or new_id("art"),
        event_id=event_id,
        artifact_type=artifact_type,
        author_role=author_role,
        author_id=author_id,
        content=content,
        created_at=created_at or datetime(2026, 8, 26, 12, 0),
        version=1,
        provenance_pointer=None,
    )
    db.add(a)
    db.commit()
    return a


def _add_instruction(db, event_id, instruction, follow_up=None, created_at=None, artifact_id=None):
    return _add_artifact(
        db,
        event_id=event_id,
        artifact_type="patient_instruction",
        author_role="clinician",
        author_id=fixture.USER_CLINICIAN_ID,
        content={"instruction": instruction, "follow_up": follow_up},
        created_at=created_at or datetime(2026, 8, 26, 12, 0),
        artifact_id=artifact_id,
    )


# --- success + exact shape -------------------------------------------------
def test_patient_own_view_200_and_exact_keys(patient_client):
    r = patient_client.get(PV_URL)
    assert r.status_code == 200
    body = r.json()

    assert set(body.keys()) == TOP_KEYS
    assert body["patient_id"] == fixture.PATIENT_ID
    assert body["display_name"] == fixture.PATIENT_NAME

    cs = body["current_summary"]
    assert cs is not None and set(cs.keys()) == SUMMARY_KEYS
    # latest Event's instruction wins (Event 5 clinician_review, 08-26)
    assert cs["source_artifact_id"] == fixture.ART_REVIEW_INSTRUCTION
    assert cs["event_id"] == fixture.EVT_REVIEW_0826

    assert len(body["instructions"]) == 2
    for item in body["instructions"]:
        assert set(item.keys()) == INSTRUCTION_KEYS

    assert len(body["upcoming"]) == 2
    for item in body["upcoming"]:
        assert set(item.keys()) == UPCOMING_KEYS
        assert item["kind"] == "follow_up"

    # own AI sessions only (pre-consult + follow-up), newest first
    assert len(body["sessions"]) == 2
    for item in body["sessions"]:
        assert set(item.keys()) == SESSION_KEYS
    assert [s["event_id"] for s in body["sessions"]] == [fixture.EVT_FU_0824, fixture.EVT_PRE_0820]


# --- field / content leak guards ------------------------------------------
def test_patient_view_leaks_no_internal_content_or_keys(patient_client, db_session):
    # Inject sentinel internal content that must never surface.
    _add_artifact(
        db_session,
        event_id=fixture.EVT_DOC_0821,
        artifact_type="clinician_note",
        author_role="clinician",
        author_id=fixture.USER_CLINICIAN_ID,
        content={"assessment": "CLINICIAN_SENTINEL_A1B2", "plan": "hidden plan"},
    )
    _add_artifact(
        db_session,
        event_id=fixture.EVT_DOC_0821,
        artifact_type="staff_note",
        author_role="staff",
        author_id=fixture.USER_STAFF_ID,
        content={"note": "STAFF_SENTINEL_C3D4"},
    )
    _add_artifact(
        db_session,
        event_id=fixture.EVT_PRE_0820,
        artifact_type="ai_patient_session_summary",
        author_role="system",
        content={"summary": "AI_SUMMARY_SENTINEL_E5F6", "key_points": []},
    )
    db_session.add(
        Comment(
            comment_id=new_id("com"),
            anchor_type="event",
            anchor_id=fixture.EVT_DOC_0821,
            parent_comment_id=None,
            author_id=fixture.USER_CLINICIAN_ID,
            author_role="clinician",
            body="COMMENT_SENTINEL_G7H8",
            mentions=[],
            resolved=False,
            created_at=datetime(2026, 8, 26, 12, 0),
        )
    )
    db_session.add(
        Highlight(
            highlight_id=new_id("hl"),
            patient_id=fixture.PATIENT_ID,
            event_id=fixture.EVT_DOC_0821,
            artifact_id=fixture.ART_DOC_SUMMARY,
            source_artifact_id=fixture.ART_DOC_TRANSCRIPT,
            source_span={"kind": "segment", "index": 1},
            text="HIGHLIGHT_SENTINEL_I9J0",
            risk_reason="RISK_REASON_SENTINEL_K1L2",
            feature_flags={"explicit_risk": True},
            importance_score=99,
            status="suggested",
            status_history=[],
            created_at=datetime(2026, 8, 26, 12, 0),
            updated_at=datetime(2026, 8, 26, 12, 0),
            entity_key="sentinel:key",
            review_status="needs_review",
        )
    )
    db_session.commit()

    r = patient_client.get(PV_URL)
    assert r.status_code == 200
    raw = json.dumps(r.json())

    for sentinel in (
        "CLINICIAN_SENTINEL_A1B2",
        "STAFF_SENTINEL_C3D4",
        "AI_SUMMARY_SENTINEL_E5F6",
        "COMMENT_SENTINEL_G7H8",
        "HIGHLIGHT_SENTINEL_I9J0",
        "RISK_REASON_SENTINEL_K1L2",
    ):
        assert sentinel not in raw

    # Internal field names never appear as JSON keys.
    for field in (
        "risk_reason",
        "importance_score",
        "provenance_pointer",
        "entity_key",
        "review_status",
        "author_id",
        "author_role",
        "feature_flags",
        "source_span",
        "generation_metadata",
        "conflict_with",
        "status_history",
        "highlight",
        "comment",
        "audit",
    ):
        assert field not in raw, f"internal key leaked: {field}"


# --- unknown key in instruction content is not copied ----------------------
def test_unknown_instruction_key_not_returned(patient_client, db_session):
    _add_artifact(
        db_session,
        event_id=fixture.EVT_REVIEW_0826,
        artifact_type="patient_instruction",
        author_role="clinician",
        author_id=fixture.USER_CLINICIAN_ID,
        content={
            "instruction": "Take your medication as prescribed.",
            "follow_up": "Return in one week.",
            "internal_sentinel_key": "LEAK_VALUE_SENTINEL",
        },
        created_at=datetime(2026, 8, 26, 13, 0),
        artifact_id="art_unknown_key",
    )

    r = patient_client.get(PV_URL)
    assert r.status_code == 200
    raw = json.dumps(r.json())
    assert "internal_sentinel_key" not in raw
    assert "LEAK_VALUE_SENTINEL" not in raw

    # The injected instruction IS returned, but with only allowed keys.
    match = next(i for i in r.json()["instructions"] if i["artifact_id"] == "art_unknown_key")
    assert set(match.keys()) == INSTRUCTION_KEYS
    assert match["instruction"] == "Take your medication as prescribed."
    assert match["follow_up"] == "Return in one week."


# --- current_summary selection --------------------------------------------
def test_current_summary_latest_event_then_created_at_then_id(patient_client, db_session):
    # Same event, later created_at wins.
    _add_instruction(
        db_session,
        fixture.EVT_REVIEW_0826,
        "Later instruction wins",
        created_at=datetime(2026, 8, 26, 11, 0),
        artifact_id="art_tie_aaa",
    )
    _add_instruction(
        db_session,
        fixture.EVT_REVIEW_0826,
        "Even later instruction wins",
        created_at=datetime(2026, 8, 26, 11, 30),
        artifact_id="art_created_later",
    )

    r = patient_client.get(PV_URL)
    assert r.status_code == 200
    cs = r.json()["current_summary"]
    assert cs["source_artifact_id"] == "art_created_later"
    assert cs["instruction"] == "Even later instruction wins"

    # Same created_at => artifact_id tie-break (desc).
    _add_instruction(
        db_session,
        fixture.EVT_REVIEW_0826,
        "Tie-break zzz",
        created_at=datetime(2026, 8, 26, 11, 45),
        artifact_id="art_tie_zzz",
    )
    _add_instruction(
        db_session,
        fixture.EVT_REVIEW_0826,
        "Tie-break aaa",
        created_at=datetime(2026, 8, 26, 11, 45),
        artifact_id="art_tie_aaa2",
    )
    r = patient_client.get(PV_URL)
    cs = r.json()["current_summary"]
    assert cs["source_artifact_id"] == "art_tie_zzz"


# --- upcoming only projects non-empty follow_up ---------------------------
def test_upcoming_only_nonempty_follow_up(patient_client, db_session):
    # No follow_up => not in upcoming.
    _add_instruction(db_session, fixture.EVT_REVIEW_0826, "Instruction without follow-up")
    # Non-string follow_up => not in upcoming.
    _add_artifact(
        db_session,
        event_id=fixture.EVT_REVIEW_0826,
        artifact_type="patient_instruction",
        author_role="clinician",
        author_id=fixture.USER_CLINICIAN_ID,
        content={"instruction": "Instruction with bad follow-up", "follow_up": 123},
        created_at=datetime(2026, 8, 26, 14, 0),
        artifact_id="art_bad_followup",
    )

    r = patient_client.get(PV_URL)
    assert r.status_code == 200
    texts = [u["text"] for u in r.json()["upcoming"]]
    assert "Instruction without follow-up" not in texts
    assert "123" not in texts
    # fixture's two follow_up strings are present
    assert any("blood test result" in t for t in texts)
    assert any("few days" in t for t in texts)


# --- empty patient (no instruction) falls back to nothing -----------------
def test_no_instruction_returns_null_and_no_fallback(client, db_session):
    # Give pat_002 a clinician note with a sentinel; it must NOT be used.
    evt = Event(
        event_id="evt_ben_note",
        patient_id=fixture.PATIENT_B_ID,
        clinic_id=fixture.CLINIC_ID,
        event_type="doctor_consult",
        started_at=datetime(2026, 8, 25, 9, 0),
        ended_at=datetime(2026, 8, 25, 9, 20),
        created_at=datetime(2026, 8, 25, 9, 25),
    )
    db_session.add(evt)
    db_session.commit()
    _add_artifact(
        db_session,
        event_id="evt_ben_note",
        artifact_type="clinician_note",
        author_role="clinician",
        author_id=fixture.USER_CLINICIAN_ID,
        content={"assessment": "BEN_CLINICIAN_FALLBACK_SENTINEL", "plan": "x"},
    )

    with TestClient(app, headers={"X-User-Id": fixture.USER_PATIENT_B_ID}) as c:
        r = c.get(f"/api/patients/{fixture.PATIENT_B_ID}/patient-view")
    assert r.status_code == 200
    body = r.json()
    assert body["current_summary"] is None
    assert body["instructions"] == []
    assert body["upcoming"] == []
    assert body["sessions"] == []
    assert "BEN_CLINICIAN_FALLBACK_SENTINEL" not in json.dumps(body)


# --- sessions --------------------------------------------------------------
def test_sessions_own_only_no_internal_fields(patient_client, db_session):
    # A raw_conversation authored by someone else must not surface as a session.
    _add_artifact(
        db_session,
        event_id=fixture.EVT_PRE_0820,
        artifact_type="raw_conversation",
        author_role="patient",
        author_id="usr_patient_02",
        content={"messages": []},
        artifact_id="art_foreign_raw",
    )
    r = patient_client.get(PV_URL)
    assert r.status_code == 200
    sessions = r.json()["sessions"]
    assert [s["event_id"] for s in sessions] == [fixture.EVT_FU_0824, fixture.EVT_PRE_0820]
    for s in sessions:
        assert set(s.keys()) == SESSION_KEYS
        assert "status" not in s
        assert "ai_summary_artifact_id" not in s
        assert "highlight_ids" not in s


# --- RBAC ----------------------------------------------------------------
def test_patient_other_patient_404_same_body_as_cross_clinic(patient_client, client):
    other = patient_client.get(f"/api/patients/{fixture.PATIENT_B_ID}/patient-view")
    cross = client.get(
        PV_URL, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID}
    )
    assert other.status_code == cross.status_code == 404
    assert other.json() == cross.json()


def test_absent_patient_view_404(client):
    r = client.get(
        "/api/patients/pat_does_not_exist/patient-view",
        headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID},
    )
    assert r.status_code == 404


def test_staff_clinician_admin_403(staff_client, clinician_client, admin_client):
    assert staff_client.get(PV_URL).status_code == 403
    assert clinician_client.get(PV_URL).status_code == 403
    assert admin_client.get(PV_URL).status_code == 403


def test_anonymous_401(client):
    assert client.get(PV_URL).status_code == 401


def test_patient_view_cross_clinic_404(client):
    r = client.get(PV_URL, headers={"X-User-Id": fixture.USER_CLINICIAN_B_ID})
    assert r.status_code == 404


# --- existing patient endpoints keep M3 filtering -------------------------
def test_existing_endpoints_still_filter_for_patient(patient_client):
    r = patient_client.get(f"/api/patients/{fixture.PATIENT_ID}/events")
    assert r.status_code == 200
    doc = next(e for e in r.json() if e["event_type"] == "doctor_consult")
    assert doc["artifact_count"] == 1  # internal artifacts do not leak count

    r = patient_client.get(f"/api/events/{fixture.EVT_DOC_0821}/artifacts")
    assert r.status_code == 200
    assert {a["artifact_type"] for a in r.json()} == {"patient_instruction"}


# --- session POST then appears in patient-view ----------------------------
def test_session_post_appears_in_next_patient_view(patient_client):
    payload = {
        "session_id": "sess-pv-refresh",
        "event_type": "patient_followup",
        "started_at": "2026-08-27T10:00:00",
        "content": {"messages": [{"id": "m1", "speaker": "patient", "text": "Headache is better today."}]},
    }
    r = patient_client.post(f"/api/patients/{fixture.PATIENT_ID}/sessions", json=payload)
    assert r.status_code == 200
    assert "ai_summary_artifact_id" not in r.json()
    assert "highlight_ids" not in r.json()

    rv = patient_client.get(PV_URL)
    assert rv.status_code == 200
    session_ids = [s["event_id"] for s in rv.json()["sessions"]]
    assert r.json()["event_id"] in session_ids
