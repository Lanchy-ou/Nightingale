"""M7 H4: warm-path read modules never import the AI pipeline / LLM / extraction.

Each read module is imported in a clean interpreter subprocess and its
*transitive* import delta is inspected. If any of glance / patient-view /
events / patients pulls in the provider, extraction, redaction, fallback or
conflict machinery, this test fails — proving the read path stays LLM-free by
construction, not just by convention.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent

READ_MODULES = [
    "app.api.highlights",  # glance + provenance
    "app.api.patient_view",
    "app.api.events",
    "app.api.patients",
]

FORBIDDEN = {
    "app.ai_pipeline",
    "app.llm_client",
    "app.extraction",
    "app.redaction",
    "app.deterministic_pipeline",
    "app.conflicts",
    "app.importance_learning",
}


def _import_delta() -> dict[str, list[str]]:
    code = (
        "import json, sys\n"
        "out = {}\n"
        "for name in %r:\n"
        "    before = set(sys.modules)\n"
        "    __import__(name)\n"
        "    out[name] = sorted(set(sys.modules) - before)\n"
        "print(json.dumps(out))\n" % (READ_MODULES,)
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(BACKEND),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_read_paths_do_not_import_ai_pipeline():
    delta = _import_delta()
    for module in READ_MODULES:
        assert module in delta
        loaded = set(delta[module])
        leaked = loaded & FORBIDDEN
        assert not leaked, (
            f"{module} transitively imported forbidden modules: {sorted(leaked)}"
        )
