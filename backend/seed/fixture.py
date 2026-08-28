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

from datetime import datetime, timedelta

from app.models import Artifact, AuditLog, Clinic, Comment, Event, Patient, Task, User, UserCredential
from app.auth_security import hash_password

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

# Purpose-built demo expansion. Alice remains the canonical primary story;
# these patients exercise sparse, task-heavy, dense-history, and cross-clinic
# UI states without changing any Alice fact or identifier.
PATIENT_TASK_ID = "pat_003"
PATIENT_TASK_NAME = "Maya Rahman"
USER_PATIENT_TASK_ID = "usr_patient_03"

PATIENT_DENSE_ID = "pat_004"
PATIENT_DENSE_NAME = "Daniel Koh"
USER_PATIENT_DENSE_ID = "usr_patient_04"

PATIENT_OTHER_ID = "pat_005"
PATIENT_OTHER_NAME = "Leah Ong"
USER_PATIENT_OTHER_ID = "usr_patient_05"

USER_STAFF_2_ID = "usr_staff_02"
USER_CLINICIAN_2_ID = "usr_clinician_03"

# ---------------------------------------------------------------------------
# D1 demo credentials (synthetic demo only — never real accounts).
# One shared demo password, Argon2id-hashed exactly once per process (hashing
# is deliberately expensive, and the seed runs before every test).
# ---------------------------------------------------------------------------
DEMO_PASSWORD = "nightingale-demo"

DEMO_EMAILS = {
    USER_PATIENT_ID: "alice@demo.clinic",
    USER_STAFF_ID: "staff@demo.clinic",
    USER_CLINICIAN_ID: "doctor@demo.clinic",
    USER_ADMIN_ID: "admin@demo.clinic",
    USER_PATIENT_B_ID: "ben@demo.clinic",
    USER_CLINICIAN_B_ID: "doctor@other-demo.clinic",
    USER_PATIENT_TASK_ID: "maya@demo.clinic",
    USER_PATIENT_DENSE_ID: "daniel@demo.clinic",
    USER_PATIENT_OTHER_ID: "leah@other-demo.clinic",
    USER_STAFF_2_ID: "nurse2@demo.clinic",
    USER_CLINICIAN_2_ID: "doctor2@demo.clinic",
}

_SEED_PASSWORD_HASH: str | None = None


def _seed_hash() -> str:
    global _SEED_PASSWORD_HASH
    if _SEED_PASSWORD_HASH is None:
        _SEED_PASSWORD_HASH = hash_password(DEMO_PASSWORD)
    return _SEED_PASSWORD_HASH

EVT_HIST_2025 = "evt_hist_2025"
EVT_HIST_2026 = "evt_hist_2026"
EVT_PRE_0820 = "evt_pre_0820"
EVT_NURSE_0821 = "evt_nurse_0821"
EVT_DOC_0821 = "evt_doc_0821"
EVT_FU_0824 = "evt_fu_0824"
EVT_REVIEW_0826 = "evt_review_0826"

# Explicit Clinic Visit grouping. Only this non-empty identity (never date alone)
# groups the 2026-08-21 Nurse and Doctor Consult Events.
ENCOUNTER_0821 = "enc_visit_20260821"

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

TASK_BLOOD_TEST = "task_blood_test"
TASK_SYMPTOM_DIARY = "task_symptom_diary"

EVT_MAYA_PRE = "evt_maya_pre_0810"
EVT_MAYA_NURSE = "evt_maya_nurse_0811"
EVT_MAYA_DOCTOR = "evt_maya_doctor_0811"
EVT_MAYA_FOLLOWUP = "evt_maya_followup_0818"
EVT_MAYA_REVIEW = "evt_maya_review_0827"
ENCOUNTER_MAYA_0811 = "enc_maya_20260811"

ART_MAYA_PRE_RAW = "art_maya_pre_raw"
ART_MAYA_PRE_SUMMARY = "art_maya_pre_summary"
ART_MAYA_NURSE_TRANSCRIPT = "art_maya_nurse_transcript"
ART_MAYA_STAFF_NOTE = "art_maya_staff_note"
ART_MAYA_DOCTOR_TRANSCRIPT = "art_maya_doctor_transcript"
ART_MAYA_DOCTOR_SUMMARY = "art_maya_doctor_summary"
ART_MAYA_DOCTOR_NOTE = "art_maya_doctor_note"
ART_MAYA_INSTRUCTION = "art_maya_instruction"
ART_MAYA_FOLLOWUP_RAW = "art_maya_followup_raw"
ART_MAYA_FOLLOWUP_SUMMARY = "art_maya_followup_summary"
ART_MAYA_REVIEW_NOTE = "art_maya_review_note"
ART_MAYA_REVIEW_INSTRUCTION = "art_maya_review_instruction"

TASK_MAYA_BP_LOG = "task_maya_bp_log"
TASK_MAYA_LAB_REVIEW = "task_maya_lab_review"

TASK_DANIEL_PHYSIO = "task_daniel_physio"
TASK_DANIEL_EXERCISE_LOG = "task_daniel_exercise_log"

DENSE_EVENT_SPECS = [
    ("evt_daniel_20240112", "historical_review", datetime(2024, 1, 12, 9, 0)),
    ("evt_daniel_20240418", "doctor_consult", datetime(2024, 4, 18, 10, 0)),
    ("evt_daniel_20240703", "patient_followup", datetime(2024, 7, 3, 15, 0)),
    ("evt_daniel_20241121", "clinician_review", datetime(2024, 11, 21, 11, 0)),
    ("evt_daniel_20250214", "nurse_consult", datetime(2025, 2, 14, 9, 30)),
    ("evt_daniel_20250509", "doctor_consult", datetime(2025, 5, 9, 14, 0)),
    ("evt_daniel_20250822", "patient_followup", datetime(2025, 8, 22, 16, 0)),
    ("evt_daniel_20251205", "clinician_review", datetime(2025, 12, 5, 10, 0)),
    ("evt_daniel_20260216", "historical_review", datetime(2026, 2, 16, 9, 0)),
    ("evt_daniel_20260512", "nurse_consult", datetime(2026, 5, 12, 9, 15)),
    ("evt_daniel_20260812", "doctor_consult", datetime(2026, 8, 12, 11, 0)),
    ("evt_daniel_20260825", "clinician_review", datetime(2026, 8, 25, 10, 0)),
]

EVT_DANIEL_LATEST_DOCTOR = "evt_daniel_20260812"
EVT_DANIEL_LATEST_REVIEW = "evt_daniel_20260825"
ART_DANIEL_LATEST_TRANSCRIPT = "art_daniel_20260812_transcript"
ART_DANIEL_LATEST_SUMMARY = "art_daniel_20260812_summary"
ART_DANIEL_LATEST_NOTE = "art_daniel_20260812_note"
ART_DANIEL_LATEST_INSTRUCTION = "art_daniel_20260812_instruction"
ART_DANIEL_REVIEW_NOTE = "art_daniel_20260825_note"
ART_DANIEL_REVIEW_INSTRUCTION = "art_daniel_20260825_instruction"

EVT_LEAH_PRE = "evt_leah_pre_0602"
EVT_LEAH_DOCTOR = "evt_leah_doctor_0603"
EVT_LEAH_FOLLOWUP = "evt_leah_followup_0615"
ART_LEAH_PRE_RAW = "art_leah_pre_raw"
ART_LEAH_PRE_SUMMARY = "art_leah_pre_summary"
ART_LEAH_DOCTOR_TRANSCRIPT = "art_leah_doctor_transcript"
ART_LEAH_DOCTOR_SUMMARY = "art_leah_doctor_summary"
ART_LEAH_DOCTOR_NOTE = "art_leah_doctor_note"
ART_LEAH_INSTRUCTION = "art_leah_instruction"
ART_LEAH_FOLLOWUP_RAW = "art_leah_followup_raw"
ART_LEAH_FOLLOWUP_SUMMARY = "art_leah_followup_summary"

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
    "care_tasks": "blood test task remains open; symptom diary task created 2026-08-21, patient reported done 2026-08-24, clinic verified completed 2026-08-26",
}

EXPANSION_FACTS = {
    PATIENT_TASK_ID: "Maya reports light-headedness on standing; a home blood-pressure log is reported done and awaits clinic confirmation.",
    PATIENT_DENSE_ID: "Daniel has a fixed 12-Event knee-discomfort history; the latest record notes symptoms after about twenty minutes of walking and an open physiotherapy follow-up.",
    PATIENT_OTHER_ID: "Leah belongs only to the other demo clinic and has a short synthetic wrist-recovery journey.",
}

# Hand-written C1/C2 paste demo. It adds no facts beyond FACTS and already uses
# the strict server canonical shape (0-based continuous doctor/patient segments).
C1_DEMO_DOCTOR_TRANSCRIPT = {
    "segments": [
        {"index": 0, "speaker": "doctor", "text": "How has your headache changed?"},
        {"index": 1, "speaker": "patient", "text": "It is better, about 3 out of 10, but I still feel nauseous in the morning."},
        {"index": 2, "speaker": "doctor", "text": "Have you completed the blood test?"},
        {"index": 3, "speaker": "patient", "text": "Not yet."},
        {"index": 4, "speaker": "doctor", "text": "Please continue propranolol 20 mg daily while we chase the result."},
    ]
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
        "feature_flags": {"explicit_risk": False, "symptom_change": True},
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
        "feature_flags": {"explicit_risk": False, "symptom_change": True},
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
        "feature_flags": {"explicit_risk": True, "symptom_change": False},
        "entity_type": "risk", "entity_key": "risk:blood pressure", "assertion_value": "158/96",
    },
    {
        "highlight_id": "hl_blood_test_pending",
        "event_id": EVT_DOC_0821,
        "artifact_id": ART_DOC_SUMMARY,
        "source_artifact_id": ART_DOC_TRANSCRIPT,
        "task_id": TASK_BLOOD_TEST,
        "quote": "I'm ordering a blood test to check for any underlying causes.",
        "text": "Blood test ordered - pending",
        "risk_reason": "Blood test ordered to rule out underlying causes; result still pending",
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
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
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
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
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
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
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
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
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
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
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
        "entity_type": "task", "entity_key": "task:blood test", "assertion_value": "pending",
    },
]

HIGHLIGHT_CANDIDATES += [
    {
        "highlight_id": "hl_maya_lightheaded",
        "patient_id": PATIENT_TASK_ID,
        "event_id": EVT_MAYA_PRE,
        "artifact_id": ART_MAYA_PRE_SUMMARY,
        "source_artifact_id": ART_MAYA_PRE_RAW,
        "quote": "I feel light-headed when I stand up, especially in the morning.",
        "text": "Light-headedness on standing",
        "risk_reason": "New positional symptom reported before the clinic visit",
        "feature_flags": {"explicit_risk": False, "symptom_change": True},
        "entity_type": "symptom",
        "entity_key": "symptom:light-headedness",
        "assertion_value": "on standing",
    },
    {
        "highlight_id": "hl_maya_bp_log",
        "patient_id": PATIENT_TASK_ID,
        "event_id": EVT_MAYA_DOCTOR,
        "artifact_id": ART_MAYA_DOCTOR_SUMMARY,
        "source_artifact_id": ART_MAYA_DOCTOR_TRANSCRIPT,
        "task_id": TASK_MAYA_BP_LOG,
        "quote": "Please record your blood pressure morning and evening for seven days.",
        "text": "Home blood-pressure log awaiting review",
        "risk_reason": "Patient reported the assigned log done; clinic confirmation remains pending",
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
        "entity_type": "task",
        "entity_key": "task:home blood pressure log",
        "assertion_value": "reported_done",
    },
    {
        "highlight_id": "hl_daniel_walking_discomfort",
        "patient_id": PATIENT_DENSE_ID,
        "event_id": EVT_DANIEL_LATEST_DOCTOR,
        "artifact_id": ART_DANIEL_LATEST_SUMMARY,
        "source_artifact_id": ART_DANIEL_LATEST_TRANSCRIPT,
        "quote": "The discomfort returns after about twenty minutes of walking.",
        "text": "Knee discomfort returns during longer walks",
        "risk_reason": "Current activity tolerance changed after earlier improvement",
        "feature_flags": {"explicit_risk": False, "symptom_change": True},
        "entity_type": "symptom",
        "entity_key": "symptom:knee discomfort",
        "assertion_value": "after twenty minutes walking",
    },
    {
        "highlight_id": "hl_daniel_physio",
        "patient_id": PATIENT_DENSE_ID,
        "event_id": EVT_DANIEL_LATEST_DOCTOR,
        "artifact_id": ART_DANIEL_LATEST_SUMMARY,
        "source_artifact_id": ART_DANIEL_LATEST_TRANSCRIPT,
        "task_id": TASK_DANIEL_PHYSIO,
        "quote": "Please arrange a physiotherapy follow-up and keep the exercise log going.",
        "text": "Physiotherapy follow-up remains open",
        "risk_reason": "Follow-up action is not yet completed",
        "feature_flags": {"explicit_risk": False, "symptom_change": False},
        "entity_type": "task",
        "entity_key": "task:physiotherapy follow-up",
        "assertion_value": "open",
    },
    {
        "highlight_id": "hl_leah_wrist_ache",
        "patient_id": PATIENT_OTHER_ID,
        "event_id": EVT_LEAH_PRE,
        "artifact_id": ART_LEAH_PRE_SUMMARY,
        "source_artifact_id": ART_LEAH_PRE_RAW,
        "quote": "My right wrist aches after typing, but there was no injury.",
        "text": "Wrist discomfort after typing",
        "risk_reason": "New activity-related symptom reported to the other clinic",
        "feature_flags": {"explicit_risk": False, "symptom_change": True},
        "entity_type": "symptom",
        "entity_key": "symptom:wrist discomfort",
        "assertion_value": "after typing",
    },
]


def _span(kind: str, index: int | str) -> dict:
    return {"kind": kind, "index": index}


def build_clinics() -> list[Clinic]:
    return [
        Clinic(clinic_id=CLINIC_ID, name=CLINIC_NAME),
        Clinic(clinic_id=CLINIC_B_ID, name=CLINIC_B_NAME),
    ]


def build_users() -> list[User]:
    return [
        User(user_id=USER_PATIENT_ID, clinic_id=CLINIC_ID, name=PATIENT_NAME, role="patient", patient_id=PATIENT_ID),
        User(
            user_id=USER_STAFF_ID,
            clinic_id=CLINIC_ID,
            name="Bob Lee",
            role="staff",
            professional_title="Registered Nurse",
        ),
        User(user_id=USER_CLINICIAN_ID, clinic_id=CLINIC_ID, name="Dr. Carol Wong", role="clinician"),
        User(user_id=USER_ADMIN_ID, clinic_id=CLINIC_ID, name="Nightingale Admin", role="admin"),
        User(user_id=USER_PATIENT_B_ID, clinic_id=CLINIC_ID, name=PATIENT_B_NAME, role="patient", patient_id=PATIENT_B_ID),
        User(user_id=USER_CLINICIAN_B_ID, clinic_id=CLINIC_B_ID, name="Dr. Other Clinic", role="clinician"),
        User(user_id=USER_PATIENT_TASK_ID, clinic_id=CLINIC_ID, name=PATIENT_TASK_NAME, role="patient", patient_id=PATIENT_TASK_ID),
        User(user_id=USER_PATIENT_DENSE_ID, clinic_id=CLINIC_ID, name=PATIENT_DENSE_NAME, role="patient", patient_id=PATIENT_DENSE_ID),
        User(user_id=USER_PATIENT_OTHER_ID, clinic_id=CLINIC_B_ID, name=PATIENT_OTHER_NAME, role="patient", patient_id=PATIENT_OTHER_ID),
        User(
            user_id=USER_STAFF_2_ID,
            clinic_id=CLINIC_ID,
            name="Aisha Noor",
            role="staff",
            professional_title="Registered Nurse",
        ),
        User(
            user_id=USER_CLINICIAN_2_ID,
            clinic_id=CLINIC_ID,
            name="Dr. Marcus Chen",
            role="clinician",
        ),
    ]


def build_patients() -> list[Patient]:
    return [
        Patient(patient_id=PATIENT_ID, clinic_id=CLINIC_ID, name=PATIENT_NAME),
        Patient(patient_id=PATIENT_B_ID, clinic_id=CLINIC_ID, name=PATIENT_B_NAME),
        Patient(patient_id=PATIENT_TASK_ID, clinic_id=CLINIC_ID, name=PATIENT_TASK_NAME),
        Patient(patient_id=PATIENT_DENSE_ID, clinic_id=CLINIC_ID, name=PATIENT_DENSE_NAME),
        Patient(patient_id=PATIENT_OTHER_ID, clinic_id=CLINIC_B_ID, name=PATIENT_OTHER_NAME),
    ]


def build_credentials() -> list[UserCredential]:
    """D1: seeded demo accounts so every role can log in (shared demo password)."""
    from datetime import datetime

    now = datetime(2026, 8, 26, 8, 0)
    hash_value = _seed_hash()
    return [
        UserCredential(
            user_id=user_id,
            email_normalized=email,
            password_hash=hash_value,
            created_at=now,
            password_changed_at=now,
            disabled_at=None,
        )
        for user_id, email in DEMO_EMAILS.items()
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
            event_type="nurse_consult", encounter_id=ENCOUNTER_0821,
            started_at=datetime(2026, 8, 21, 9, 0), ended_at=datetime(2026, 8, 21, 9, 15),
            created_at=datetime(2026, 8, 21, 9, 16),
        ),
        Event(
            event_id=EVT_DOC_0821, patient_id=PATIENT_ID, clinic_id=CLINIC_ID,
            event_type="doctor_consult", encounter_id=ENCOUNTER_0821,
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
    ] + _build_expansion_events()


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
                    {"index": 0, "speaker": "doctor", "text": "Good morning. I've reviewed your pre-consult notes and the nurse's vitals."},
                    {"index": 1, "speaker": "patient", "text": "Morning, doctor."},
                    {"index": 2, "speaker": "doctor", "text": "So your headaches have gone from once a week to almost every day?"},
                    {"index": 3, "speaker": "patient", "text": "Yes, for about two weeks now."},
                    {"index": 4, "speaker": "doctor", "text": "And the nausea - is it mainly in the morning?"},
                    {"index": 5, "speaker": "patient", "text": "Yes, mostly in the morning."},
                    {"index": 6, "speaker": "doctor", "text": "Any visual changes, weakness, or numbness?"},
                    {"index": 7, "speaker": "patient", "text": "No, none of those."},
                    {"index": 8, "speaker": "doctor", "text": "The nurse recorded your blood pressure at 158 over 96."},
                    {"index": 9, "speaker": "patient", "text": "Yes, that worried me a bit."},
                    {"index": 10, "speaker": "doctor", "text": "We should keep an eye on it - it may be related to the headache changes."},
                    {"index": 11, "speaker": "patient", "text": "Okay."},
                    {"index": 12, "speaker": "doctor", "text": "You've been on propranolol 20 mg daily since February, correct?"},
                    {"index": 13, "speaker": "patient", "text": "Yes, I haven't missed any doses."},
                    {"index": 14, "speaker": "doctor", "text": "Good. We may need to adjust it, but first I want some tests."},
                    {"index": 15, "speaker": "patient", "text": "What kind of tests?"},
                    {"index": 16, "speaker": "doctor", "text": "I'm ordering a blood test to check for any underlying causes."},
                    {"index": 17, "speaker": "patient", "text": "Alright."},
                    {"index": 18, "speaker": "doctor", "text": "I'd also like to see you again after we get the results."},
                    {"index": 19, "speaker": "patient", "text": "When should I come back?"},
                    {"index": 20, "speaker": "doctor", "text": "We'll schedule a follow-up in a few days."},
                    {"index": 21, "speaker": "doctor", "text": "For now, continue your medication and keep a symptom diary."},
                    {"index": 22, "speaker": "patient", "text": "Thank you, doctor."},
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
            provenance_pointer={"event_id": EVT_DOC_0821, "artifact_id": ART_DOC_TRANSCRIPT, "span": _span("segment", 16)},
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
    ] + _build_expansion_artifacts()


def build_tasks() -> list[Task]:
    """D2 canonical longitudinal actions; descriptions remain clinic-internal."""
    return [
        Task(
            task_id=TASK_BLOOD_TEST,
            patient_id=PATIENT_ID,
            clinic_id=CLINIC_ID,
            event_id=EVT_DOC_0821,
            source_artifact_id=ART_DOC_TRANSCRIPT,
            source_span={"kind": "segment", "index": 16, "offset": [0, 61]},
            title="Complete the blood test",
            description="Confirm the patient attends for the ordered blood test; result review remains a separate clinic action.",
            assigned_role="patient",
            assigned_user_id=USER_PATIENT_ID,
            patient_visible=True,
            status="open",
            due_at=datetime(2026, 8, 28, 17, 0),
            created_by=USER_CLINICIAN_ID,
            created_at=datetime(2026, 8, 21, 10, 56),
            updated_at=datetime(2026, 8, 21, 10, 56),
            reported_done_at=None,
            completed_by=None,
            completed_at=None,
            cancelled_by=None,
            cancelled_at=None,
        ),
        Task(
            task_id=TASK_SYMPTOM_DIARY,
            patient_id=PATIENT_ID,
            clinic_id=CLINIC_ID,
            event_id=EVT_DOC_0821,
            source_artifact_id=ART_DOC_INSTRUCTION,
            source_span={"kind": "section", "index": "instruction", "offset": [110, 160]},
            title="Keep a headache and nausea symptom diary",
            description="Review diary pattern at the next clinical follow-up.",
            assigned_role="patient",
            assigned_user_id=USER_PATIENT_ID,
            patient_visible=True,
            status="completed",
            due_at=datetime(2026, 8, 24, 18, 0),
            created_by=USER_CLINICIAN_ID,
            created_at=datetime(2026, 8, 21, 10, 57),
            updated_at=datetime(2026, 8, 26, 9, 40),
            reported_done_at=datetime(2026, 8, 24, 11, 20),
            completed_by=USER_CLINICIAN_ID,
            completed_at=datetime(2026, 8, 26, 9, 40),
            cancelled_by=None,
            cancelled_at=None,
        ),
    ] + _build_expansion_tasks()


def build_task_audits() -> list[AuditLog]:
    """AuditLog is the single authoritative seeded Task status history."""
    return [
        AuditLog(
            audit_id="aud_task_diary_create",
            actor_id=USER_CLINICIAN_ID,
            actor_role="clinician",
            action="task_create",
            target_type="task",
            target_id=TASK_SYMPTOM_DIARY,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            event_id=EVT_DOC_0821,
            details={"status": "open"},
            created_at=datetime(2026, 8, 21, 10, 57),
        ),
        AuditLog(
            audit_id="aud_task_diary_reported",
            actor_id=USER_PATIENT_ID,
            actor_role="patient",
            action="task_transition",
            target_type="task",
            target_id=TASK_SYMPTOM_DIARY,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            event_id=EVT_DOC_0821,
            details={"from_status": "open", "to_status": "reported_done"},
            created_at=datetime(2026, 8, 24, 11, 20),
        ),
        AuditLog(
            audit_id="aud_task_diary_completed",
            actor_id=USER_CLINICIAN_ID,
            actor_role="clinician",
            action="task_transition",
            target_type="task",
            target_id=TASK_SYMPTOM_DIARY,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            event_id=EVT_DOC_0821,
            details={"from_status": "reported_done", "to_status": "completed"},
            created_at=datetime(2026, 8, 26, 9, 40),
        ),
        AuditLog(
            audit_id="aud_task_blood_create",
            actor_id=USER_CLINICIAN_ID,
            actor_role="clinician",
            action="task_create",
            target_type="task",
            target_id=TASK_BLOOD_TEST,
            clinic_id=CLINIC_ID,
            patient_id=PATIENT_ID,
            event_id=EVT_DOC_0821,
            details={"status": "open"},
            created_at=datetime(2026, 8, 21, 10, 56),
        ),
    ] + _build_expansion_audits()


def _build_expansion_events() -> list[Event]:
    maya = [
        Event(
            event_id=EVT_MAYA_PRE,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_type="patient_ai_preconsult",
            started_at=datetime(2026, 8, 10, 8, 30),
            ended_at=datetime(2026, 8, 10, 8, 42),
            created_at=datetime(2026, 8, 10, 8, 43),
        ),
        Event(
            event_id=EVT_MAYA_NURSE,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_type="nurse_consult",
            encounter_id=ENCOUNTER_MAYA_0811,
            started_at=datetime(2026, 8, 11, 9, 0),
            ended_at=datetime(2026, 8, 11, 9, 15),
            created_at=datetime(2026, 8, 11, 9, 16),
        ),
        Event(
            event_id=EVT_MAYA_DOCTOR,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_type="doctor_consult",
            encounter_id=ENCOUNTER_MAYA_0811,
            started_at=datetime(2026, 8, 11, 9, 30),
            ended_at=datetime(2026, 8, 11, 9, 55),
            created_at=datetime(2026, 8, 11, 9, 56),
        ),
        Event(
            event_id=EVT_MAYA_FOLLOWUP,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_type="patient_followup",
            started_at=datetime(2026, 8, 18, 18, 0),
            ended_at=datetime(2026, 8, 18, 18, 10),
            created_at=datetime(2026, 8, 18, 18, 11),
        ),
        Event(
            event_id=EVT_MAYA_REVIEW,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_type="clinician_review",
            started_at=datetime(2026, 8, 27, 10, 0),
            ended_at=datetime(2026, 8, 27, 10, 20),
            created_at=datetime(2026, 8, 27, 10, 21),
        ),
    ]
    dense = [
        Event(
            event_id=event_id,
            patient_id=PATIENT_DENSE_ID,
            clinic_id=CLINIC_ID,
            event_type=event_type,
            started_at=started_at,
            ended_at=started_at + timedelta(minutes=25),
            created_at=started_at + timedelta(minutes=27),
        )
        for event_id, event_type, started_at in DENSE_EVENT_SPECS
    ]
    other_clinic = [
        Event(
            event_id=EVT_LEAH_PRE,
            patient_id=PATIENT_OTHER_ID,
            clinic_id=CLINIC_B_ID,
            event_type="patient_ai_preconsult",
            started_at=datetime(2026, 6, 2, 8, 0),
            ended_at=datetime(2026, 6, 2, 8, 10),
            created_at=datetime(2026, 6, 2, 8, 11),
        ),
        Event(
            event_id=EVT_LEAH_DOCTOR,
            patient_id=PATIENT_OTHER_ID,
            clinic_id=CLINIC_B_ID,
            event_type="doctor_consult",
            started_at=datetime(2026, 6, 3, 14, 0),
            ended_at=datetime(2026, 6, 3, 14, 25),
            created_at=datetime(2026, 6, 3, 14, 26),
        ),
        Event(
            event_id=EVT_LEAH_FOLLOWUP,
            patient_id=PATIENT_OTHER_ID,
            clinic_id=CLINIC_B_ID,
            event_type="patient_followup",
            started_at=datetime(2026, 6, 15, 17, 0),
            ended_at=datetime(2026, 6, 15, 17, 10),
            created_at=datetime(2026, 6, 15, 17, 11),
        ),
    ]
    return maya + dense + other_clinic


def _build_expansion_artifacts() -> list[Artifact]:
    return _build_maya_artifacts() + _build_daniel_artifacts() + _build_leah_artifacts()


def _build_maya_artifacts() -> list[Artifact]:
    return [
        Artifact(
            artifact_id=ART_MAYA_PRE_RAW,
            event_id=EVT_MAYA_PRE,
            artifact_type="raw_conversation",
            author_role="patient",
            author_id=USER_PATIENT_TASK_ID,
            content={
                "messages": [
                    {"id": "maya_msg_1", "speaker": "patient", "text": "I feel light-headed when I stand up, especially in the morning."},
                    {"id": "maya_msg_2", "speaker": "ai", "text": "When did you first notice that change?"},
                    {"id": "maya_msg_3", "speaker": "patient", "text": "It started four days ago. I have not fainted."},
                    {"id": "maya_msg_4", "speaker": "ai", "text": "Have you recorded any blood-pressure readings at home?"},
                    {"id": "maya_msg_5", "speaker": "patient", "text": "Not yet. I would like the clinic to check it."},
                ]
            },
            created_at=datetime(2026, 8, 10, 8, 42),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_PRE_SUMMARY,
            event_id=EVT_MAYA_PRE,
            artifact_type="ai_patient_session_summary",
            author_role="system",
            author_id=None,
            content={
                "summary": "Patient reports four days of light-headedness on standing, mainly in the morning, without fainting. No home blood-pressure log is available.",
                "chief_complaint": "Light-headedness on standing",
                "key_points": ["Started four days ago", "No fainting reported", "No home readings yet"],
            },
            created_at=datetime(2026, 8, 10, 8, 45),
            version=1,
            provenance_pointer={"event_id": EVT_MAYA_PRE, "artifact_id": ART_MAYA_PRE_RAW, "span": _span("message", "maya_msg_1")},
        ),
        Artifact(
            artifact_id=ART_MAYA_NURSE_TRANSCRIPT,
            event_id=EVT_MAYA_NURSE,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content={
                "segments": [
                    {"index": 0, "speaker": "nurse", "text": "I will record your seated and standing observations."},
                    {"index": 1, "speaker": "patient", "text": "Thank you. The light-headed feeling is brief."},
                    {"index": 2, "speaker": "nurse", "text": "Please stand slowly while I repeat the measurement."},
                    {"index": 3, "speaker": "patient", "text": "I feel steady now."},
                ]
            },
            created_at=datetime(2026, 8, 11, 9, 16),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_STAFF_NOTE,
            event_id=EVT_MAYA_NURSE,
            artifact_type="staff_note",
            author_role="staff",
            author_id=USER_STAFF_2_ID,
            content={
                "observation": "Brief positional light-headedness reported. Patient remained steady during repeated observations.",
                "handoff": "Doctor review requested; no interpretation or care-plan change recorded by staff.",
            },
            created_at=datetime(2026, 8, 11, 9, 20),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_DOCTOR_TRANSCRIPT,
            event_id=EVT_MAYA_DOCTOR,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content={
                "segments": [
                    {"index": 0, "speaker": "doctor", "text": "Tell me what happens when you stand."},
                    {"index": 1, "speaker": "patient", "text": "I feel light-headed for a few seconds, mostly in the morning."},
                    {"index": 2, "speaker": "doctor", "text": "Have you fainted or fallen?"},
                    {"index": 3, "speaker": "patient", "text": "No, I have not fainted or fallen."},
                    {"index": 4, "speaker": "doctor", "text": "We will review the pattern rather than change treatment from this conversation alone."},
                    {"index": 5, "speaker": "patient", "text": "What should I do next?"},
                    {"index": 6, "speaker": "doctor", "text": "Please record your blood pressure morning and evening for seven days."},
                    {"index": 7, "speaker": "doctor", "text": "Contact the clinic sooner if the symptoms worsen or you faint."},
                ]
            },
            created_at=datetime(2026, 8, 11, 9, 56),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_DOCTOR_SUMMARY,
            event_id=EVT_MAYA_DOCTOR,
            artifact_type="ai_doctor_consult_summary",
            author_role="system",
            author_id=None,
            content={
                "summary": "Brief positional light-headedness without fainting or falls. A seven-day home blood-pressure log was requested for clinician review.",
                "chief_complaint": "Positional light-headedness",
                "key_points": ["No fainting", "No falls", "Seven-day home log requested"],
            },
            created_at=datetime(2026, 8, 11, 10, 0),
            version=1,
            provenance_pointer={"event_id": EVT_MAYA_DOCTOR, "artifact_id": ART_MAYA_DOCTOR_TRANSCRIPT, "span": _span("segment", 6)},
        ),
        Artifact(
            artifact_id=ART_MAYA_DOCTOR_NOTE,
            event_id=EVT_MAYA_DOCTOR,
            artifact_type="clinician_note",
            author_role="clinician",
            author_id=USER_CLINICIAN_2_ID,
            content={
                "assessment": "New brief positional light-headedness. No reported fainting or falls. Staff observations reviewed.",
                "plan": "Collect a seven-day home blood-pressure log and review before making any treatment change.",
            },
            created_at=datetime(2026, 8, 11, 10, 4),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_INSTRUCTION,
            event_id=EVT_MAYA_DOCTOR,
            artifact_type="patient_instruction",
            author_role="clinician",
            author_id=USER_CLINICIAN_2_ID,
            content={
                "instruction": "Record your blood pressure in the morning and evening for seven days, then report when the log is ready for clinic review.",
                "follow_up": "Contact the clinic sooner if symptoms worsen or if you faint.",
            },
            created_at=datetime(2026, 8, 11, 10, 6),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_FOLLOWUP_RAW,
            event_id=EVT_MAYA_FOLLOWUP,
            artifact_type="raw_conversation",
            author_role="patient",
            author_id=USER_PATIENT_TASK_ID,
            content={
                "messages": [
                    {"id": "maya_fu_1", "speaker": "patient", "text": "I completed the seven-day blood-pressure log."},
                    {"id": "maya_fu_2", "speaker": "ai", "text": "Has the light-headed feeling changed?"},
                    {"id": "maya_fu_3", "speaker": "patient", "text": "It happens less often, and I have not fainted."},
                ]
            },
            created_at=datetime(2026, 8, 18, 18, 11),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_FOLLOWUP_SUMMARY,
            event_id=EVT_MAYA_FOLLOWUP,
            artifact_type="ai_patient_session_summary",
            author_role="system",
            author_id=None,
            content={
                "summary": "Patient reports the seven-day log is complete. Light-headedness occurs less often and no fainting is reported.",
                "chief_complaint": "Follow-up on positional symptoms",
                "key_points": ["Home log complete", "Symptoms less frequent", "No fainting"],
            },
            created_at=datetime(2026, 8, 18, 18, 14),
            version=1,
            provenance_pointer={"event_id": EVT_MAYA_FOLLOWUP, "artifact_id": ART_MAYA_FOLLOWUP_RAW, "span": _span("message", "maya_fu_1")},
        ),
        Artifact(
            artifact_id=ART_MAYA_REVIEW_NOTE,
            event_id=EVT_MAYA_REVIEW,
            artifact_type="clinician_note",
            author_role="clinician",
            author_id=USER_CLINICIAN_2_ID,
            content={
                "assessment": "Home log received for review. Patient reports less frequent positional light-headedness and no fainting.",
                "plan": "Review the submitted readings and confirm the next step with the patient; no automatic care-plan change.",
            },
            created_at=datetime(2026, 8, 27, 10, 21),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_MAYA_REVIEW_INSTRUCTION,
            event_id=EVT_MAYA_REVIEW,
            artifact_type="patient_instruction",
            author_role="clinician",
            author_id=USER_CLINICIAN_2_ID,
            content={
                "instruction": "Keep the completed home log available while the clinic reviews it.",
                "follow_up": "The clinic will confirm the next step after reviewing the readings.",
            },
            created_at=datetime(2026, 8, 27, 10, 24),
            version=1,
            provenance_pointer=None,
        ),
    ]


def _build_daniel_artifacts() -> list[Artifact]:
    early_specs = [
        ("evt_daniel_20240112", "historical_review", "Intermittent right-knee discomfort after long walks; no injury reported.", "Use an activity diary and return if function worsens."),
        ("evt_daniel_20240418", "doctor_consult", "Activity-related knee discomfort without locking or instability.", "Begin a guided exercise programme and review progress."),
        ("evt_daniel_20240703", "patient_followup", "Exercises are easier and walking tolerance has improved.", "Continue the agreed programme and record longer walks."),
        ("evt_daniel_20241121", "clinician_review", "Improved function with occasional discomfort after prolonged activity.", "Continue activity pacing and review if symptoms change."),
        ("evt_daniel_20250214", "nurse_consult", "Patient reports completing the exercise diary; no new functional concern raised.", "Diary available for clinician review; staff made no plan change."),
        ("evt_daniel_20250509", "doctor_consult", "Mild recurrence after increasing weekend walking distance.", "Restart the exercise log and arrange a routine review."),
        ("evt_daniel_20250822", "patient_followup", "Exercise log completed; discomfort settles with rest.", "Continue current pacing while awaiting routine review."),
        ("evt_daniel_20251205", "clinician_review", "Stable activity-related symptoms with preserved daily function.", "Continue exercises and return if swelling, locking, or instability develops."),
        ("evt_daniel_20260216", "historical_review", "Longitudinal review confirms fluctuating activity-related discomfort and no recorded acute injury.", "Maintain the existing exercise plan and reassess activity tolerance."),
        ("evt_daniel_20260512", "nurse_consult", "Patient reports mild swelling after a long walk, improving by the next day.", "Documented for clinician review; no staff-authored clinical assessment."),
    ]
    artifacts: list[Artifact] = []
    event_times = {event_id: started_at for event_id, _event_type, started_at in DENSE_EVENT_SPECS}
    for index, (event_id, event_type, assessment, plan) in enumerate(early_specs, start=1):
        created_at = event_times[event_id] + timedelta(minutes=27)
        artifact_id = f"art_daniel_{index:02d}"
        if event_type == "patient_followup":
            artifacts.append(
                Artifact(
                    artifact_id=artifact_id,
                    event_id=event_id,
                    artifact_type="raw_conversation",
                    author_role="patient",
                    author_id=USER_PATIENT_DENSE_ID,
                    content={"messages": [{"id": f"daniel_msg_{index}", "speaker": "patient", "text": assessment}]},
                    created_at=created_at,
                    version=1,
                    provenance_pointer=None,
                )
            )
        elif event_type == "nurse_consult":
            artifacts.append(
                Artifact(
                    artifact_id=artifact_id,
                    event_id=event_id,
                    artifact_type="staff_note",
                    author_role="staff",
                    author_id=USER_STAFF_ID if index % 2 else USER_STAFF_2_ID,
                    content={"observation": assessment, "handoff": plan},
                    created_at=created_at,
                    version=1,
                    provenance_pointer=None,
                )
            )
        else:
            artifacts.append(
                Artifact(
                    artifact_id=artifact_id,
                    event_id=event_id,
                    artifact_type="clinician_note",
                    author_role="clinician",
                    author_id=USER_CLINICIAN_ID if index % 2 else USER_CLINICIAN_2_ID,
                    content={"assessment": assessment, "plan": plan},
                    created_at=created_at,
                    version=1,
                    provenance_pointer=None,
                )
            )

    artifacts.extend(
        [
            Artifact(
                artifact_id=ART_DANIEL_LATEST_TRANSCRIPT,
                event_id=EVT_DANIEL_LATEST_DOCTOR,
                artifact_type="transcript",
                author_role="system",
                author_id=None,
                content={
                    "segments": [
                        {"index": 0, "speaker": "doctor", "text": "How has the knee felt since the last review?"},
                        {"index": 1, "speaker": "patient", "text": "Most daily activities are comfortable."},
                        {"index": 2, "speaker": "doctor", "text": "What happens during a longer walk?"},
                        {"index": 3, "speaker": "patient", "text": "The discomfort returns after about twenty minutes of walking."},
                        {"index": 4, "speaker": "doctor", "text": "Any locking, giving way, or new injury?"},
                        {"index": 5, "speaker": "patient", "text": "No locking, no giving way, and no injury."},
                        {"index": 6, "speaker": "doctor", "text": "Has the swelling changed?"},
                        {"index": 7, "speaker": "patient", "text": "It settles by the next morning."},
                        {"index": 8, "speaker": "doctor", "text": "Are you still using the exercise log?"},
                        {"index": 9, "speaker": "patient", "text": "Yes, I record the longer walks and the exercises."},
                        {"index": 10, "speaker": "doctor", "text": "Please arrange a physiotherapy follow-up and keep the exercise log going."},
                        {"index": 11, "speaker": "patient", "text": "I can do that."},
                        {"index": 12, "speaker": "doctor", "text": "Return sooner if function worsens or the knee becomes unstable."},
                        {"index": 13, "speaker": "patient", "text": "Understood."},
                    ]
                },
                created_at=datetime(2026, 8, 12, 11, 27),
                version=1,
                provenance_pointer=None,
            ),
            Artifact(
                artifact_id=ART_DANIEL_LATEST_SUMMARY,
                event_id=EVT_DANIEL_LATEST_DOCTOR,
                artifact_type="ai_doctor_consult_summary",
                author_role="system",
                author_id=None,
                content={
                    "summary": "Daily function remains comfortable, but right-knee discomfort returns after about twenty minutes of walking. No new injury, locking, or instability is reported. Physiotherapy follow-up was requested.",
                    "chief_complaint": "Activity-related right-knee discomfort",
                    "key_points": ["Daily function preserved", "Symptoms during longer walks", "No locking or instability", "Physiotherapy follow-up requested"],
                },
                created_at=datetime(2026, 8, 12, 11, 31),
                version=1,
                provenance_pointer={"event_id": EVT_DANIEL_LATEST_DOCTOR, "artifact_id": ART_DANIEL_LATEST_TRANSCRIPT, "span": _span("segment", 3)},
            ),
            Artifact(
                artifact_id=ART_DANIEL_LATEST_NOTE,
                event_id=EVT_DANIEL_LATEST_DOCTOR,
                artifact_type="clinician_note",
                author_role="clinician",
                author_id=USER_CLINICIAN_ID,
                content={
                    "assessment": "Recurrent activity-related right-knee discomfort after longer walks. Daily function preserved; no reported locking, instability, or acute injury.",
                    "plan": "Arrange physiotherapy follow-up, continue the exercise log, and review sooner if function worsens.",
                },
                created_at=datetime(2026, 8, 12, 11, 35),
                version=1,
                provenance_pointer=None,
            ),
            Artifact(
                artifact_id=ART_DANIEL_LATEST_INSTRUCTION,
                event_id=EVT_DANIEL_LATEST_DOCTOR,
                artifact_type="patient_instruction",
                author_role="clinician",
                author_id=USER_CLINICIAN_ID,
                content={
                    "instruction": "Continue your exercise log and arrange the physiotherapy follow-up.",
                    "follow_up": "Contact the clinic sooner if walking function worsens or the knee becomes unstable.",
                },
                created_at=datetime(2026, 8, 12, 11, 38),
                version=1,
                provenance_pointer=None,
            ),
            Artifact(
                artifact_id=ART_DANIEL_REVIEW_NOTE,
                event_id=EVT_DANIEL_LATEST_REVIEW,
                artifact_type="clinician_note",
                author_role="clinician",
                author_id=USER_CLINICIAN_2_ID,
                content={
                    "assessment": "Swelling is less than last week. The physiotherapy follow-up remains open and the exercise log is current.",
                    "plan": "Keep the existing plan and review after physiotherapy feedback is available.",
                },
                created_at=datetime(2026, 8, 25, 10, 27),
                version=1,
                provenance_pointer=None,
            ),
            Artifact(
                artifact_id=ART_DANIEL_REVIEW_INSTRUCTION,
                event_id=EVT_DANIEL_LATEST_REVIEW,
                artifact_type="patient_instruction",
                author_role="clinician",
                author_id=USER_CLINICIAN_2_ID,
                content={
                    "instruction": "Continue the exercise log while waiting for physiotherapy follow-up.",
                    "follow_up": "The clinic will review the plan after physiotherapy feedback is available.",
                },
                created_at=datetime(2026, 8, 25, 10, 30),
                version=1,
                provenance_pointer=None,
            ),
        ]
    )
    return artifacts


def _build_leah_artifacts() -> list[Artifact]:
    return [
        Artifact(
            artifact_id=ART_LEAH_PRE_RAW,
            event_id=EVT_LEAH_PRE,
            artifact_type="raw_conversation",
            author_role="patient",
            author_id=USER_PATIENT_OTHER_ID,
            content={
                "messages": [
                    {"id": "leah_msg_1", "speaker": "patient", "text": "My right wrist aches after typing, but there was no injury."},
                    {"id": "leah_msg_2", "speaker": "ai", "text": "How long has that been happening?"},
                    {"id": "leah_msg_3", "speaker": "patient", "text": "About one week, and it eases when I stop typing."},
                ]
            },
            created_at=datetime(2026, 6, 2, 8, 10),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_LEAH_PRE_SUMMARY,
            event_id=EVT_LEAH_PRE,
            artifact_type="ai_patient_session_summary",
            author_role="system",
            author_id=None,
            content={
                "summary": "One week of right-wrist discomfort after typing, easing with rest, without a reported injury.",
                "chief_complaint": "Right-wrist discomfort",
                "key_points": ["Activity related", "Eases with rest", "No injury reported"],
            },
            created_at=datetime(2026, 6, 2, 8, 13),
            version=1,
            provenance_pointer={"event_id": EVT_LEAH_PRE, "artifact_id": ART_LEAH_PRE_RAW, "span": _span("message", "leah_msg_1")},
        ),
        Artifact(
            artifact_id=ART_LEAH_DOCTOR_TRANSCRIPT,
            event_id=EVT_LEAH_DOCTOR,
            artifact_type="transcript",
            author_role="system",
            author_id=None,
            content={
                "segments": [
                    {"index": 0, "speaker": "doctor", "text": "Which activity brings on the wrist discomfort?"},
                    {"index": 1, "speaker": "patient", "text": "Typing for a long time."},
                    {"index": 2, "speaker": "doctor", "text": "Any injury, weakness, or persistent numbness?"},
                    {"index": 3, "speaker": "patient", "text": "No injury, weakness, or persistent numbness."},
                    {"index": 4, "speaker": "doctor", "text": "Use regular breaks and keep a short activity log for review."},
                    {"index": 5, "speaker": "patient", "text": "I will do that."},
                ]
            },
            created_at=datetime(2026, 6, 3, 14, 26),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_LEAH_DOCTOR_SUMMARY,
            event_id=EVT_LEAH_DOCTOR,
            artifact_type="ai_doctor_consult_summary",
            author_role="system",
            author_id=None,
            content={
                "summary": "Typing-related right-wrist discomfort without reported injury, weakness, or persistent numbness. Regular breaks and an activity log were advised.",
                "chief_complaint": "Typing-related wrist discomfort",
                "key_points": ["No injury", "No weakness", "Regular breaks advised"],
            },
            created_at=datetime(2026, 6, 3, 14, 30),
            version=1,
            provenance_pointer={"event_id": EVT_LEAH_DOCTOR, "artifact_id": ART_LEAH_DOCTOR_TRANSCRIPT, "span": _span("segment", 1)},
        ),
        Artifact(
            artifact_id=ART_LEAH_DOCTOR_NOTE,
            event_id=EVT_LEAH_DOCTOR,
            artifact_type="clinician_note",
            author_role="clinician",
            author_id=USER_CLINICIAN_B_ID,
            content={
                "assessment": "Activity-related right-wrist discomfort without reported acute injury or persistent neurological symptom.",
                "plan": "Regular typing breaks and a short activity log; review if symptoms persist or function changes.",
            },
            created_at=datetime(2026, 6, 3, 14, 34),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_LEAH_INSTRUCTION,
            event_id=EVT_LEAH_DOCTOR,
            artifact_type="patient_instruction",
            author_role="clinician",
            author_id=USER_CLINICIAN_B_ID,
            content={
                "instruction": "Take regular breaks from typing and keep a short activity log.",
                "follow_up": "Contact your clinic if symptoms persist or hand function changes.",
            },
            created_at=datetime(2026, 6, 3, 14, 36),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_LEAH_FOLLOWUP_RAW,
            event_id=EVT_LEAH_FOLLOWUP,
            artifact_type="raw_conversation",
            author_role="patient",
            author_id=USER_PATIENT_OTHER_ID,
            content={"messages": [{"id": "leah_fu_1", "speaker": "patient", "text": "The wrist discomfort is less frequent when I take regular breaks."}]},
            created_at=datetime(2026, 6, 15, 17, 11),
            version=1,
            provenance_pointer=None,
        ),
        Artifact(
            artifact_id=ART_LEAH_FOLLOWUP_SUMMARY,
            event_id=EVT_LEAH_FOLLOWUP,
            artifact_type="ai_patient_session_summary",
            author_role="system",
            author_id=None,
            content={
                "summary": "Patient reports less frequent wrist discomfort when taking regular typing breaks.",
                "chief_complaint": "Wrist follow-up",
                "key_points": ["Less frequent discomfort", "Regular breaks helpful"],
            },
            created_at=datetime(2026, 6, 15, 17, 14),
            version=1,
            provenance_pointer={"event_id": EVT_LEAH_FOLLOWUP, "artifact_id": ART_LEAH_FOLLOWUP_RAW, "span": _span("message", "leah_fu_1")},
        ),
    ]


def _build_expansion_tasks() -> list[Task]:
    maya_quote = "Please record your blood pressure morning and evening for seven days."
    daniel_quote = "Please arrange a physiotherapy follow-up and keep the exercise log going."
    return [
        Task(
            task_id=TASK_MAYA_BP_LOG,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_id=EVT_MAYA_DOCTOR,
            source_artifact_id=ART_MAYA_DOCTOR_TRANSCRIPT,
            source_span={"kind": "segment", "index": 6, "offset": [0, len(maya_quote)]},
            title="Complete the seven-day blood-pressure log",
            description="Clinic review is required after the patient reports the log ready.",
            assigned_role="patient",
            assigned_user_id=USER_PATIENT_TASK_ID,
            patient_visible=True,
            status="reported_done",
            due_at=datetime(2026, 8, 18, 20, 0),
            created_by=USER_CLINICIAN_2_ID,
            created_at=datetime(2026, 8, 11, 10, 7),
            updated_at=datetime(2026, 8, 18, 18, 12),
            reported_done_at=datetime(2026, 8, 18, 18, 12),
            completed_by=None,
            completed_at=None,
            cancelled_by=None,
            cancelled_at=None,
        ),
        Task(
            task_id=TASK_MAYA_LAB_REVIEW,
            patient_id=PATIENT_TASK_ID,
            clinic_id=CLINIC_ID,
            event_id=EVT_MAYA_REVIEW,
            source_artifact_id=None,
            source_span=None,
            title="Review Maya's submitted home readings",
            description="Staff queue action; reviewing the readings does not automatically change the care plan.",
            assigned_role="staff",
            assigned_user_id=USER_STAFF_2_ID,
            patient_visible=False,
            status="open",
            due_at=datetime(2026, 8, 29, 12, 0),
            created_by=USER_CLINICIAN_2_ID,
            created_at=datetime(2026, 8, 27, 10, 25),
            updated_at=datetime(2026, 8, 27, 10, 25),
            reported_done_at=None,
            completed_by=None,
            completed_at=None,
            cancelled_by=None,
            cancelled_at=None,
        ),
        Task(
            task_id=TASK_DANIEL_PHYSIO,
            patient_id=PATIENT_DENSE_ID,
            clinic_id=CLINIC_ID,
            event_id=EVT_DANIEL_LATEST_DOCTOR,
            source_artifact_id=ART_DANIEL_LATEST_TRANSCRIPT,
            source_span={"kind": "segment", "index": 10, "offset": [0, len(daniel_quote)]},
            title="Arrange physiotherapy follow-up",
            description="Confirm a routine physiotherapy follow-up is arranged and retain exact Event provenance.",
            assigned_role="patient",
            assigned_user_id=USER_PATIENT_DENSE_ID,
            patient_visible=True,
            status="open",
            due_at=datetime(2026, 9, 2, 17, 0),
            created_by=USER_CLINICIAN_ID,
            created_at=datetime(2026, 8, 12, 11, 39),
            updated_at=datetime(2026, 8, 12, 11, 39),
            reported_done_at=None,
            completed_by=None,
            completed_at=None,
            cancelled_by=None,
            cancelled_at=None,
        ),
        Task(
            task_id=TASK_DANIEL_EXERCISE_LOG,
            patient_id=PATIENT_DENSE_ID,
            clinic_id=CLINIC_ID,
            event_id="evt_daniel_20250509",
            source_artifact_id=None,
            source_span=None,
            title="Complete the two-week exercise log",
            description="Historical patient-visible action retained to demonstrate a completed Task lifecycle.",
            assigned_role="patient",
            assigned_user_id=USER_PATIENT_DENSE_ID,
            patient_visible=True,
            status="completed",
            due_at=datetime(2025, 8, 22, 17, 0),
            created_by=USER_CLINICIAN_2_ID,
            created_at=datetime(2025, 5, 9, 14, 30),
            updated_at=datetime(2025, 8, 25, 9, 0),
            reported_done_at=datetime(2025, 8, 22, 16, 10),
            completed_by=USER_CLINICIAN_2_ID,
            completed_at=datetime(2025, 8, 25, 9, 0),
            cancelled_by=None,
            cancelled_at=None,
        ),
    ]


def _build_expansion_audits() -> list[AuditLog]:
    specs = [
        ("aud_maya_bp_create", USER_CLINICIAN_2_ID, "clinician", "task_create", TASK_MAYA_BP_LOG, PATIENT_TASK_ID, EVT_MAYA_DOCTOR, {"status": "open"}, datetime(2026, 8, 11, 10, 7)),
        ("aud_maya_bp_reported", USER_PATIENT_TASK_ID, "patient", "task_transition", TASK_MAYA_BP_LOG, PATIENT_TASK_ID, EVT_MAYA_DOCTOR, {"from_status": "open", "to_status": "reported_done"}, datetime(2026, 8, 18, 18, 12)),
        ("aud_maya_review_create", USER_CLINICIAN_2_ID, "clinician", "task_create", TASK_MAYA_LAB_REVIEW, PATIENT_TASK_ID, EVT_MAYA_REVIEW, {"status": "open"}, datetime(2026, 8, 27, 10, 25)),
        ("aud_daniel_physio_create", USER_CLINICIAN_ID, "clinician", "task_create", TASK_DANIEL_PHYSIO, PATIENT_DENSE_ID, EVT_DANIEL_LATEST_DOCTOR, {"status": "open"}, datetime(2026, 8, 12, 11, 39)),
        ("aud_daniel_log_create", USER_CLINICIAN_2_ID, "clinician", "task_create", TASK_DANIEL_EXERCISE_LOG, PATIENT_DENSE_ID, "evt_daniel_20250509", {"status": "open"}, datetime(2025, 5, 9, 14, 30)),
        ("aud_daniel_log_reported", USER_PATIENT_DENSE_ID, "patient", "task_transition", TASK_DANIEL_EXERCISE_LOG, PATIENT_DENSE_ID, "evt_daniel_20250509", {"from_status": "open", "to_status": "reported_done"}, datetime(2025, 8, 22, 16, 10)),
        ("aud_daniel_log_completed", USER_CLINICIAN_2_ID, "clinician", "task_transition", TASK_DANIEL_EXERCISE_LOG, PATIENT_DENSE_ID, "evt_daniel_20250509", {"from_status": "reported_done", "to_status": "completed"}, datetime(2025, 8, 25, 9, 0)),
    ]
    return [
        AuditLog(
            audit_id=audit_id,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            target_type="task",
            target_id=target_id,
            clinic_id=CLINIC_ID,
            patient_id=patient_id,
            event_id=event_id,
            details=details,
            created_at=created_at,
        )
        for audit_id, actor_id, actor_role, action, target_id, patient_id, event_id, details, created_at in specs
    ]


def build_comments() -> list[Comment]:
    return [
        Comment(
            comment_id="comment_maya_staff_handoff",
            anchor_type="event",
            anchor_id=EVT_MAYA_DOCTOR,
            parent_comment_id=None,
            author_id=USER_STAFF_2_ID,
            author_role="staff",
            body="Home-reading instructions were reviewed with the patient; the clinic still needs to confirm the submitted log.",
            mentions=[USER_CLINICIAN_2_ID],
            resolved=True,
            created_at=datetime(2026, 8, 11, 10, 8),
            resolved_at=datetime(2026, 8, 27, 10, 22),
            resolved_by=USER_CLINICIAN_2_ID,
        ),
        Comment(
            comment_id="comment_maya_clinician_reply",
            anchor_type="event",
            anchor_id=EVT_MAYA_DOCTOR,
            parent_comment_id="comment_maya_staff_handoff",
            author_id=USER_CLINICIAN_2_ID,
            author_role="clinician",
            body="Acknowledged. The submitted readings remain queued for clinical review.",
            mentions=[],
            resolved=True,
            created_at=datetime(2026, 8, 27, 10, 22),
            resolved_at=datetime(2026, 8, 27, 10, 22),
            resolved_by=USER_CLINICIAN_2_ID,
        ),
        Comment(
            comment_id="comment_daniel_physio",
            anchor_type="artifact",
            anchor_id=ART_DANIEL_LATEST_INSTRUCTION,
            parent_comment_id=None,
            author_id=USER_STAFF_ID,
            author_role="staff",
            body="Physiotherapy follow-up is still awaiting confirmation; no care-plan change has been made.",
            mentions=[USER_CLINICIAN_ID],
            resolved=False,
            created_at=datetime(2026, 8, 25, 10, 31),
            resolved_at=None,
            resolved_by=None,
        ),
    ]
