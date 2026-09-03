"""F1 final gate: approved patient priority reason-code stability matrix.

This is rule/workflow conformance evidence, not medical validation. Mock and
deterministic fallback are evaluated separately; live Provider remains NOT_RUN.
"""
from __future__ import annotations

from datetime import datetime

from app.checkins import _fallback_summary
from app.llm_client import MockLLMClient
from app.models import PatientCheckInMessage
from app.priority_routing import validated_priority_reason_codes
from app.redaction import RedactedContent


MATRIX = {
    "patient_explicit_worsening": {
        "clear_positive": ("My headache is getting worse.", True),
        "negation": ("My headache is not worse.", False),
        "historical_only": ("My headache was worse last year but is stable now.", False),
        "resolved": ("My headache was worse yesterday but is better now.", False),
        "ambiguous": ("Could my headache get worse in the future?", False),
        "patient_correction": ("Correction: my headache is not worse.", False),
        "multiple_people_pronouns": (
            "My mother says her headache is worse; mine is unchanged.", False
        ),
    },
    "patient_explicit_severe_intensity": {
        "clear_positive": ("My headache pain is severe.", True),
        "negation": ("My headache pain is not severe.", False),
        "historical_only": ("My headache pain was severe last year but is mild now.", False),
        "resolved": ("My headache pain was severe yesterday but is mild now.", False),
        "ambiguous": ("Could this headache become severe in the future?", False),
        "patient_correction": ("Correction: my headache pain is not severe.", False),
        "multiple_people_pronouns": (
            "My brother says his headache is severe; mine is mild.", False
        ),
    },
    "patient_requests_urgent_contact": {
        "clear_positive": ("I need urgent contact about my headache.", True),
        "negation": ("My headache is not urgent.", False),
        "historical_only": (
            "I needed urgent contact for my headache last year but I am stable now.", False
        ),
        "resolved": ("I needed urgent help earlier, but my headache is stable now.", False),
        "ambiguous": ("Should I request urgent contact if my headache changes?", False),
        "patient_correction": (
            "Correction: I do not need urgent contact for my headache.", False
        ),
        "multiple_people_pronouns": (
            "My mother needs urgent contact; my headache is unchanged.", False
        ),
    },
    "patient_reports_medication_or_allergy_concern": {
        "clear_positive": (
            "I have a medication concern because my nausea started after the medicine.", True
        ),
        "negation": (
            "I have no medication or allergy concern; my nausea is unchanged.", False
        ),
        "historical_only": (
            "I had a medication concern last year, but my nausea is stable now.", False
        ),
        "resolved": (
            "I had a medicine reaction earlier, but my nausea has resolved now.", False
        ),
        "ambiguous": ("Could this nausea be a medication concern?", False),
        "patient_correction": (
            "Correction: I have no medication or allergy concern; my nausea is unchanged.",
            False,
        ),
        "multiple_people_pronouns": (
            "My sister has a medication allergy concern; my nausea is unchanged.", False
        ),
    },
}


def _mock_codes(text: str) -> set[str]:
    result = MockLLMClient().checkin_summary(
        RedactedContent(
            content={"messages": [{"id": "msg_matrix", "speaker": "patient", "text": text}]},
            redaction_counts={},
        )
    )
    return {
        code
        for candidate in result.candidates
        for code in candidate.priority_review_reason_codes
    }


def _fallback_codes(text: str) -> set[str]:
    message = PatientCheckInMessage(
        message_id="msg_matrix",
        session_id="session_matrix",
        sequence=1,
        role="patient",
        intent="answer",
        text=text,
        question_type=None,
        conversation_action=None,
        referenced_patient_message_ids=[],
        response_to_message_id=None,
        processing_status="processed",
        generation_metadata=None,
        created_at=datetime(2026, 9, 2, 12, 0),
    )
    result = _fallback_summary([message])
    return {
        code
        for candidate in result.candidates
        for code in candidate.priority_review_reason_codes
    }


def test_mock_reason_code_stability_matrix():
    failures = []
    for code, cases in MATRIX.items():
        for case_name, (text, expected) in cases.items():
            observed = code in _mock_codes(text)
            if observed != expected:
                failures.append(
                    {"code": code, "case": case_name, "expected": expected, "observed": observed}
                )
    assert failures == []


def test_deterministic_fallback_never_claims_priority_reason_codes():
    failures = []
    for code, cases in MATRIX.items():
        for case_name, (text, _expected) in cases.items():
            observed = _fallback_codes(text)
            if observed:
                failures.append({"code": code, "case": case_name, "observed": sorted(observed)})
    assert failures == []


def test_source_span_mismatch_drops_every_priority_reason_code():
    source_text = "My headache is stable and I have no medication concern."
    mismatched_quotes = {
        "patient_explicit_worsening": "My headache is getting worse.",
        "patient_explicit_severe_intensity": "My headache pain is severe.",
        "patient_requests_urgent_contact": "I need urgent contact about my headache.",
        "patient_reports_medication_or_allergy_concern": (
            "I have a medication concern because my nausea started after the medicine."
        ),
    }
    for code, quote in mismatched_quotes.items():
        assert validated_priority_reason_codes(source_text, quote, [code]) == []
