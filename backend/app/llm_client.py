"""Provider-neutral LLM client (M4).

- `LLMClient.summarize(redacted, flow_type)` is the ONLY egress point to any
  provider. It accepts `RedactedContent` (never a raw string/dict).
- `MockLLMClient`: deterministic, no network, key-free.
- `DeepSeekAdapter`: reads a key from env only; BLOCKED because Gate 0 returned
  NOT_LIVE_VERIFIED. It raises so the pipeline falls back deterministically.
"""
from __future__ import annotations

import os
from typing import Protocol

from .extraction import AISummaryResult, Candidate
from .redaction import RedactedContent


class LLMError(Exception):
    pass


class ProviderUnavailableError(LLMError):
    """No provider / key configured."""


class ProviderProtocolError(LLMError):
    """Provider reachable but returned an error / protocol is incompatible."""


class InvalidOutputError(LLMError):
    """Provider output failed strict schema validation."""


class LLMClient(Protocol):
    def summarize(self, redacted: RedactedContent, flow_type: str) -> AISummaryResult:
        ...


def _text_leaves(redacted: RedactedContent) -> list[str]:
    out: list[str] = []
    for seg in redacted.content.get("segments", []):
        if isinstance(seg, dict) and isinstance(seg.get("text"), str):
            out.append(seg["text"])
    for msg in redacted.content.get("messages", []):
        if isinstance(msg, dict) and isinstance(msg.get("text"), str):
            out.append(msg["text"])
    return out


class MockLLMClient:
    """Deterministic mock provider.

    Returns a valid summary derived from the redacted content, plus any
    candidates injected at construction. Records the last payload so tests can
    assert the provider only ever received redacted content.
    """

    def __init__(self, candidates: list[Candidate] | None = None):
        self._candidates = candidates or []
        self.last_payload: RedactedContent | None = None

    def summarize(self, redacted: RedactedContent, flow_type: str) -> AISummaryResult:
        self.last_payload = redacted
        leaves = _text_leaves(redacted)
        summary = ("Mock summary: " + " ".join(leaves[:2])) if leaves else "Mock summary."
        return AISummaryResult(
            summary=summary,
            chief_complaint=None,
            candidates=list(self._candidates),
        )


class DeepSeekAdapter:
    """DeepSeek via anthropic-compatible endpoint.

    BLOCKED (Gate 0 = NOT_LIVE_VERIFIED). Reads key from env only; never prints
    or stores it. No key => ProviderUnavailableError; with a key it still
    raises ProviderProtocolError until the protocol is live-verified.
    """

    def __init__(self, model: str = "deepseek-v4-flash"):
        self.model = model

    def summarize(self, redacted: RedactedContent, flow_type: str) -> AISummaryResult:
        key = os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
        if not key:
            raise ProviderUnavailableError("no DeepSeek API key configured")
        raise ProviderProtocolError("DeepSeek live adapter blocked (Gate 0 NOT_LIVE_VERIFIED)")


def build_client(provider: str = "mock", **kwargs) -> LLMClient:
    if provider == "mock":
        return MockLLMClient(**kwargs)
    if provider == "deepseek":
        return DeepSeekAdapter(**kwargs)
    raise ValueError(f"unknown provider: {provider}")
