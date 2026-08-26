"""Highlight domain logic: transparent importance scoring + deterministic span
location.

Span anchoring rule (Phase 4 will reuse this exact contract):
- candidates carry a verbatim `quote` from the source artifact;
- `locate_span` finds the quote via deterministic string matching (never
  trusting an LLM-supplied index);
- no match => drop the candidate (never fabricate a span).

importance_score is always computed at write time and stored; the Glance read
path does zero computation.
"""
from __future__ import annotations

from typing import Any

# Transparent, rule-based weights (constants, not a config system).
WEIGHTS = {
    "recency": 2,
    "explicit_risk": 3,
    "unresolved_task": 2,
    "clinician_confirmed": 2,
    "symptom_change": 3,
    "repeated_mentions": 1,
}

FEATURE_FLAGS = tuple(WEIGHTS.keys())

# Default number of highlights surfaced in the Glance View.
GLANCE_LIMIT = 5


def compute_score(feature_flags: dict[str, bool]) -> int:
    return sum(WEIGHTS[k] for k in FEATURE_FLAGS if feature_flags.get(k))


def locate_span(content: dict, quote: str) -> dict | None:
    """Deterministically locate `quote` inside an artifact's content.

    Supports the M1 content shapes: transcript segments, conversation messages,
    and top-level string sections (clinician_note / patient_instruction / ai
    summary fields).
    """
    for seg in content.get("segments", []):
        idx = seg.get("text", "").find(quote)
        if idx != -1:
            return {"kind": "segment", "index": seg["index"], "offset": [idx, idx + len(quote)]}

    for i, msg in enumerate(content.get("messages", []), start=1):
        idx = msg.get("text", "").find(quote)
        if idx != -1:
            return {"kind": "message", "index": i, "offset": [idx, idx + len(quote)]}

    for key, val in content.items():
        if isinstance(val, str):
            idx = val.find(quote)
            if idx != -1:
                return {"kind": "section", "index": key, "offset": [idx, idx + len(quote)]}

    return None


def extract_text(content: dict, span: dict) -> str | None:
    """Resolve a span back to the exact source substring."""
    kind = span.get("kind")
    if kind == "segment":
        for seg in content.get("segments", []):
            if seg.get("index") == span.get("index"):
                text = seg.get("text", "")
                start, end = _offset(span, text)
                return text[start:end]
    elif kind == "message":
        msgs = content.get("messages", [])
        idx = span.get("index", 0)
        if 1 <= idx <= len(msgs):
            text = msgs[idx - 1].get("text", "")
            start, end = _offset(span, text)
            return text[start:end]
    elif kind == "section":
        text = content.get(span.get("index"))
        if isinstance(text, str):
            start, end = _offset(span, text)
            return text[start:end]
    return None


def _offset(span: dict, text: str) -> tuple[int, int]:
    start, end = span.get("offset", [0, len(text)])
    return max(0, start), min(len(text), end)


def status_transitions() -> dict[str, set[str]]:
    # Legal status-machine transitions; same-status updates are no-ops.
    return {
        "suggested": {"accepted", "rejected", "pinned"},
        "accepted": {"rejected", "pinned"},
        "rejected": {"accepted"},
        "pinned": {"accepted", "rejected"},
    }
