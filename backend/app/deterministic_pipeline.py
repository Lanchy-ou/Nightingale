"""Fixture-independent deterministic fallback (M4).

Hard rule: NEVER imports `seed.fixture`, `HIGHLIGHT_CANDIDATES`, or any fixed
artifact/event/highlight ID. Operates only on the given raw source content.

Produces a conservative extractive summary plus keyword-driven candidates whose
`quote` is always a verbatim substring of the source (so it can anchor exactly).
Unsupported sources may yield 0 candidates — it never fabricates content.
"""
from __future__ import annotations

import re

from .extraction import AISummaryResult, Candidate
from .semantic_rules import FAMILY, PAST, HYPOTHETICAL, clauses, current_positive

_SYMPTOM_CHANGE = re.compile(
    r"\b(worse|worsening|worsen|improved|improving|better|increased|decreased"
    r"|more frequent|less frequent|almost every day|once a week)\b",
    re.IGNORECASE,
)
_RISK = re.compile(r"\b(elevated|high|abnormal|severe|critical)\b|严重|升高|异常", re.IGNORECASE)
_TASK = re.compile(
    r"\b(ordered|scheduled|pending|follow-up|followup|waiting for)\b", re.IGNORECASE
)
_MED = re.compile(
    r"\b(mg|dose|daily|propranolol|amitriptyline|medication|prescription)\b",
    re.IGNORECASE,
)


def extract_text_leaves(content: dict) -> list[str]:
    out: list[str] = []
    for seg in content.get("segments", []):
        if isinstance(seg, dict) and isinstance(seg.get("text"), str):
            out.append(seg["text"])
    for msg in content.get("messages", []):
        if isinstance(msg, dict) and isinstance(msg.get("text"), str):
            out.append(msg["text"])
    for key, val in content.items():
        if key in ("segments", "messages"):
            continue
        if isinstance(val, str):
            out.append(val)
    return out


def _candidate_for(sentence: str) -> Candidate | None:
    if _RISK.search(sentence):
        return Candidate(
            text="Risk-related statement",
            quote=sentence,
            risk_reason="Risk-related statement detected",
            entity_type="risk",
            explicit_risk=current_positive(sentence),
        )
    if _SYMPTOM_CHANGE.search(sentence):
        return Candidate(
            text="Symptom change",
            quote=sentence,
            risk_reason="Symptom change statement detected",
            entity_type="symptom",
            symptom_change=True,
        )
    if _TASK.search(sentence):
        return Candidate(
            text="Action item",
            quote=sentence,
            risk_reason="Action/task statement detected",
            entity_type="task",
        )
    if _MED.search(sentence):
        return Candidate(
            text="Medication mention",
            quote=sentence,
            risk_reason="Medication statement detected",
            entity_type="medication",
        )
    return None


def build_fallback(content: dict, flow_type: str = "") -> AISummaryResult:
    leaves = extract_text_leaves(content)
    summary = " ".join(leaves[:3]) if leaves else "(no content)"
    candidates: list[Candidate] = []
    for leaf in leaves:
        for sentence in clauses(leaf):
            c = _candidate_for(sentence)
            if c is not None:
                if FAMILY.search(leaf) or PAST.search(leaf) or HYPOTHETICAL.search(leaf):
                    c.explicit_risk = False
                candidates.append(c)
    return AISummaryResult(summary=summary, chief_complaint=None, candidates=candidates)
