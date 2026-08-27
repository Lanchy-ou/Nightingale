"""Corpus-only checks for D3 transcript reliability preparation."""
from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys


BACKEND = Path(__file__).resolve().parents[1]
CORPUS = BACKEND / "evals" / "transcripts"
MANIFEST = CORPUS / "manifest.json"
RUNNER = BACKEND / "scripts" / "evaluate_transcripts.py"
EXPECTED_MANIFEST_SHA256 = "0dca7c95dab20c23705bf59677a8525b0d2eec61b63e7a9fb9109e1ec0103771"
EXPECTED_HOLDOUT_DIGEST = "e2b429ff98cfc802b307c7de46f4ffa0006e12211cce7efaf37799b762a4d962"
REQUIRED_COVERAGE = {
    "canonical_label",
    "case_variant",
    "dr_pt_mapping",
    "continuation",
    "blank_line",
    "repeated_label",
    "unknown_speaker",
    "three_party",
    "unlabeled",
    "bilingual",
    "self_correction",
    "interruption",
    "medication_dose",
    "negation",
    "time_expression",
    "task_status",
    "internal_contradiction",
    "no_clinical_information",
    "overlong_input",
    "synthetic_name",
    "synthetic_id",
    "synthetic_phone",
    "prompt_injection",
    "malicious_json",
    "malicious_markdown",
    "anchorable_quote",
    "unanchorable_quote",
    "provider_invalid_schema",
    "provider_failure",
    "deterministic_fallback",
}


def _manifest(path: Path = MANIFEST) -> dict:
    return json.loads(path.read_bytes().decode("utf-8"))


def _case(entry: dict, root: Path = CORPUS) -> dict:
    return json.loads((root / entry["path"]).read_bytes().decode("utf-8"))


def _run(manifest: Path = MANIFEST) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), "--validate-corpus", "--manifest", str(manifest)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write_json_lf(path: Path, value: dict) -> bytes:
    raw = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    path.write_bytes(raw)
    return raw


def test_manifest_bytes_hashes_and_frozen_holdout_digest_are_reproducible():
    manifest_raw = MANIFEST.read_bytes()
    assert not manifest_raw.startswith(b"\xef\xbb\xbf")
    assert b"\r" not in manifest_raw
    assert hashlib.sha256(manifest_raw).hexdigest() == EXPECTED_MANIFEST_SHA256

    manifest = _manifest()
    entries = manifest["cases"]
    assert len(entries) == 40
    assert manifest["splits"] == {"development": 26, "frozen_holdout": 14}
    assert [entry["path"] for entry in entries] == sorted(entry["path"] for entry in entries)

    holdout_lines: list[str] = []
    for entry in entries:
        raw = (CORPUS / entry["path"]).read_bytes()
        assert b"\r" not in raw
        assert raw.endswith(b"\n")
        assert len(raw) == entry["byte_length"]
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        if entry["split"] == "frozen_holdout":
            holdout_lines.append(f"{entry['path']}\t{entry['byte_length']}\t{entry['sha256']}\n")

    digest = hashlib.sha256("".join(holdout_lines).encode("utf-8")).hexdigest()
    assert digest == EXPECTED_HOLDOUT_DIGEST
    assert manifest["frozen_holdout_digest"] == EXPECTED_HOLDOUT_DIGEST


def test_schema_split_coverage_and_hard_gate_annotations_are_complete():
    manifest = _manifest()
    tags: set[str] = set()
    outcomes: set[str] = set()
    case_ids: set[str] = set()
    for entry in manifest["cases"]:
        case = _case(entry)
        assert case["case_id"] == entry["case_id"]
        assert case["case_id"] not in case_ids
        case_ids.add(case["case_id"])
        assert case["split"] == entry["split"]
        assert case["data_classification"] == "SYNTHETIC_ONLY"
        assert case["expected_normalize_outcome"] in {"ACCEPT", "NEEDS_REVIEW", "REJECT"}
        outcomes.add(case["expected_normalize_outcome"])
        tags.update(case["coverage_tags"])
        assert set(case["hard_gate_annotations"].values()) == {False}
        assert case["provider_expectations"]["metrics_status"] == "NOT_EVALUATED"
        for field in ("extraction_expectations", "redaction_expectations", "anchor_expectations"):
            assert case[field]["annotation_status"] in {"ANNOTATED", "NOT_APPLICABLE", "UNKNOWN"}

    assert outcomes == {"ACCEPT", "NEEDS_REVIEW", "REJECT"}
    assert REQUIRED_COVERAGE <= tags


def test_expected_source_ranges_are_exact_and_unknown_is_never_defaulted():
    manifest = _manifest()
    limits = manifest["protocol_limits"]
    saw_overlong = False
    saw_unknown = False
    for entry in manifest["cases"]:
        case = _case(entry)
        raw_text = case["raw_text"]
        if case["expected_normalize_outcome"] == "ACCEPT":
            segments = case["expected_canonical_segments"]
            assert [segment["index"] for segment in segments] == list(range(len(segments)))
            assert {segment["speaker"] for segment in segments} <= {"doctor", "patient"}
            for segment in segments:
                assert raw_text[segment["source_start"] : segment["source_end"]] == segment["text"]
        if "overlong_input" in case["coverage_tags"]:
            saw_overlong = True
            assert len(raw_text.encode("utf-8")) > limits["max_raw_text_bytes"]
            assert case["expected_normalize_outcome"] == "REJECT"
            assert case["normalize_reason"] == "INPUT_TOO_LONG"
        if "unknown_speaker" in case["coverage_tags"] or "unknown_not_defaulted" in case["coverage_tags"]:
            saw_unknown = True
            assert case["expected_normalize_outcome"] != "ACCEPT"
            assert case["hard_gate_annotations"]["unknown_to_default_allowed"] is False
            assert case["expected_canonical_segments"] is None
    assert saw_overlong and saw_unknown


def test_runner_validates_corpus_only_and_reports_no_runtime_scores():
    result = _run()
    assert result.returncode == 0, result.stderr
    assert "FROZEN_CORPUS" in result.stdout
    assert "RUNTIME_EVALUATED_SEPARATELY" in result.stdout
    assert "CORPUS_VALIDATION_PASS" in result.stdout
    assert "D3_COMPLETE" not in result.stdout
    assert "VALIDATION_PASS" in result.stdout
    assert "manifest_hashes_verified: 40/40" in result.stdout
    assert EXPECTED_HOLDOUT_DIGEST in result.stdout
    assert "%" not in result.stdout

    tree = ast.parse(RUNNER.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module != "__future__":
            imports.add((node.module or "").split(".")[0])
    assert imports <= {"argparse", "collections", "hashlib", "importlib", "json", "os", "pathlib", "re", "sys", "typing"}


def test_runner_fails_closed_on_case_hash_mismatch(tmp_path: Path):
    copied = tmp_path / "transcripts"
    shutil.copytree(CORPUS, copied)
    manifest = _manifest(copied / "manifest.json")
    target = copied / manifest["cases"][0]["path"]
    target.write_bytes(target.read_bytes() + b" ")

    result = _run(copied / "manifest.json")
    assert result.returncode != 0
    assert "VALIDATION_FAILED" in result.stderr
    assert any(
        reason in result.stderr
        for reason in ("deterministic file must end with LF", "byte_length mismatch", "sha256 mismatch")
    )


def test_runner_fails_closed_on_schema_gap_even_with_updated_development_hash(tmp_path: Path):
    copied = tmp_path / "transcripts"
    shutil.copytree(CORPUS, copied)
    manifest_path = copied / "manifest.json"
    manifest = _manifest(manifest_path)
    entry = next(item for item in manifest["cases"] if item["split"] == "development")
    case_path = copied / entry["path"]
    case = _case(entry, copied)
    del case["anchor_expectations"]
    raw = _write_json_lf(case_path, case)
    entry["byte_length"] = len(raw)
    entry["sha256"] = hashlib.sha256(raw).hexdigest()
    _write_json_lf(manifest_path, manifest)

    result = _run(manifest_path)
    assert result.returncode != 0
    assert "VALIDATION_FAILED" in result.stderr
    assert "missing=['anchor_expectations']" in result.stderr
