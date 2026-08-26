"""Strict Pydantic output schema + server-side entity normalization (M4).

The LLM never controls `entity_key` or structural feature flags: the server
recomputes `entity_key` from `entity_type + normalized token`, and only trusts
`explicit_risk` / `symptom_change` suggestions from the provider.
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel

EntityType = Literal["symptom", "medication", "allergy", "chief_complaint", "task", "risk"]

ENTITY_TYPES = {"symptom", "medication", "allergy", "chief_complaint", "task", "risk"}


class Candidate(BaseModel):
    text: str
    quote: str
    risk_reason: str
    entity_type: EntityType
    entity_key: str = ""  # ignored; server recomputes
    assertion_value: str | None = None
    explicit_risk: bool = False
    symptom_change: bool = False


class AISummaryResult(BaseModel):
    summary: str
    chief_complaint: str | None = None
    candidates: list[Candidate] = []


def normalize_token(text: str) -> str:
    t = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return " ".join(t.split())


def normalize_entity_key(entity_type: str, text: str) -> str:
    return f"{entity_type}:{normalize_token(text)}"


def validate_candidate(c: Candidate) -> Candidate | None:
    """Fail closed: drop empty text/quote/reason or unknown entity types."""
    if not c.text or not c.text.strip():
        return None
    if not c.quote or not c.quote.strip():
        return None
    if not c.risk_reason or not c.risk_reason.strip():
        return None
    if c.entity_type not in ENTITY_TYPES:
        return None
    # Recompute the stable key server-side (never trust the LLM value).
    c.entity_key = normalize_entity_key(c.entity_type, c.text)
    return c
