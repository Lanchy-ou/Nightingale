"""Non-BMP / emoji source-range contract (backend + frontend).

The backend counts source_start/source_end as Python code points while
JavaScript counts UTF-16 code units. This locks both sides of that contract:
the normalizer must return code-point ranges, and the frontend split/length
helpers must be code-point aware (never pseudo-precise, never split a
surrogate pair).
"""
from __future__ import annotations

from pathlib import Path
import subprocess

FRONTEND_TEST = (
    Path(__file__).resolve().parents[2] / "frontend" / "tests" / "transcriptRange.test.ts"
)


def test_normalize_source_ranges_are_code_point_offsets_for_emoji(clinician_client):
    raw = "Doctor: Pain \U0001F600 today\nPatient: yes"
    response = clinician_client.post("/api/transcripts/normalize", json={"raw_text": raw})
    assert response.status_code == 200, response.text
    first = response.json()["segments"][0]
    assert first["text"] == "Pain \U0001F600 today"
    # The range must be a code-point span that slices back to the exact text.
    assert raw[first["source_start"] : first["source_end"]] == first["text"]
    # Python len() is code points; this is the span the frontend must reproduce.
    assert first["source_end"] - first["source_start"] == len(first["text"])
    assert first["source_end"] - first["source_start"] == 12


def test_frontend_non_bmp_split_helpers_are_code_point_aware():
    result = subprocess.run(
        ["node", str(FRONTEND_TEST)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "non-BMP checks passed" in result.stdout
