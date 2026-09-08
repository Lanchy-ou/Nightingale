"""Strict Pydantic output schema + server-side entity normalization (M4).

The LLM never controls `entity_key` or structural feature flags: the server
recomputes `entity_key` from `entity_type + normalized token`, and only trusts
`explicit_risk` / `symptom_change` suggestions from the provider.
"""
from __future__ import annotations

import unicodedata
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

EntityType = Literal["symptom", "medication", "allergy", "chief_complaint", "task", "risk"]

ENTITY_TYPES = {"symptom", "medication", "allergy", "chief_complaint", "task", "risk"}


class Candidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    quote: str
    risk_reason: str
    entity_type: EntityType
    entity_key: str = ""  # ignored; server recomputes
    assertion_value: str | None = None
    explicit_risk: bool = False
    symptom_change: bool = False
    semantic_context: dict | None = None  # server recomputes against anchored source


class AISummaryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    chief_complaint: str | None = None
    candidates: list[Candidate] = Field(default_factory=list)


def normalize_token(text: str) -> str:
    t = "".join(c if c.isalnum() else " " for c in unicodedata.normalize("NFKC", text).casefold())
    return " ".join(t.split())


def normalize_entity_key(entity_type: str, text: str) -> str:
    token = normalize_token(text)
    if token in {"", "clinical risk flagged", "risk related statement", "medication mention", "symptom change", "action item"}:
        return ""
    return f"{entity_type}:{token}"


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
