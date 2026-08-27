"""Frozen D3 runtime evaluation remains local, deterministic, and layered."""
from __future__ import annotations

import hashlib
from pathlib import Path
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]
RUNNER = BACKEND / "scripts" / "evaluate_transcripts.py"
MANIFEST = BACKEND / "evals" / "transcripts" / "manifest.json"
NORMALIZER = BACKEND / "app" / "transcript_normalizer.py"
FROZEN_NORMALIZER_SHA256 = "1ac0e01e92401b1728e7b938541e71f8d95e81cca137376004953eb2cd371476"


def test_normalizer_bytes_are_frozen_before_holdout_evaluation():
    assert hashlib.sha256(NORMALIZER.read_bytes()).hexdigest() == FROZEN_NORMALIZER_SHA256


def test_runtime_eval_passes_hard_gates_and_keeps_provider_separate():
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER),
            "--evaluate-runtime",
            "--manifest",
            str(MANIFEST),
        ],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "D3_RUNTIME_EVALUATION" in result.stdout
    assert "PROVIDER_LAYER_NOT_RUN" in result.stdout
    assert "DETERMINISTIC_FALLBACK_REPORTED_SEPARATELY" in result.stdout
    assert "HARD_GATES_PASS" in result.stdout
    assert '"silent_speaker_invention": 0' in result.stdout
    assert '"silent_truncation": 0' in result.stdout
    assert '"known_phi_unredacted_payload": 0' in result.stdout
    assert '"fallback_unanchored_candidate": 0' in result.stdout
    assert FROZEN_NORMALIZER_SHA256 in result.stdout
