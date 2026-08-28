"""The single provider-neutral ASR exit for E4."""

from __future__ import annotations

import io
import os
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from .contracts import ASRResult, ASRSegment, AuthorizedRecording

FASTER_WHISPER_MODEL = "Systran/faster-whisper-base"
FASTER_WHISPER_MODEL_REVISION = "a80717a3a48b1b28aa687bca146cb7301feae1b1"
_REQUIRED_MODEL_FILES = {"config.json", "model.bin", "tokenizer.json"}
DEFAULT_ASR_MODEL_PATH = Path(__file__).resolve().parents[2] / ".models" / "faster-whisper-base"


class ASRClient(Protocol):
    def transcribe(self, recording: AuthorizedRecording) -> ASRResult: ...


def configured_asr_provider() -> str:
    return os.environ.get("NANTINGALE_ASR_PROVIDER", "mock").strip().lower()


def configured_model_path() -> Path | None:
    raw = os.environ.get("NANTINGALE_ASR_MODEL_PATH", "").strip()
    return Path(raw).expanduser().resolve() if raw else DEFAULT_ASR_MODEL_PATH.resolve()


def asr_runtime_ready(provider: str | None = None) -> bool:
    provider = provider or configured_asr_provider()
    if provider == "mock":
        return True
    if provider != "faster_whisper":
        return False
    model_path = configured_model_path()
    return bool(
        model_path
        and model_path.is_dir()
        and _REQUIRED_MODEL_FILES.issubset(
            {item.name for item in model_path.iterdir() if item.is_file()}
        )
    )


def _failure(reason: str, *, provider: str = "deterministic_mock") -> ASRResult:
    return ASRResult(
        provider=provider,
        method="fixture_lookup" if provider == "deterministic_mock" else "local_cpu_int8",
        model=None if provider == "deterministic_mock" else "faster-whisper-base",
        version="1" if provider == "deterministic_mock" else FASTER_WHISPER_MODEL_REVISION,
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


@lru_cache(maxsize=2)
def _load_local_model(model_path: str):
    # Import lazily so disabled deployments do not load the native ASR stack.
    # A local directory plus local_files_only prevents request-time downloads.
    from faster_whisper import WhisperModel

    return WhisperModel(
        model_path,
        device="cpu",
        compute_type="int8",
        local_files_only=True,
    )


class FasterWhisperASRClient:
    """Offline multilingual Base ASR. It deliberately performs no diarization."""

    def __init__(self, model_path: Path):
        self._model_path = model_path

    def transcribe(self, recording: AuthorizedRecording) -> ASRResult:
        actual_digest = sha256(recording.audio_bytes).hexdigest()
        if (
            actual_digest != recording.metadata.sha256
            or len(recording.audio_bytes) != recording.metadata.byte_length
        ):
            return _failure("recording_digest_mismatch", provider="faster_whisper")

        try:
            model = _load_local_model(str(self._model_path))
            observed, info = model.transcribe(
                io.BytesIO(recording.audio_bytes),
                beam_size=1,
                vad_filter=False,
                condition_on_previous_text=False,
            )
            segments: list[ASRSegment] = []
            for index, item in enumerate(observed):
                text = item.text.strip()
                if not text:
                    continue
                if index >= 500 or len(text) > 4000:
                    return _failure("asr_output_limit", provider="faster_whisper")
                segments.append(
                    ASRSegment(
                        machine_segment_id=f"fw_{index}",
                        source_start_ms=max(0, round(float(item.start) * 1000)),
                        source_end_ms=max(0, round(float(item.end) * 1000)),
                        speaker_candidate=None,
                        text=text,
                        confidence=None,
                        issues=["unknown_speaker"],
                    )
                )
        except Exception:
            return _failure("local_asr_error", provider="faster_whisper")

        if not segments:
            return _failure("no_speech_detected", provider="faster_whisper")
        return ASRResult(
            provider="faster_whisper",
            method="local_cpu_int8",
            model="faster-whisper-base-multilingual",
            version=FASTER_WHISPER_MODEL_REVISION,
            language=info.language or None,
            segments=segments,
            degraded=False,
            failure_reason=None,
        )


def build_asr_client(provider: str | None = None) -> ASRClient:
    provider = provider or configured_asr_provider()
    if provider == "mock":
        return DeterministicMockASRClient({})
    if provider == "faster_whisper":
        model_path = configured_model_path()
        if model_path is None or not asr_runtime_ready(provider):
            raise RuntimeError("Local ASR model is unavailable")
        return FasterWhisperASRClient(model_path)
    raise ValueError("Unsupported ASR provider")
