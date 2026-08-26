"""Canonical synthetic fixture — the single source of truth for M1 demo data.

Every narrative statement MUST be consistent with FACTS below. If you add
content, update FACTS and the fact assertions in tests/test_seed_integrity.py.

Facts (must never contradict each other):
  1. headache: once weekly -> near-daily (2026-08-20); severity 7/10 -> 3/10 (08-24)
  2. morning nausea: present 08-20, still persisting 08-24
  3. BP elevated 158/96: measured by nurse 08-21
  4. existing medication: propranolol 20 mg daily started 2026-02-06
  5. blood test: ordered 08-21, still pending as of 08-24
  6. follow-up: scheduled during 08-21 doctor consult
"""
from __future__ import annotations

from datetime import datetime

from app.models import Artifact, Clinic, Event, Patient, User

# ---------------------------------------------------------------------------
# IDs
# ---------------------------------------------------------------------------
CLINIC_ID = "clinic_001"
CLINIC_NAME = "Nightingale Demo Clinic"

PATIENT_ID = "pat_001"
PATIENT_NAME = "Alice Tan"

USER_PATIENT_ID = "usr_patient_01"
USER_STAFF_ID = "usr_staff_01"
USER_CLINICIAN_ID = "usr_clinician_01"
USER_ADMIN_ID = "usr_admin_01"

# Second patient (same clinic) + second clinic user, for RBAC isolation tests.
PATIENT_B_ID = "pat_002"
PATIENT_B_NAME = "Ben Lim"
USER_PATIENT_B_ID = "usr_patient_02"
CLINIC_B_ID = "clinic_002"
CLINIC_B_NAME = "Other Demo Clinic"
USER_CLINICIAN_B_ID = "usr_clinician_02"

EVT_HIST_2025 = "evt_hist_2025"
EVT_HIST_2026 = "evt_hist_2026"
EVT_PRE_0820 = "evt_pre_0820"
EVT_NURSE_0821 = "evt_nurse_0821"
EVT_DOC_0821 = "evt_doc_0821"
EVT_FU_0824 = "evt_fu_0824"
EVT_REVIEW_0826 = "evt_review_0826"

ART_HIST_2025_NOTE = "art_hist_2025_note"
ART_HIST_2026_NOTE = "art_hist_2026_note"
ART_PRE_RAW = "art_pre_raw"
ART_PRE_SUMMARY = "art_pre_summary"
ART_NURSE_TRANSCRIPT = "art_nurse_transcript"
ART_NURSE_SUMMARY = "art_nurse_summary"
ART_DOC_TRANSCRIPT = "art_doc_transcript"
ART_DOC_SUMMARY = "art_doc_summary"
ART_DOC_NOTE = "art_doc_note"
ART_DOC_INSTRUCTION = "art_doc_instruction"
ART_FU_RAW = "art_fu_raw"
ART_FU_SUMMARY = "art_fu_summary"
ART_REVIEW_NOTE = "art_review_note"
ART_REVIEW_INSTRUCTION = "art_review_instruction"

# ---------------------------------------------------------------------------
# Canonical facts (single source of truth)
# ---------------------------------------------------------------------------
FACTS = {
    "headache": "once weekly (2025-04) -> a few times per week (2026-02) -> near-daily (2026-08-20); severity 7/10 -> 3/10 by 2026-08-24",
    "nausea": "morning nausea present from 2026-08-20, still persisting 2026-08-24",
    "bp": "elevated BP 158/96 measured by nurse on 2026-08-21",
    "medication": "existing prophylactic medication (propranolol 20 mg daily) started 2026-02-06",
    "blood_test": "ordered 2026-08-21, still pending as of 2026-08-26",
    "follow_up": "scheduled during 2026-08-21 doctor consult",
    "review_0826": "clinician review 2026-08-26: severity improved to ~3/10, frequency not re-assessed, nausea persists, continue propranolol 20 mg daily, chase blood test result",
}

# ---------------------------------------------------------------------------
# Deterministic highlight candidates (M2 stub).
#
# Each candidate carries a verbatim `quote` that MUST exist in the source
# artifact. The generator locates it via string matching; a failed match drops
# the candidate (never fabricate a span).
# ---------------------------------------------------------------------------
HIGHLIGHT_CANDIDATES = [
    {
        "highlight_id": "hl_headache_worsening",
        "event_id": EVT_PRE_0820,
        "artifact_id": ART_PRE_SUMMARY,
        "source_artifact_id": ART_PRE_RAW,
        "quote": "My headaches used to happen once a week, but now they're almost every day.",
        "text": "Worsening headache frequency",
        "risk_reason": "Headache frequency increased from once weekly to near-daily",
        "feature_flags": {"recency": True, "explicit_risk": False, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": True, "repeated_mentions": False},
        "entity_type": "symptom", "entity_key": "symptom:headache frequency", "assertion_value": "worsening",
    },
    {
        "highlight_id": "hl_nausea_persists",
        "event_id": EVT_FU_0824,
        "artifact_id": ART_FU_SUMMARY,
        "source_artifact_id": ART_FU_RAW,
        "quote": "The nausea is still there in the mornings.",
        "text": "Morning nausea persists",
        "risk_reason": "Nausea still present despite headache improvement",
        "feature_flags": {"recency": True, "explicit_risk": False, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": True, "repeated_mentions": False},
        "entity_type": "symptom", "entity_key": "symptom:nausea", "assertion_value": "persistent",
    },
    {
        "highlight_id": "hl_bp_elevated",
        "event_id": EVT_NURSE_0821,
        "artifact_id": ART_NURSE_SUMMARY,
        "source_artifact_id": ART_NURSE_TRANSCRIPT,
        "quote": "Your blood pressure is 158 over 96.",
        "text": "Blood pressure elevated (158/96)",
        "risk_reason": "Elevated blood pressure measured at nurse consult",
        "feature_flags": {"recency": False, "explicit_risk": True, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "risk", "entity_key": "risk:blood pressure", "assertion_value": "158/96",
    },
    {
        "highlight_id": "hl_blood_test_pending",
        "event_id": EVT_DOC_0821,
        "artifact_id": ART_DOC_SUMMARY,
        "source_artifact_id": ART_DOC_TRANSCRIPT,
        "quote": "I'm ordering a blood test to check for any underlying causes.",
        "text": "Blood test ordered - pending",
        "risk_reason": "Blood test ordered to rule out underlying causes; result still pending",
        "feature_flags": {"recency": False, "explicit_risk": False, "unresolved_task": True, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "task", "entity_key": "task:blood test", "assertion_value": "pending",
    },
    {
        "highlight_id": "hl_followup_scheduled",
        "event_id": EVT_DOC_0821,
        "artifact_id": ART_DOC_SUMMARY,
        "source_artifact_id": ART_DOC_TRANSCRIPT,
        "quote": "We'll schedule a follow-up in a few days.",
        "text": "Follow-up scheduled",
        "risk_reason": "Follow-up appointment scheduled to review blood test results",
        "feature_flags": {"recency": False, "explicit_risk": False, "unresolved_task": True, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "task", "entity_key": "task:follow-up", "assertion_value": "scheduled",
    },
    {
        "highlight_id": "hl_medication_existing",
        "event_id": EVT_HIST_2026,
        "artifact_id": ART_HIST_2026_NOTE,
        "source_artifact_id": ART_HIST_2026_NOTE,
        "quote": "Start propranolol 20 mg daily",
        "text": "Existing medication: propranolol 20 mg daily",
        "risk_reason": "Prophylactic medication active since Feb 2026",
        "feature_flags": {"recency": False, "explicit_risk": False, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "medication", "entity_key": "medication:propranolol", "assertion_value": "20 mg daily",
    },
    {
        "highlight_id": "hl_headache_once_weekly",
        "event_id": EVT_HIST_2025,
        "artifact_id": ART_HIST_2025_NOTE,
        "source_artifact_id": ART_HIST_2025_NOTE,
        "quote": "Intermittent tension-type headaches, once weekly.",
        "text": "Headache frequency: once weekly (Apr 2025)",
        "risk_reason": "Historical baseline: once-weekly headaches at initial assessment",
        "feature_flags": {"recency": False, "explicit_risk": False, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "symptom", "entity_key": "symptom:headache frequency", "assertion_value": "once weekly",
    },
    {
        "highlight_id": "hl_headache_frequency_feb",
        "event_id": EVT_HIST_2026,
        "artifact_id": ART_HIST_2026_NOTE,
        "source_artifact_id": ART_HIST_2026_NOTE,
        "quote": "Headache frequency increased to a few times per week",
        "text": "Headache frequency increased (Feb 2026)",
        "risk_reason": "Historical context: frequency increased before propranolol was started",
        "feature_flags": {"recency": False, "explicit_risk": False, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "symptom", "entity_key": "symptom:headache frequency", "assertion_value": "a few times per week",
    },
    {
        "highlight_id": "hl_blood_test_review",
        "event_id": EVT_REVIEW_0826,
        "artifact_id": ART_REVIEW_NOTE,
        "source_artifact_id": ART_REVIEW_NOTE,
        "quote": "Blood test result is still pending",
        "text": "Blood test still pending",
        "risk_reason": "Blood test result has not returned; chase result and follow up",
        "feature_flags": {"recency": False, "explicit_risk": False, "unresolved_task": False, "clinician_confirmed": False, "symptom_change": False, "repeated_mentions": False},
        "entity_type": "task", "entity_key": "task:blood test", "assertion_value": "pending",
    },
]


def _span(kind: str, index: int) -> dict:
    return {"kind": kind, "index": index}


def build_clinics() -> list[Clinic]:
    return [
        Clinic(clinic_id=CLINIC_ID, name=CLINIC_NAME),
        Clinic(clinic_id=CLINIC_B_ID, name=CLINIC_B_NAME),
    ]


def build_users() -> list[User]:
    return [
        User(user_id=USER_PATIENT_ID, clinic_id=CLINIC_ID, name=PATIENT_NAME, role="patient", patient_id=PATIENT_ID),
        User(user_id=USER_STAFF_ID, clinic_id=CLINIC_ID, name="Bob Lee", role="staff"),
        User(user_id=USER_CLINICIAN_ID, clinic_id=CLINIC_ID, name="Dr. Carol Wong", role="clinician"),
        User(user_id=USER_ADMIN_ID, clinic_id=CLINIC_ID, name="Nightingale Admin", role="admin"),
        User(user_id=USER_PATIENT_B_ID, clinic_id=CLINIC_ID, name=PATIENT_B_NAME, role="patient", patient_id=PATIENT_B_ID),
        User(user_id=USER_CLINICIAN_B_ID, clinic_id=CLINIC_B_ID, name="Dr. Other Clinic", role="clinician"),
    ]


def build_patients() -> list[Patient]:
    return [
        Patient(patient_id=PATIENT_ID, clinic_id=CLINIC_ID, name=PATIENT_NAME),
        Patient(patient_id=PATIENT_B_ID, clinic_id=CLINIC_ID, name=PATIENT_B_NAME),
    ]


def build_events() -> list[Event]:
    return [
        Event(
            event_id=EVT_HIST_2025, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="historical_review",
            started_at=datetime(2025, 4, 15, 9, 0), ended_at=datetime(2025, 4, 15, 9, 30),
            created_at=datetime(2025, 4, 15, 9, 35),
        ),
        Event(
            event_id=EVT_HIST_2026, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="historical_review",
            started_at=datetime(2026, 2, 6, 10, 0), ended_at=datetime(2026, 2, 6, 10, 20),
            created_at=datetime(2026, 2, 6, 10, 25),
        ),
        Event(
            event_id=EVT_PRE_0820, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="patient_ai_preconsult",
            started_at=datetime(2026, 8, 20, 14, 0), ended_at=datetime(2026, 8, 20, 14, 20),
            created_at=datetime(2026, 8, 20, 14, 21),
        ),
        Event(
            event_id=EVT_NURSE_0821, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="nurse_consult",
            started_at=datetime(2026, 8, 21, 9, 0), ended_at=datetime(2026, 8, 21, 9, 15),
            created_at=datetime(2026, 8, 21, 9, 16),
        ),
        Event(
            event_id=EVT_DOC_0821, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="doctor_consult",
            started_at=datetime(2026, 8, 21, 10, 0), ended_at=datetime(2026, 8, 21, 10, 35),
            created_at=datetime(2026, 8, 21, 10, 36),
        ),
        Event(
            event_id=EVT_FU_0824, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="patient_followup",
            started_at=datetime(2026, 8, 24, 11, 0), ended_at=datetime(2026, 8, 24, 11, 15),
            created_at=datetime(2026, 8, 24, 11, 16),
        ),
        Event(
            event_id=EVT_REVIEW_0826, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="clinician_review",
            started_at=datetime(2026, 8, 26, 9, 0), ended_at=datetime(2026, 8, 26, 9, 25),
            created_at=datetime(2026, 8, 26, 9, 30),
        ),
    ]


def build_artifacts() -> list[Artifact]:
    return [
        # --- 2025-04-15 historical review ---
        Artifact(
            artifact_id=ART_HIST_2025_NOTE, event_id=EVT_HIST_2025,
            artifact_type="clinician_note", author_role="clinician", author_id=USER_CLINICIAN_ID,
            content={
                "assessment": "Intermittent tension-type headaches, once weekly. No red-flag features on initial evaluation. Neurological examination unremarkable.",
                "plan": "Headache diary; watchful waiting. Return if frequency or severity increases.",
            },
            created_at=datetime(2025, 4, 15, 9, 35), version=1, provenance_pointer=None,
        ),
        # --- 2026-02-06 medication review ---
        Artifact(
            artifact_id=ART_HIST_2026_NOTE, event_id=EVT_HIST_2026,
            artifact_type="clinician_note", author_role="clinician", author_id=USER_CLINICIAN_ID,
            content={
                "assessment": "Headache frequency increased to a few times per week since last review. Started prophylactic medication.",
                "plan": "Start propranolol 20 mg daily. Review response at next follow-up.",
            },
            created_at=datetime(2026, 2, 6, 10, 25), version=1, provenance_pointer=None,
        ),
        # --- 2026-08-20 patient AI pre-consult ---
        Artifact(
            artifact_id=ART_PRE_RAW, event_id=EVT_PRE_0820,
            artifact_type="raw_conversation", author_role="patient", author_id=USER_PATIENT_ID,
            content={
                "messages": [
                    {"id": "msg_1", "speaker": "patient", "text": "My headaches used to happen once a week, but now they're almost every day."},
                    {"id": "msg_2", "speaker": "ai", "text": "I'm sorry to hear that. When did this change start?"},
                    {"id": "msg_3", "speaker": "patient", "text": "About two weeks ago. On a bad day it's a 7 out of 10."},
                    {"id": "msg_4", "speaker": "ai", "text": "Thank you. Do you get any nausea with the headaches?"},
                    {"id": "msg_5", "speaker": "patient", "text": "Yes, I feel nauseous in the mornings."},
                    {"id": "msg_6", "speaker": "ai", "text": "Any vision changes, weakness, or numbness?"},
                    {"id": "msg_7", "speaker": "patient", "text": "No, nothing like that. I'm still taking my medication."},
                ]
            },
            created_at=datetime(2026, 8, 20, 14, 20), version=1, provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_PRE_SUMMARY, event_id=EVT_PRE_0820,
            artifact_type="ai_patient_session_summary", author_role="system", author_id=None,
            content={
                "summary": "Headache frequency increased from once weekly to near-daily over the last two weeks, with severity up to 7/10. Morning nausea present. No red-flag symptoms. Patient continues existing medication.",
                "chief_complaint": "Worsening headache frequency",
                "key_points": [
                    "Frequency: once weekly -> near-daily",
                    "Severity: up to 7/10",
                    "Morning nausea present",
                    "No red-flag symptoms",
                    "Continues existing medication",
                ],
            },
            created_at=datetime(2026, 8, 20, 14, 25), version=1,
            provenance_pointer={"event_id": EVT_PRE_0820, "artifact_id": ART_PRE_RAW, "span": _span("message", 1)},
        ),
        # --- 2026-08-21 nurse consult ---
        Artifact(
            artifact_id=ART_NURSE_TRANSCRIPT, event_id=EVT_NURSE_0821,
            artifact_type="transcript", author_role="system", author_id=None,
            content={
                "segments": [
                    {"index": 1, "speaker": "nurse", "text": "Good morning. Let me check your vitals today."},
                    {"index": 2, "speaker": "patient", "text": "Sure."},
                    {"index": 3, "speaker": "nurse", "text": "Your blood pressure is 158 over 96."},
                    {"index": 4, "speaker": "nurse", "text": "That's elevated. I'll flag it for the doctor."},
                    {"index": 5, "speaker": "patient", "text": "Okay, thank you."},
                ]
            },
            created_at=datetime(2026, 8, 21, 9, 16), version=1, provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_NURSE_SUMMARY, event_id=EVT_NURSE_0821,
            artifact_type="ai_nurse_consult_summary", author_role="system", author_id=None,
            content={
                "summary": "Vitals measured. Blood pressure elevated at 158/96 mmHg.",
                "chief_complaint": "Elevated blood pressure",
                "key_points": ["BP 158/96 mmHg", "Elevated - flagged for doctor review"],
            },
            created_at=datetime(2026, 8, 21, 9, 22), version=1,
            provenance_pointer={"event_id": EVT_NURSE_0821, "artifact_id": ART_NURSE_TRANSCRIPT, "span": _span("segment", 3)},
        ),
        # --- 2026-08-21 doctor consult ---
        Artifact(
            artifact_id=ART_DOC_TRANSCRIPT, event_id=EVT_DOC_0821,
            artifact_type="transcript", author_role="system", author_id=None,
            content={
                "segments": [
                    {"index": 1, "speaker": "doctor", "text": "Good morning. I've reviewed your pre-consult notes and the nurse's vitals."},
                    {"index": 2, "speaker": "patient", "text": "Morning, doctor."},
                    {"index": 3, "speaker": "doctor", "text": "So your headaches have gone from once a week to almost every day?"},
                    {"index": 4, "speaker": "patient", "text": "Yes, for about two weeks now."},
                    {"index": 5, "speaker": "doctor", "text": "And the nausea - is it mainly in the morning?"},
                    {"index": 6, "speaker": "patient", "text": "Yes, mostly in the morning."},
                    {"index": 7, "speaker": "doctor", "text": "Any visual changes, weakness, or numbness?"},
                    {"index": 8, "speaker": "patient", "text": "No, none of those."},
                    {"index": 9, "speaker": "doctor", "text": "The nurse recorded your blood pressure at 158 over 96."},
                    {"index": 10, "speaker": "patient", "text": "Yes, that worried me a bit."},
                    {"index": 11, "speaker": "doctor", "text": "We should keep an eye on it - it may be related to the headache changes."},
                    {"index": 12, "speaker": "patient", "text": "Okay."},
                    {"index": 13, "speaker": "doctor", "text": "You've been on propranolol 20 mg daily since February, correct?"},
                    {"index": 14, "speaker": "patient", "text": "Yes, I haven't missed any doses."},
                    {"index": 15, "speaker": "doctor", "text": "Good. We may need to adjust it, but first I want some tests."},
                    {"index": 16, "speaker": "patient", "text": "What kind of tests?"},
                    {"index": 17, "speaker": "doctor", "text": "I'm ordering a blood test to check for any underlying causes."},
                    {"index": 18, "speaker": "patient", "text": "Alright."},
                    {"index": 19, "speaker": "doctor", "text": "I'd also like to see you again after we get the results."},
                    {"index": 20, "speaker": "patient", "text": "When should I come back?"},
                    {"index": 21, "speaker": "doctor", "text": "We'll schedule a follow-up in a few days."},
                    {"index": 22, "speaker": "doctor", "text": "For now, continue your medication and keep a symptom diary."},
                    {"index": 23, "speaker": "patient", "text": "Thank you, doctor."},
                ]
            },
            created_at=datetime(2026, 8, 21, 10, 36), version=1, provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_DOC_SUMMARY, event_id=EVT_DOC_0821,
            artifact_type="ai_doctor_consult_summary", author_role="system", author_id=None,
            content={
                "summary": "Doctor consult for worsening near-daily headaches with morning nausea. BP elevated at 158/96. Blood test ordered to investigate underlying causes; follow-up scheduled after results.",
                "chief_complaint": "Worsening near-daily headache with morning nausea",
                "key_points": [
                    "Headache frequency weekly -> near-daily",
                    "Morning nausea persists",
                    "BP 158/96 elevated",
                    "Blood test ordered",
                    "Follow-up scheduled",
                ],
            },
            created_at=datetime(2026, 8, 21, 10, 42), version=1,
            provenance_pointer={"event_id": EVT_DOC_0821, "artifact_id": ART_DOC_TRANSCRIPT, "span": _span("segment", 17)},
        ),
        Artifact(
            artifact_id=ART_DOC_NOTE, event_id=EVT_DOC_0821,
            artifact_type="clinician_note", author_role="clinician", author_id=USER_CLINICIAN_ID,
            content={
                "assessment": "Near-daily tension-type headaches with morning nausea, onset over two weeks. Elevated BP 158/96. No red-flag neurological symptoms.",
                "plan": "Order blood test (FBC, thyroid, metabolic panel) to rule out underlying causes. Schedule follow-up after results. Continue propranolol 20 mg daily.",
            },
            created_at=datetime(2026, 8, 21, 10, 50), version=1, provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_DOC_INSTRUCTION, event_id=EVT_DOC_0821,
            artifact_type="patient_instruction", author_role="clinician", author_id=USER_CLINICIAN_ID,
            content={
                "instruction": "Please get the blood test done before your follow-up appointment. Continue taking propranolol 20 mg daily and keep a symptom diary of your headaches and nausea.",
                "follow_up": "Follow-up appointment scheduled in a few days to review blood test results.",
            },
            created_at=datetime(2026, 8, 21, 10, 55), version=1, provenance_pointer=None,
        ),
        # --- 2026-08-24 patient follow-up ---
        Artifact(
            artifact_id=ART_FU_RAW, event_id=EVT_FU_0824,
            artifact_type="raw_conversation", author_role="patient", author_id=USER_PATIENT_ID,
            content={
                "messages": [
                    {"id": "msg_1", "speaker": "patient", "text": "The headaches have improved - about 3 out of 10 now."},
                    {"id": "msg_2", "speaker": "ai", "text": "That's good to hear. Any nausea still?"},
                    {"id": "msg_3", "speaker": "patient", "text": "The nausea is still there in the mornings."},
                    {"id": "msg_4", "speaker": "ai", "text": "Have you done the blood test yet?"},
                    {"id": "msg_5", "speaker": "patient", "text": "Not yet, I'm waiting for my appointment."},
                ]
            },
            created_at=datetime(2026, 8, 24, 11, 16), version=1, provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_FU_SUMMARY, event_id=EVT_FU_0824,
            artifact_type="ai_patient_session_summary", author_role="system", author_id=None,
            content={
                "summary": "Headache improved to 3/10. Morning nausea persists. Blood test still pending.",
                "chief_complaint": "Persistent morning nausea",
                "key_points": [
                    "Headache severity 7/10 -> 3/10",
                    "Morning nausea persists",
                    "Blood test still pending",
                ],
            },
            created_at=datetime(2026, 8, 24, 11, 25), version=1,
            provenance_pointer={"event_id": EVT_FU_0824, "artifact_id": ART_FU_RAW, "span": _span("message", 1)},
        ),
        # --- 2026-08-26 clinician review (Event 5) ---
        Artifact(
            artifact_id=ART_REVIEW_NOTE, event_id=EVT_REVIEW_0826,
            artifact_type="clinician_note", author_role="clinician", author_id=USER_CLINICIAN_ID,
            content={
                "assessment": "Headache severity improved from 7/10 to approximately 3/10 since the doctor consult. Current headache frequency is not established in the available notes. Morning nausea persists.",
                "plan": "Continue propranolol 20 mg daily. Blood test result is still pending; chase the result and schedule follow-up once it returns.",
            },
            created_at=datetime(2026, 8, 26, 9, 30), version=1, provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_REVIEW_INSTRUCTION, event_id=EVT_REVIEW_0826,
            artifact_type="patient_instruction", author_role="clinician", author_id=USER_CLINICIAN_ID,
            content={
                "instruction": "Continue taking propranolol 20 mg daily. Complete your blood test and keep the follow-up appointment.",
                "follow_up": "Follow-up scheduled after the blood test result returns.",
            },
            created_at=datetime(2026, 8, 26, 9, 35), version=1, provenance_pointer=None,
        ),
    ]
