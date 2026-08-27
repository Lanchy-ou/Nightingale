"""Observed local-only ASR smoke check for an explicitly synthetic WAV."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from hashlib import sha256
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from app.voice.asr import FasterWhisperASRClient  # noqa: E402
from app.voice.audio import AudioPolicy, inspect_audio  # noqa: E402
from app.voice.contracts import AuthorizedRecording, CaptureMode  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("audio", type=Path)
    parser.add_argument("--model-dir", type=Path, required=True)
    args = parser.parse_args()
    audio_path = args.audio.expanduser().resolve()
    model_path = args.model_dir.expanduser().resolve()
    audio_bytes = audio_path.read_bytes()
    metadata = inspect_audio(
        audio_bytes,
        declared_mime_type="audio/wav",
        policy=AudioPolicy(max_bytes=8 * 1024 * 1024, max_duration_ms=120_000),
    )
    os.environ["HF_HUB_OFFLINE"] = "1"
    started = time.perf_counter()
    result = FasterWhisperASRClient(model_path).transcribe(
        AuthorizedRecording(
            capture_id="synthetic_gate0",
            clinic_id="synthetic_clinic",
            patient_id="synthetic_patient",
            capture_mode=CaptureMode.DOCTOR_CONSULT,
            audio_bytes=audio_bytes,
            metadata=metadata,
        )
    )
    print(
        json.dumps(
            {
                "audio_sha256": sha256(audio_bytes).hexdigest(),
                "duration_ms": metadata.duration_ms,
                "latency_ms": round((time.perf_counter() - started) * 1000),
                "provider": result.provider,
                "model": result.model,
                "version": result.version,
                "language": result.language,
                "failure_reason": result.failure_reason,
                "segments": [segment.model_dump(mode="json") for segment in result.segments],
            },
            ensure_ascii=False,
        )
    )
    if result.failure_reason is not None or not result.segments:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
