"""The strengthened D4 frozen evaluator remains reproducible and layered."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


BACKEND = Path(__file__).resolve().parents[1]


def test_frozen_copilot_eval_passes_with_separate_read_latency():
    result = subprocess.run(
        [sys.executable, "-B", "scripts/evaluate_copilot.py"],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    lines = result.stdout.strip().splitlines()
    assert lines[0] == "D4_COPILOT_EVAL_PASS"
    report = json.loads(lines[1])
    assert [row["id"] for row in report["questions"]] == ["changed", "matters", "evidence", "draft"]
    assert report["ai_self_citation_rejected"] is True
    assert report["forged_confirmation_rejected"] is True
    assert report["latency"]["metric"] == "COPILOT_READ_PATH"
    assert report["latency"]["glance_latency_included"] is False
