"""The single provider-neutral ASR exit for E4."""

from __future__ import annotations

from hashlib import sha256
from typing import Protocol

from .contracts import ASRResult, AuthorizedRecording


class ASRClient(Protocol):
    def transcribe(self, recording: AuthorizedRecording) -> ASRResult: ...


def _failure(reason: str) -> ASRResult:
    return ASRResult(
        provider="deterministic_mock",
        method="fixture_lookup",
        model=None,
        version="1",
        language=None,
        segments=[],
        degraded=True,
        failure_reason=reason,
    )


class DeterministicMockASRClient:
    """Key-free contract double; it does not perform acoustic recognition."""

    def __init__(self, results_by_sha256: dict[str, ASRResult]):
        self._results = {
            digest: result.model_copy(deep=True)
            for digest, result in results_by_sha256.items()
        }

    def transcribe(self, recording: AuthorizedRecording) -> ASRResult:
        actual_digest = sha256(recording.audio_bytes).hexdigest()
        if (
            actual_digest != recording.metadata.sha256
            or len(recording.audio_bytes) != recording.metadata.byte_length
        ):
            return _failure("recording_digest_mismatch")

        result = self._results.get(actual_digest)
        if result is None:
            return _failure("mock_fixture_not_found")
        return result.model_copy(deep=True)


def build_asr_client(provider: str = "mock") -> ASRClient:
    """Build the approved ASR adapter.

    E4 currently exposes only the deterministic contract double. It has no
    built-in transcript fixtures, so an unknown recording fails explicitly.
    A real local/external provider requires a separate privacy/license gate.
    """
    if provider == "mock":
        return DeterministicMockASRClient({})
    raise ValueError("Unsupported ASR provider")
