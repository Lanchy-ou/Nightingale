"""Download the approved E4 model once; runtime never downloads weights."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

from huggingface_hub import snapshot_download

from app.voice.asr import FASTER_WHISPER_MODEL, FASTER_WHISPER_MODEL_REVISION  # noqa: E402


def main() -> None:
    default_dir = Path(__file__).resolve().parents[1] / ".models" / "faster-whisper-base"
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, default=default_dir)
    args = parser.parse_args()
    model_dir = args.model_dir.expanduser().resolve()
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
        json.dumps(manifest, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print(f"LOCAL_ASR_MODEL_READY {model_dir}")


if __name__ == "__main__":
    main()
