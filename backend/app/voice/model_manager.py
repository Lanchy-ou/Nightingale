"""Pinned, single-job local ASR model preparation for the Admin UI."""
from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from huggingface_hub import snapshot_download

from .asr import (
    DEFAULT_ASR_MODEL_PATH,
    FASTER_WHISPER_MODEL,
    FASTER_WHISPER_MODEL_REVISION,
    asr_runtime_ready,
)

_lock = threading.RLock()
_state = {"status": "ready" if asr_runtime_ready("faster_whisper") else "missing", "error_code": None}


def model_status() -> dict:
    with _lock:
        status = _state["status"]
        error_code = _state["error_code"]
    if status != "downloading" and asr_runtime_ready("faster_whisper"):
        status, error_code = "ready", None
    return {
        "status": status,
        "error_code": error_code,
        "model": "faster-whisper-base",
        "revision": FASTER_WHISPER_MODEL_REVISION,
        "download_bytes_approx": 148_000_000,
    }


def _prepare() -> None:
    model_dir = DEFAULT_ASR_MODEL_PATH.resolve()
    model_dir.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=FASTER_WHISPER_MODEL,
        revision=FASTER_WHISPER_MODEL_REVISION,
        local_dir=model_dir,
    )
    files = {}
    for path in sorted(item for item in model_dir.iterdir() if item.is_file()):
        if path.name == "model_manifest.json":
            continue
        files[path.name] = {
            "bytes": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
    manifest = {
        "repo_id": FASTER_WHISPER_MODEL,
        "revision": FASTER_WHISPER_MODEL_REVISION,
        "prepared_at": datetime.now(timezone.utc).isoformat(),
        "files": files,
    }
    (model_dir / "model_manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
    )
    if not asr_runtime_ready("faster_whisper"):
        raise RuntimeError("model_validation_failed")


def start_model_download(on_finished: Callable[[str], None] | None = None) -> dict:
    with _lock:
        if _state["status"] == "downloading":
            return model_status()
        if asr_runtime_ready("faster_whisper"):
            _state.update(status="ready", error_code=None)
            return model_status()
        _state.update(status="downloading", error_code=None)

    def run() -> None:
        final = "ready"
        try:
            _prepare()
            with _lock:
                _state.update(status="ready", error_code=None)
        except Exception:
            final = "failed"
            with _lock:
                _state.update(status="failed", error_code="model_download_failed")
        if on_finished:
            on_finished(final)

    threading.Thread(target=run, name="nantingale-voice-model", daemon=True).start()
    return model_status()


def prepare_model_blocking() -> None:
    """Deployment CLI entry: prepare and validate the pinned model synchronously."""
    with _lock:
        if asr_runtime_ready("faster_whisper"):
            _state.update(status="ready", error_code=None)
            return
        _state.update(status="downloading", error_code=None)
    try:
        _prepare()
    except Exception:
        with _lock:
            _state.update(status="failed", error_code="model_download_failed")
        raise
    with _lock:
        _state.update(status="ready", error_code=None)
