"""Recursive PHI redaction + placeholder restore (deterministic, synthetic MVP).

- `redact_content(content, known_names)` redacts every string leaf: known names
  (case-insensitive word boundary), IC/ID, and phone numbers. IC/ID and phone
  are classified in a SINGLE pass so a value is never double-replaced.
- `placeholder_mapping` exists only in memory for the duration of one pipeline
  run; it is never logged, stored, or sent to the provider.
- `restore_placeholders` restores only complete, unmodified placeholder tokens.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ROLE_LABELS = {"patient", "doctor", "nurse", "ai", "clinician", "staff"}

_IC_RE = re.compile(r"\b\d{6}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"\b(?:\+?60|0060|0)?1\d[-\s]?\d{3,4}[-\s]?\d{4}\b")
# Single-pass classifier: IC/ID and phone are mutually exclusive alternatives.
_TOKEN_RE = re.compile(r"(?P<ic>" + _IC_RE.pattern + r")|(?P<phone>" + _PHONE_RE.pattern + r")")

_PLACEHOLDER_RE = re.compile(r"\[(NAME|ID|PHONE)_\d+\]")
_ANY_PLACEHOLDER_RE = re.compile(r"\[[A-Za-z][A-Za-z0-9_]*[_\d][A-Za-z0-9_]*\]")


@dataclass
class RedactedContent:
    content: dict
    redaction_counts: dict


@dataclass
class RedactionResult:
    redacted: RedactedContent
    placeholder_mapping: dict


class _Assigner:
    def __init__(self) -> None:
        self.mapping: dict[str, str] = {}
        self.counts: dict[str, int] = {"name": 0, "id": 0, "phone": 0}

    def placeholder(self, prefix: str, value: str) -> str:
        for ph, v in self.mapping.items():
            if v == value and ph.startswith(f"[{prefix}_"):
                return ph
        n = sum(1 for k in self.mapping if k.startswith(f"[{prefix}_"))
        ph = f"[{prefix}_{n + 1}]"
        self.mapping[ph] = value
        return ph

    def apply(self, prefix: str, value: str) -> str:
        ph = self.placeholder(prefix, value)
        self.counts[prefix.lower()] += 1
        return ph


def _walk(node, fn):
    if isinstance(node, dict):
        return {k: _walk(v, fn) for k, v in node.items()}
    if isinstance(node, list):
        return [_walk(v, fn) for v in node]
    if isinstance(node, str):
        return fn(node)
    return node


def redact_content(content: dict, known_names: list[str]) -> RedactionResult:
    assigner = _Assigner()
    names = sorted(
        {n.strip() for n in known_names if n and n.strip()}, key=len, reverse=True
    )

    def redact_string(s: str) -> str:
        out = s
        for name in names:
            pat = re.compile(r"\b" + re.escape(name) + r"\b", re.IGNORECASE)
            out = pat.sub(lambda m: assigner.apply("NAME", m.group(0)), out)

        def classify(m):
            if m.group("ic"):
                return assigner.apply("ID", m.group(0))
            if m.group("phone"):
                return assigner.apply("PHONE", m.group(0))
            return m.group(0)

        return _TOKEN_RE.sub(classify, out)

    redacted = _walk(content, redact_string)
    return RedactionResult(
        redacted=RedactedContent(content=redacted, redaction_counts=dict(assigner.counts)),
        placeholder_mapping=assigner.mapping,
    )


def restore_placeholders(text: str, placeholder_mapping: dict) -> str:
    return _PLACEHOLDER_RE.sub(
        lambda m: placeholder_mapping.get(m.group(0), m.group(0)), text
    )


def unresolved_placeholders(text: str, placeholder_mapping: dict) -> list[str]:
    """Return placeholder-shaped tokens in `text` that cannot be restored."""
    return [t for t in _ANY_PLACEHOLDER_RE.findall(text) if t not in placeholder_mapping]
