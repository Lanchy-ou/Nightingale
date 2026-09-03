"""Fail-closed validation for patient-reported priority-review reason codes.

This validates explicit wording only. It does not determine clinical urgency or
medical truth; rejected or ambiguous codes still enter routine Nurse review.
"""
from __future__ import annotations

import re
from collections.abc import Iterable


APPROVED_PRIORITY_REASON_CODES = (
    "patient_explicit_worsening",
    "patient_explicit_severe_intensity",
    "patient_requests_urgent_contact",
    "patient_reports_medication_or_allergy_concern",
)

_OTHER_PERSON = re.compile(
    r"\b(?:mother|father|sister|brother|friend|daughter|son|partner|husband|wife|"
    r"he|she|they|his|her|their)\b",
    re.IGNORECASE,
)
_HYPOTHETICAL = re.compile(
    r"\b(?:could|might|may|maybe|possibly|should|would|what\s+if|if)\b",
    re.IGNORECASE,
)
_HISTORICAL_ONLY = re.compile(
    r"\b(?:last\s+year|years?\s+ago|in\s+the\s+past|previously|earlier|yesterday|"
    r"used\s+to|before)\b",
    re.IGNORECASE,
)
_RESOLVED = re.compile(
    r"\b(?:no\s+longer|resolved|gone)\b|"
    r"\b(?:but|and)\b.{0,32}\b(?:now|currently|today)\b.{0,32}"
    r"\b(?:better|mild|stable|resolved|gone|improved|unchanged)\b",
    re.IGNORECASE,
)

_WORSENING = re.compile(
    r"\b(?:worse|worsening|getting\s+worse|much\s+worse)\b", re.IGNORECASE
)
_SEVERE = re.compile(
    r"\b(?:severe|extreme|unbearable)\b|\b(?:9|10)\s*(?:/|out\s+of)\s*10\b",
    re.IGNORECASE,
)
_URGENT_REQUEST = re.compile(
    r"\b(?:i\s+)?need(?:\s+you)?\s+(?:an?\s+)?(?:urgent\s+)?(?:call|contact|help)\b|"
    r"\b(?:please|can\s+you|could\s+you)\s+(?:call|contact)\s+me\b|"
    r"\b(?:call|contact)\s+me\s+(?:urgently|now)\b|"
    r"\bneed\s+help\s+now\b",
    re.IGNORECASE,
)
_MEDICATION = re.compile(
    r"\b(?:medicine|medication|drug|allerg(?:y|ic)|dose|tablet|prescription)\b",
    re.IGNORECASE,
)
_MEDICATION_CONCERN = re.compile(
    r"\b(?:concern|worried|worry|reaction|side\s+effect|problem|"
    r"caused|causing|making|made|after\s+(?:taking|starting))\b",
    re.IGNORECASE,
)
_MEDICATION_ACTION_QUESTION = re.compile(
    r"\bshould\s+i\s+(?:change|stop|start|increase|decrease)\s+"
    r"(?:my\s+)?(?:medicine|medication|drug|dose|tablet|prescription)\b",
    re.IGNORECASE,
)


def _is_negated(text: str, signal: re.Pattern[str]) -> bool:
    for match in signal.finditer(text):
        prefix = text[max(0, match.start() - 40):match.start()]
        if re.search(
            r"\b(?:no|not|without|never|do\s+not|don't|did\s+not|didn't|isn't|"
            r"aren't|am\s+not|no\s+longer)\b[^.!?]{0,32}$",
            prefix,
            re.IGNORECASE,
        ):
            return True
    return False


def validated_priority_reason_codes(
    source_text: str,
    quote: str,
    proposed_codes: Iterable[str],
) -> list[str]:
    """Return only exact-source, current, explicit, self-reported codes."""
    if not quote or quote not in source_text:
        return []
    if _OTHER_PERSON.search(quote):
        return []
    if _HISTORICAL_ONLY.search(quote) or _RESOLVED.search(quote):
        return []

    hypothetical = _HYPOTHETICAL.search(quote) is not None
    detected: set[str] = set()
    if (
        not hypothetical
        and _WORSENING.search(quote)
        and not _is_negated(quote, _WORSENING)
    ):
        detected.add("patient_explicit_worsening")
    if not hypothetical and _SEVERE.search(quote) and not _is_negated(quote, _SEVERE):
        detected.add("patient_explicit_severe_intensity")
    if _URGENT_REQUEST.search(quote) and not _is_negated(quote, _URGENT_REQUEST):
        detected.add("patient_requests_urgent_contact")
    if (
        _MEDICATION.search(quote)
        and (
            _MEDICATION_ACTION_QUESTION.search(quote)
            or (not hypothetical and _MEDICATION_CONCERN.search(quote))
        )
        and not _is_negated(quote, _MEDICATION)
        and not _is_negated(quote, _MEDICATION_CONCERN)
    ):
        detected.add("patient_reports_medication_or_allergy_concern")

    proposed = set(proposed_codes)
    return [
        code
        for code in APPROVED_PRIORITY_REASON_CODES
        if code in proposed and code in detected
    ]
