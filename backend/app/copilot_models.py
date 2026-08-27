"""Strict provider-facing and API-facing shapes for D4 Copilot.

Provider output is always treated as an untrusted proposal.  The server owns
the evidence cards, claim text for source facts, patient/event selection, and
every writable draft field.
"""
from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


CopilotCategory = Literal["what_changed", "what_matters_now", "find_evidence", "draft_action"]


class CopilotProviderClaim(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=600)
    status: Literal["supported", "inference", "unknown"]
    evidence_ids: list[str] = Field(default_factory=list, max_length=4)


class CopilotProviderResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    claims: list[CopilotProviderClaim] = Field(default_factory=list, max_length=6)


class CopilotEvidenceOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    event_id: str
    event_type: str
    event_time: datetime
    record_time: datetime
    artifact_id: str
    artifact_type: str
    author_role: str
    span: dict
    quote: str
    review_required: bool = False


class CopilotClaimOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    status: Literal["supported", "inference", "unknown"]
    evidence_ids: list[str]


class CopilotDraftOut(BaseModel):
    model_config = ConfigDict(extra="forbid")

    artifact_type: Literal["clinician_note", "patient_instruction", "task"]
    event_id: str
    evidence_ids: list[str]
    content: dict
    patient_visible: bool
    ai_generated: Literal[True] = True
    requires_clinician_confirmation: Literal[True] = True
    confirmation_token: str


class CopilotQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: CopilotCategory
    question: str = Field(default="", max_length=300)
    draft_type: Literal["clinician_note", "patient_instruction", "task"] | None = None

    @model_validator(mode="after")
    def draft_type_matches_category(self):
        if self.category == "draft_action" and self.draft_type is None:
            raise ValueError("draft_type is required for draft_action")
        if self.category != "draft_action" and self.draft_type is not None:
            raise ValueError("draft_type is only valid for draft_action")
        return self


class CopilotResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: CopilotCategory
    status: Literal["ok", "unavailable"]
    claims: list[CopilotClaimOut]
    evidence: list[CopilotEvidenceOut]
    limitations: list[str]
    draft: CopilotDraftOut | None = None
