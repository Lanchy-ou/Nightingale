"""M1 smoke test 1: schema + fixture integrity (facts must not contradict)."""
from __future__ import annotations

import json

from sqlalchemy import select

from app.highlights import extract_text, locate_span
from app.models import Artifact, ArtifactVersion, Clinic, Event, Highlight, Patient, User
from seed import fixture


def _content(db, artifact_id: str) -> str:
    return json.dumps(db.get(Artifact, artifact_id).content)


def test_fixture_shape(db_session):
    assert len(db_session.scalars(select(Clinic)).all()) == 2
    users = db_session.scalars(select(User)).all()
    assert {u.role for u in users} == {"patient", "staff", "clinician", "admin"}
    assert len(db_session.scalars(select(Patient)).all()) == 2


def test_event_timeline_dates_and_types(db_session):
    events = db_session.scalars(select(Event).order_by(Event.started_at)).all()
    assert [e.event_type for e in events] == [
        "historical_review",
        "historical_review",
        "patient_ai_preconsult",
        "nurse_consult",
        "doctor_consult",
        "patient_followup",
        "clinician_review",
    ]
    assert events[0].started_at.year == 2025 and events[0].started_at.month == 4
    assert events[1].started_at.year == 2026 and events[1].started_at.month == 2
    assert events[2].started_at.year == 2026 and events[2].started_at.month == 8


def test_ai_artifacts_are_system_authored(db_session):
    ai_types = [
        "ai_doctor_consult_summary",
        "ai_nurse_consult_summary",
        "ai_patient_session_summary",
    ]
    ai_artifacts = db_session.scalars(
        select(Artifact).where(Artifact.artifact_type.in_(ai_types))
    ).all()
    assert len(ai_artifacts) == 4  # pre, nurse, doctor, follow-up summaries
    for a in ai_artifacts:
        assert a.author_role == "system"
        assert a.author_id is None


def test_fact_checklist_is_satisfied(db_session):
    # 1. headache frequency + 7/10 severity (08-20 pre-consult raw)
    pre_raw = _content(db_session, fixture.ART_PRE_RAW)
    assert "once a week" in pre_raw and "almost every day" in pre_raw
    assert "7 out of 10" in pre_raw

    # 3. BP 158/96 (08-21 nurse transcript)
    nurse_transcript = _content(db_session, fixture.ART_NURSE_TRANSCRIPT)
    assert "158 over 96" in nurse_transcript

    # 4. medication started 2026-02-06
    hist_note = _content(db_session, fixture.ART_HIST_2026_NOTE)
    assert "propranolol" in hist_note.lower()

    # 5. blood test ordered (08-21) and still pending (08-24)
    doc_note = _content(db_session, fixture.ART_DOC_NOTE)
    assert "blood test" in doc_note.lower()
    fu_raw = _content(db_session, fixture.ART_FU_RAW)
    assert "waiting for my appointment" in fu_raw

    # 1 + 2. headache improved to 3/10 and nausea persists (08-24)
    assert "3 out of 10" in fu_raw
    fu_summary = _content(db_session, fixture.ART_FU_SUMMARY)
    assert "nausea" in fu_summary.lower()

    # 6. follow-up scheduled
    assert "follow-up" in doc_note.lower()


def test_doctor_transcript_has_20_plus_segments(db_session):
    t = db_session.get(Artifact, fixture.ART_DOC_TRANSCRIPT)
    segs = t.content["segments"]
    assert len(segs) >= 20
    # C1 canonical Doctor Transcript contract: 0-based continuous indexes.
    assert [segment["index"] for segment in segs] == list(range(len(segs)))
    assert {segment["speaker"] for segment in segs} <= {"doctor", "patient"}
    summary = db_session.get(Artifact, fixture.ART_DOC_SUMMARY)
    assert extract_text(t.content, summary.provenance_pointer["span"]) == (
        "I'm ordering a blood test to check for any underlying causes."
    )


def test_explicit_encounter_groups_only_nurse_and_doctor_visit(db_session):
    nurse = db_session.get(Event, fixture.EVT_NURSE_0821)
    doctor = db_session.get(Event, fixture.EVT_DOC_0821)
    assert nurse.encounter_id == doctor.encounter_id == fixture.ENCOUNTER_0821
    for event_id in (
        fixture.EVT_HIST_2025,
        fixture.EVT_HIST_2026,
        fixture.EVT_PRE_0820,
        fixture.EVT_FU_0824,
        fixture.EVT_REVIEW_0826,
    ):
        assert db_session.get(Event, event_id).encounter_id is None


def test_c1_demo_transcript_is_strict_and_fact_consistent():
    segments = fixture.C1_DEMO_DOCTOR_TRANSCRIPT["segments"]
    assert [segment["index"] for segment in segments] == list(range(len(segments)))
    assert {segment["speaker"] for segment in segments} <= {"doctor", "patient"}
    text = " ".join(segment["text"] for segment in segments).lower()
    assert "3 out of 10" in text
    assert "nauseous" in text
    assert "blood test" in text and "not yet" in text
    assert "propranolol 20 mg daily" in text


def test_event5_review_exists_and_ordered(db_session):
    review = db_session.get(Event, fixture.EVT_REVIEW_0826)
    assert review is not None
    assert review.event_type == "clinician_review"
    fu = db_session.get(Event, fixture.EVT_FU_0824)
    assert review.started_at > fu.started_at


def test_review_note_has_single_v1_snapshot(db_session):
    versions = db_session.scalars(
        select(ArtifactVersion).where(ArtifactVersion.artifact_id == fixture.ART_REVIEW_NOTE)
    ).all()
    assert [v.version for v in versions] == [1]


def test_patient_instruction_is_patient_visible(db_session):
    inst = db_session.get(Artifact, fixture.ART_REVIEW_INSTRUCTION)
    assert inst.artifact_type == "patient_instruction"
    assert inst.author_role == "clinician"
    assert "instruction" in inst.content
    assert "assessment" not in inst.content  # no internal clinical reasoning


def test_historical_notes_enriched(db_session):
    hist2025 = _content(db_session, fixture.ART_HIST_2025_NOTE)
    assert "once weekly" in hist2025
    hist2026 = _content(db_session, fixture.ART_HIST_2026_NOTE)
    assert "a few times per week" in hist2026
    assert "Start propranolol 20 mg daily" in hist2026


def test_all_candidate_quotes_anchor(db_session):
    for cand in fixture.HIGHLIGHT_CANDIDATES:
        src = db_session.get(Artifact, cand["source_artifact_id"])
        assert src is not None, cand["highlight_id"]
        span = locate_span(src.content, cand["quote"])
        assert span is not None, f"{cand['highlight_id']} quote not anchored"
        assert extract_text(src.content, span) == cand["quote"]


def test_nine_highlights_seeded(db_session):
    highlights = db_session.scalars(select(Highlight)).all()
    assert len(highlights) == len(fixture.HIGHLIGHT_CANDIDATES) == 9


def test_d2_task_glance_mapping_is_explicit(db_session):
    # The blood-test Task owns exactly the blood-test highlight; no other
    # highlight carries a task_id and the mapping is never event-inferred.
    pending = db_session.get(Highlight, "hl_blood_test_pending")
    assert pending.task_id == fixture.TASK_BLOOD_TEST
    others = db_session.scalars(
        select(Highlight).where(Highlight.highlight_id != "hl_blood_test_pending")
    ).all()
    assert all(highlight.task_id is None for highlight in others)


def test_d1_demo_credentials_argon2_hashed_for_all_seeded_users(db_session):
    from app.models import UserCredential

    credentials = db_session.scalars(select(UserCredential)).all()
    assert len(credentials) == len(fixture.DEMO_EMAILS) == 6
    for credential in credentials:
        # Argon2id hash only; the shared demo password is never stored raw.
        assert credential.password_hash.startswith("$argon2")
        assert fixture.DEMO_PASSWORD not in credential.password_hash
        assert credential.email_normalized in fixture.DEMO_EMAILS.values()
