"""Bounded, deterministic clinician-authority conflict check (M4).

Only compares normalized medication/dose and task/status values against clinician
notes. No LLM, no fuzzy substring similarity. If a value cannot be
deterministically normalized, it does NOT claim conflict (and does not claim
confirmation either).
"""
from __future__ import annotations

import re

from .extraction import normalize_entity_key

_MED_DOSE = re.compile(r"\b([a-z]+)\s+(\d+(?:\.\d+)?)\s*mg\b", re.IGNORECASE)
_TASK_STATUS = re.compile(
    r"\b(blood test|follow-?up|lab|referral)\b[^.;]*\b(pending|ordered|scheduled|done|complete|completed)\b",
    re.IGNORECASE,
)


def extract_entity_assertions(text: str) -> list[tuple[str, str]]:
    """Deterministically extract (entity_key, assertion_value) pairs."""
    pairs: list[tuple[str, str]] = []
    for m in _MED_DOSE.finditer(text):
        drug = m.group(1).lower()
        dose = f"{m.group(2)} mg"
        pairs.append((normalize_entity_key("medication", drug), dose))
    for m in _TASK_STATUS.finditer(text):
        pairs.append((normalize_entity_key("task", m.group(1)), m.group(2).lower()))
    return pairs


def find_conflict(
    candidate_entity_key: str,
    candidate_assertion: str | None,
    clinician_notes: list[tuple[str, str]],
) -> tuple[str, str] | None:
    """Return (clinician_artifact_id, clinician_assertion) on a bounded conflict.

    A conflict exists only when the entity keys match AND both assertions are
    deterministically comparable AND the values differ.
    """
    if not candidate_assertion:
        return None
    for artifact_id, text in clinician_notes:
        for ek, av in extract_entity_assertions(text):
            if ek == candidate_entity_key and av and av != candidate_assertion:
                return artifact_id, av
    return None
