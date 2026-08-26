"""Provider-neutral LLM client (M4).

- `LLMClient.summarize(redacted, flow_type)` is the ONLY egress point to any
  provider. It accepts `RedactedContent` (never a raw string/dict).
- `MockLLMClient`: deterministic, no network, key-free.
- `DeepSeekAdapter`: live adapter (Gate 0 LIVE_VERIFIED 2026-08-26). Reads key
  from env only; never prints or stores it. Output must pass the strict
  `AISummaryResult` schema or the call fails closed with `InvalidOutputError`.
"""
from __future__ import annotations

import json
import logging
import os
import re
from typing import Protocol

from .extraction import AISummaryResult, Candidate
from .redaction import RedactedContent

logger = logging.getLogger("nantingale.llm")

DEEPSEEK_BASE_URL = "https://api.deepseek.com/anthropic"


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


_SYSTEM_PROMPT = (
    "You are a clinical scribe assistant. You receive a de-identified clinical "
    "conversation and must return a concise summary plus structured candidate "
    "highlights.\n"
    "Respond with ONLY a JSON object (no markdown fences, no commentary) matching "
    "this exact schema:\n"
    '{"summary": str, "chief_complaint": str|null, "candidates": ['
    '{"text": str, "quote": str, "risk_reason": str, '
    '"entity_type": "symptom|medication|allergy|chief_complaint|task|risk", '
    '"assertion_value": str|null, "explicit_risk": bool, "symptom_change": bool}]}\n'
    "Rules: `quote` MUST be an exact verbatim sentence copied from the source. "
    "Placeholder tokens such as [NAME_1] must be copied exactly and never altered. "
    "If nothing is notable, return an empty candidates list."
)


def _user_prompt(redacted: RedactedContent, flow_type: str) -> str:
    return (
        f"Flow type: {flow_type}\n"
        f"De-identified content (JSON):\n{json.dumps(redacted.content, ensure_ascii=False)}"
    )


class DeepSeekAdapter:
    """DeepSeek via its anthropic-compatible endpoint (live, Gate 0 LIVE_VERIFIED).

    Reads the key from env only (DEEPSEEK_API_KEY, then Natingale_API_KEY). No key
    => ProviderUnavailableError -> deterministic fallback. Schema-invalid output
    => InvalidOutputError -> fallback.
    """

    def __init__(self, model: str = "deepseek-v4-flash"):
        self.model = model

    def _key(self) -> str | None:
        return os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("Natingale_API_KEY")

    def summarize(self, redacted: RedactedContent, flow_type: str) -> AISummaryResult:
        key = self._key()
        if not key:
            raise ProviderUnavailableError("no DeepSeek API key configured")

        try:
            from anthropic import Anthropic

            client = Anthropic(api_key=key, base_url=DEEPSEEK_BASE_URL)
            resp = client.messages.create(
                model=self.model,
                max_tokens=2000,
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": _user_prompt(redacted, flow_type)}],
            )
        except Exception as e:  # auth / network / timeout / protocol
            raise ProviderProtocolError(f"DeepSeek call failed: {type(e).__name__}")

        usage = getattr(resp, "usage", None)
        if usage is not None:
            logger.info(
                "deepseek usage model=%s input=%s output=%s",
                self.model,
                getattr(usage, "input_tokens", None),
                getattr(usage, "output_tokens", None),
            )

        text = "".join(
            block.text for block in resp.content if hasattr(block, "text")
        ).strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.MULTILINE).strip()

        try:
            data = json.loads(text)
            return AISummaryResult.model_validate(data)
        except Exception as e:
            raise InvalidOutputError(f"DeepSeek output failed schema: {e}")


def build_client(provider: str = "mock", **kwargs) -> LLMClient:
    if provider == "mock":
        return MockLLMClient(**kwargs)
    if provider == "deepseek":
        return DeepSeekAdapter(**kwargs)
    raise ValueError(f"unknown provider: {provider}")
