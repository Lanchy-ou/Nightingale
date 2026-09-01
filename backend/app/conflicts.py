"""Bounded, deterministic clinical-record conflict checks.

Medication/dose and task/status conflicts remain clinician-note comparisons.
Allergy conflicts additionally compare patient/AI candidates with human-authored
staff or clinician notes and confirmed Nurse Consult transcripts.  A match only
marks both statements for review; it never chooses which statement is true.
"""
from __future__ import annotations

import re

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from .extraction import normalize_entity_key
from .models import Artifact, Event

_MED_DOSE = re.compile(r"\b([a-z]+)\s+(\d+(?:\.\d+)?)\s*mg\b", re.IGNORECASE)
_TASK_STATUS = re.compile(
    r"\b(blood test|follow-?up|lab|referral)\b[^.;]*\b(pending|ordered|scheduled|done|complete|completed)\b",
    re.IGNORECASE,
)
_NO_ALLERGIES = re.compile(
    r"\b(?:no\s+(?:known\s+)?(?:drug\s+|medication\s+)?allerg(?:y|ies)|nkda)\b",
    re.IGNORECASE,
)
_NOT_ALLERGIC_TO = re.compile(
    r"\bnot\s+allergic\s+to\s+([a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*){0,2})",
    re.IGNORECASE,
)
_ALLERGIC_TO = re.compile(
    r"\ballergic\s+to\s+([a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*){0,2})",
    re.IGNORECASE,
)
_ALLERGY_TO = re.compile(
    r"\ballerg(?:y|ies)\s+to\s+([a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*){0,2})",
    re.IGNORECASE,
)
_ALLERGY_SUFFIX = re.compile(
    r"\b([a-z][a-z0-9-]*(?:\s+[a-z][a-z0-9-]*){0,2})\s+allerg(?:y|ies)\b",
    re.IGNORECASE,
)
_GENERIC_ALLERGY_TOKENS = {
    "allergy",
    "allergies",
    "drug",
    "known",
    "medication",
    "no",
    "none",
}


def _text_leaves(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for member in value.values():
            out.extend(_text_leaves(member))
        return out
    if isinstance(value, list):
        out: list[str] = []
        for member in value:
            out.extend(_text_leaves(member))
        return out
    return []


def clinical_assertion_sources(
    db: Session,
    patient_id: str,
    *,
    include_staff_and_nurse: bool = False,
) -> list[tuple[str, str]]:
    """Return newest-first clinical sources eligible for conflict review.

    Staff/clinician notes retain their distinct authority.  A Nurse Consult
    transcript is included as immutable recorded source, not as a clinician
    assessment.  Callers use the result only to flag a contradiction.
    """
    eligible = [
        and_(
            Artifact.artifact_type == "clinician_note",
            Artifact.author_role == "clinician",
        )
    ]
    if include_staff_and_nurse:
        eligible.extend(
            [
                and_(
                    Artifact.artifact_type == "staff_note",
                    Artifact.author_role == "staff",
                ),
                and_(
                    Artifact.artifact_type == "transcript",
                    Artifact.author_role == "system",
                    Event.event_type == "nurse_consult",
                ),
            ]
        )

    rows = db.execute(
        select(Artifact, Event)
        .join(Event, Artifact.event_id == Event.event_id)
        .where(
            Event.patient_id == patient_id,
            or_(*eligible),
        )
        .order_by(Event.started_at.desc(), Artifact.created_at.desc(), Artifact.artifact_id)
    ).all()
    return [
        (artifact.artifact_id, " ".join(_text_leaves(artifact.content)))
        for artifact, _event in rows
    ]


def _allergy_key(allergen: str) -> str | None:
    normalized = " ".join(
        token
        for token in re.sub(r"[^a-z0-9-]+", " ", allergen.lower()).split()
        if token not in _GENERIC_ALLERGY_TOKENS
    )
    if not normalized:
        return None
    return normalize_entity_key("allergy", normalized)


def extract_allergy_assertions(text: str) -> list[tuple[str, str]]:
    """Extract bounded positive/negative allergy statements from English text."""
    pairs: list[tuple[str, str]] = []
    if _NO_ALLERGIES.search(text):
        pairs.append(("allergy:*", "absent"))

    negative_ranges: list[tuple[int, int]] = []
    for match in _NOT_ALLERGIC_TO.finditer(text):
        key = _allergy_key(match.group(1))
        if key:
            pairs.append((key, "absent"))
            negative_ranges.append(match.span())

    for pattern in (_ALLERGIC_TO, _ALLERGY_TO, _ALLERGY_SUFFIX):
        for match in pattern.finditer(text):
            if any(start <= match.start() < end for start, end in negative_ranges):
                continue
            key = _allergy_key(match.group(1))
            if key:
                pairs.append((key, "present"))

    return list(dict.fromkeys(pairs))


def extract_entity_assertions(text: str) -> list[tuple[str, str]]:
    """Deterministically extract (entity_key, assertion_value) pairs."""
    pairs: list[tuple[str, str]] = []
    for m in _MED_DOSE.finditer(text):
        drug = m.group(1).lower()
        dose = f"{m.group(2)} mg"
        pairs.append((normalize_entity_key("medication", drug), dose))
    for m in _TASK_STATUS.finditer(text):
        pairs.append((normalize_entity_key("task", m.group(1)), m.group(2).lower()))
    pairs.extend(extract_allergy_assertions(text))
    return pairs


def _candidate_allergy_assertions(
    candidate_entity_key: str,
    candidate_assertion: str | None,
    candidate_text: str | None,
    candidate_quote: str | None,
) -> list[tuple[str, str]]:
    combined = " ".join(
        value for value in (candidate_quote, candidate_text) if isinstance(value, str)
    )
    pairs = extract_allergy_assertions(combined)
    if pairs:
        return pairs

    assertion = (candidate_assertion or "").strip().lower()
    if assertion in {"none", "no", "absent", "negative", "no known allergies", "nkda"}:
        return [("allergy:*", "absent")]
    if candidate_entity_key.startswith("allergy:") and assertion in {
        "present", "positive", "yes", "reported", "confirmed"
    }:
        suffix = candidate_entity_key.split(":", 1)[1]
        if suffix and suffix not in _GENERIC_ALLERGY_TOKENS:
            return [(candidate_entity_key, "present")]
    return []


def _allergy_conflicts(
    candidate: tuple[str, str], recorded: tuple[str, str]
) -> bool:
    candidate_key, candidate_value = candidate
    recorded_key, recorded_value = recorded
    if candidate_value == recorded_value:
        return False
    if "allergy:*" in {candidate_key, recorded_key}:
        return True
    return candidate_key == recorded_key


def find_conflict(
    candidate_entity_key: str,
    candidate_assertion: str | None,
    clinical_records: list[tuple[str, str]],
    *,
    candidate_entity_type: str | None = None,
    candidate_text: str | None = None,
    candidate_quote: str | None = None,
) -> tuple[str, str] | None:
    """Return (source_artifact_id, source_assertion) on a bounded conflict.

    A conflict exists only when both assertions are deterministically comparable.
    """
    if candidate_entity_type == "allergy" or candidate_entity_key.startswith("allergy:"):
        candidates = _candidate_allergy_assertions(
            candidate_entity_key,
            candidate_assertion,
            candidate_text,
            candidate_quote,
        )
        for artifact_id, text in clinical_records:
            recorded = extract_allergy_assertions(text)
            for candidate in candidates:
                for assertion in recorded:
                    if _allergy_conflicts(candidate, assertion):
                        return artifact_id, assertion[1]
        return None

    if not candidate_assertion:
        return None
    for artifact_id, text in clinical_records:
        for ek, av in extract_entity_assertions(text):
            if ek == candidate_entity_key and av and av != candidate_assertion:
                return artifact_id, av
    return None
