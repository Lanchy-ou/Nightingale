"""Validate the frozen synthetic transcript corpus without running runtime code.

This script intentionally does not import the transcript normalizer, provider,
fallback, persistence, or application modules.  It validates only corpus bytes,
manifest hashes, annotation schema, coverage, and fail-closed invariants.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import importlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sys
from typing import Any


SPLITS = {"development", "frozen_holdout"}
OUTCOMES = {"ACCEPT", "NEEDS_REVIEW", "REJECT"}
ANNOTATION_STATUSES = {"ANNOTATED", "NOT_APPLICABLE", "UNKNOWN"}
ANCHOR_OUTCOMES = {"ANCHORABLE", "UNANCHORABLE", "UNKNOWN"}
ENTITY_TYPES = {"symptom", "medication", "allergy", "chief_complaint", "task", "risk"}
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
HARD_GATE_KEYS = {
    "silent_speaker_invention_allowed",
    "unknown_to_default_allowed",
    "silent_truncation_allowed",
    "raw_source_overwrite_allowed",
    "unanchored_highlight_persistence_allowed",
    "known_phi_unredacted_egress_allowed",
}
CASE_KEYS = {
    "schema_version",
    "case_id",
    "split",
    "data_classification",
    "description",
    "category",
    "coverage_tags",
    "raw_text",
    "expected_normalize_outcome",
    "expected_canonical_segments",
    "expected_source_ranges",
    "normalize_reason",
    "extraction_expectations",
    "redaction_expectations",
    "anchor_expectations",
    "provider_expectations",
    "hard_gate_annotations",
}
MANIFEST_KEYS = {
    "schema_version",
    "corpus_status",
    "runtime_status",
    "frozen_base_commit",
    "encoding",
    "newline",
    "protocol_limits",
    "splits",
    "frozen_holdout_digest_algorithm",
    "frozen_holdout_digest",
    "cases",
}
class ValidationFailure(Exception):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationFailure(message)


def require_exact_keys(value: dict[str, Any], expected: set[str], label: str) -> None:
    actual = set(value)
    require(actual == expected, f"{label}: keys differ; missing={sorted(expected-actual)}, extra={sorted(actual-expected)}")


def read_json_bytes(path: Path, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValidationFailure(f"{label}: cannot read {path}: {exc}") from exc
    require(not raw.startswith(b"\xef\xbb\xbf"), f"{label}: UTF-8 BOM is forbidden")
    require(b"\r\n" not in raw and b"\r" not in raw, f"{label}: bytes must use LF newlines")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValidationFailure(f"{label}: not valid UTF-8") from exc
    require(text.endswith("\n"), f"{label}: deterministic file must end with LF")
    try:
        value = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValidationFailure(f"{label}: invalid JSON: {exc}") from exc
    require(isinstance(value, dict), f"{label}: JSON root must be an object")
    return value, raw


def valid_range(raw_text: str, value: Any, label: str) -> tuple[int, int]:
    require(isinstance(value, dict), f"{label}: range must be an object")
    start = value.get("source_start")
    end = value.get("source_end")
    require(type(start) is int and type(end) is int, f"{label}: range offsets must be integers")
    require(0 <= start < end <= len(raw_text), f"{label}: range is outside raw_text")
    return start, end


def validate_extraction(case: dict[str, Any], label: str) -> None:
    value = case["extraction_expectations"]
    require(isinstance(value, dict), f"{label}: extraction_expectations must be an object")
    require_exact_keys(value, {"annotation_status", "entities", "task_status", "conflict_expected"}, f"{label}.extraction")
    status = value["annotation_status"]
    require(status in ANNOTATION_STATUSES, f"{label}: invalid extraction annotation_status")
    entities = value["entities"]
    if status == "ANNOTATED":
        require(isinstance(entities, list), f"{label}: annotated extraction entities must be a list")
        for index, entity in enumerate(entities):
            require(isinstance(entity, dict), f"{label}: entity {index} must be an object")
            require_exact_keys(entity, {"entity_type", "text", "assertion_value", "polarity", "source_range"}, f"{label}.entity[{index}]")
            require(entity["entity_type"] in ENTITY_TYPES, f"{label}: invalid entity_type")
            require(isinstance(entity["text"], str) and entity["text"].strip(), f"{label}: entity text must be non-empty")
            require(entity["assertion_value"] is None or isinstance(entity["assertion_value"], str), f"{label}: invalid assertion_value")
            require(entity["polarity"] in {"positive", "negative", "unknown"}, f"{label}: invalid polarity")
            valid_range(case["raw_text"], entity["source_range"], f"{label}.entity[{index}].source_range")
    else:
        require(entities is None, f"{label}: non-annotated extraction entities must be null")
    require(value["task_status"] is None or isinstance(value["task_status"], str), f"{label}: task_status must be string or null")
    require(value["conflict_expected"] is None or type(value["conflict_expected"]) is bool, f"{label}: conflict_expected must be bool or null")


def validate_redaction(case: dict[str, Any], label: str) -> None:
    value = case["redaction_expectations"]
    require(isinstance(value, dict), f"{label}: redaction_expectations must be an object")
    require_exact_keys(value, {"annotation_status", "known_names", "expected_redactions", "unclassified_suspected_phi"}, f"{label}.redaction")
    status = value["annotation_status"]
    require(status in ANNOTATION_STATUSES, f"{label}: invalid redaction annotation_status")
    if status == "ANNOTATED":
        require(isinstance(value["known_names"], list), f"{label}: known_names must be a list")
        require(isinstance(value["expected_redactions"], list), f"{label}: expected_redactions must be a list")
        for index, item in enumerate(value["expected_redactions"]):
            require(isinstance(item, dict), f"{label}: redaction {index} must be an object")
            require_exact_keys(item, {"text", "placeholder_type", "occurrences"}, f"{label}.redaction[{index}]")
            require(item["placeholder_type"] in {"NAME", "ID", "PHONE"}, f"{label}: invalid placeholder_type")
            require(type(item["occurrences"]) is int and item["occurrences"] > 0, f"{label}: invalid redaction occurrence count")
            require(case["raw_text"].count(item["text"]) >= item["occurrences"], f"{label}: redaction text absent from raw_text")
    else:
        require(value["known_names"] is None and value["expected_redactions"] is None, f"{label}: non-annotated redaction fields must be null")
    require(value["unclassified_suspected_phi"] is None or value["unclassified_suspected_phi"] == "unknown", f"{label}: suspected PHI must be null or unknown")


def validate_anchors(case: dict[str, Any], label: str) -> None:
    value = case["anchor_expectations"]
    require(isinstance(value, dict), f"{label}: anchor_expectations must be an object")
    require_exact_keys(value, {"annotation_status", "quotes"}, f"{label}.anchor")
    status = value["annotation_status"]
    require(status in ANNOTATION_STATUSES, f"{label}: invalid anchor annotation_status")
    if status != "ANNOTATED":
        require(value["quotes"] is None, f"{label}: non-annotated anchor quotes must be null")
        return
    require(isinstance(value["quotes"], list) and value["quotes"], f"{label}: annotated anchor quotes must be non-empty")
    for index, item in enumerate(value["quotes"]):
        require_exact_keys(item, {"quote", "expected_outcome", "source_range"}, f"{label}.anchor[{index}]")
        quote = item["quote"]
        outcome = item["expected_outcome"]
        require(isinstance(quote, str) and quote, f"{label}: anchor quote must be non-empty")
        require(outcome in ANCHOR_OUTCOMES, f"{label}: invalid anchor outcome")
        if outcome == "ANCHORABLE":
            start, end = valid_range(case["raw_text"], item["source_range"], f"{label}.anchor[{index}].source_range")
            require(case["raw_text"][start:end] == quote, f"{label}: anchor range does not resolve exact quote")
        elif outcome == "UNANCHORABLE":
            require(item["source_range"] is None, f"{label}: unanchorable quote range must be null")
            require(quote not in case["raw_text"], f"{label}: quote marked unanchorable exists in raw_text")
        else:
            require(item["source_range"] is None, f"{label}: unknown anchor range must be null")


def validate_provider(case: dict[str, Any], label: str) -> None:
    value = case["provider_expectations"]
    require(isinstance(value, dict), f"{label}: provider_expectations must be an object")
    require_exact_keys(value, {"scenario", "primary_result", "fallback_expected", "expected_generation_method", "fallback_reason", "metrics_status"}, f"{label}.provider")
    require(value["scenario"] in {"not_applicable", "invalid_schema", "provider_failure", "placeholder_corruption", "anchor_drop_rate"}, f"{label}: invalid provider scenario")
    require(value["metrics_status"] == "NOT_EVALUATED", f"{label}: provider metrics must remain NOT_EVALUATED")
    if value["scenario"] == "not_applicable":
        for key in ("primary_result", "fallback_expected", "expected_generation_method", "fallback_reason"):
            require(value[key] is None, f"{label}: {key} must be null when provider scenario is not applicable")
    else:
        require(value["fallback_expected"] is True, f"{label}: annotated provider failure must expect fallback")
        require(value["expected_generation_method"] == "deterministic_fallback", f"{label}: fallback generation method must remain separate")
        require(value["primary_result"] in {"invalid_output", "provider_error", "placeholder_error", "anchor_drop_rate"}, f"{label}: invalid provider primary result")
        require(value["fallback_reason"] == value["primary_result"], f"{label}: fallback reason must match classified primary result")


def validate_case(case: dict[str, Any], entry: dict[str, Any], limits: dict[str, Any]) -> None:
    label = entry["path"]
    require_exact_keys(case, CASE_KEYS, label)
    require(case["schema_version"] == 1, f"{label}: unsupported schema_version")
    require(case["case_id"] == entry["case_id"], f"{label}: case_id differs from manifest")
    require(re.fullmatch(r"tr_(?:dev|hold)_\d{3}_[a-z0-9_]+", case["case_id"]) is not None, f"{label}: invalid case_id format")
    require(case["split"] == entry["split"] and case["split"] in SPLITS, f"{label}: invalid split")
    require(case["data_classification"] == "SYNTHETIC_ONLY", f"{label}: corpus must be explicitly synthetic")
    require(isinstance(case["description"], str) and case["description"].strip(), f"{label}: description is required")
    require(isinstance(case["category"], str) and case["category"].strip(), f"{label}: category is required")
    tags = case["coverage_tags"]
    require(isinstance(tags, list) and tags and all(isinstance(tag, str) and tag for tag in tags), f"{label}: coverage_tags must be non-empty strings")
    require(len(tags) == len(set(tags)), f"{label}: duplicate coverage tag")
    raw_text = case["raw_text"]
    require(isinstance(raw_text, str) and raw_text, f"{label}: raw_text must be non-empty")
    outcome = case["expected_normalize_outcome"]
    require(outcome in OUTCOMES, f"{label}: invalid normalize outcome")
    segments = case["expected_canonical_segments"]
    ranges = case["expected_source_ranges"]
    if outcome == "ACCEPT":
        require(isinstance(segments, list) and segments, f"{label}: ACCEPT requires canonical segments")
        require(case["normalize_reason"] is None, f"{label}: ACCEPT normalize_reason must be null")
        require(isinstance(ranges, list) and len(ranges) == len(segments), f"{label}: ACCEPT requires one source range per segment")
        require(len(segments) <= limits["max_segments"], f"{label}: accepted segment count exceeds limit")
        for index, segment in enumerate(segments):
            require_exact_keys(segment, {"index", "speaker", "text", "source_start", "source_end"}, f"{label}.segment[{index}]")
            require(segment["index"] == index, f"{label}: canonical indexes must be continuous from zero")
            require(segment["speaker"] in {"doctor", "patient"}, f"{label}: canonical speaker must be doctor or patient")
            require(isinstance(segment["text"], str) and segment["text"].strip(), f"{label}: segment text must be non-empty")
            require(len(segment["text"]) <= limits["max_segment_text_characters"], f"{label}: accepted segment text exceeds limit")
            start, end = valid_range(raw_text, segment, f"{label}.segment[{index}]")
            require(raw_text[start:end] == segment["text"], f"{label}: canonical segment must be an exact raw range")
            source_range = ranges[index]
            require_exact_keys(source_range, {"segment_index", "source_start", "source_end"}, f"{label}.expected_source_ranges[{index}]")
            require(source_range == {"segment_index": index, "source_start": start, "source_end": end}, f"{label}: duplicated source range disagrees with segment")
    else:
        require(segments is None, f"{label}: blocked outcome canonical segments must be null")
        require(isinstance(case["normalize_reason"], str) and case["normalize_reason"], f"{label}: blocked outcome requires a reason")
        require(ranges is None or isinstance(ranges, list), f"{label}: blocked source ranges must be list or null")
        for index, source_range in enumerate(ranges or []):
            require_exact_keys(source_range, {"issue_index", "source_start", "source_end"}, f"{label}.expected_source_ranges[{index}]")
            require(source_range["issue_index"] == index, f"{label}: issue indexes must be continuous")
            valid_range(raw_text, source_range, f"{label}.expected_source_ranges[{index}]")

    if "overlong_input" in tags:
        require(outcome == "REJECT" and case["normalize_reason"] == "INPUT_TOO_LONG", f"{label}: overlong case must explicitly reject")
        require(len(raw_text.encode("utf-8")) > limits["max_raw_text_bytes"], f"{label}: overlong raw_text does not exceed frozen limit")
    elif outcome == "ACCEPT":
        require(len(raw_text.encode("utf-8")) <= limits["max_raw_text_bytes"], f"{label}: accepted raw_text silently exceeds frozen limit")

    validate_extraction(case, label)
    validate_redaction(case, label)
    validate_anchors(case, label)
    validate_provider(case, label)
    hard_gates = case["hard_gate_annotations"]
    require(isinstance(hard_gates, dict), f"{label}: hard_gate_annotations must be an object")
    require_exact_keys(hard_gates, HARD_GATE_KEYS, f"{label}.hard_gate_annotations")
    require(all(value is False for value in hard_gates.values()), f"{label}: every hard-gate allowance must be false")
    if "unknown_speaker" in tags or "unknown_not_defaulted" in tags:
        require(outcome != "ACCEPT", f"{label}: unknown speaker must not be accepted or defaulted")


def validate_manifest(manifest_path: Path) -> dict[str, Any]:
    manifest, _ = read_json_bytes(manifest_path, "manifest")
    require_exact_keys(manifest, MANIFEST_KEYS, "manifest")
    require(manifest["schema_version"] == 1, "manifest: unsupported schema_version")
    require(manifest["corpus_status"] == "FROZEN", "manifest: invalid corpus status")
    require(manifest["runtime_status"] == "EVALUATED_LOCAL_DETERMINISTIC", "manifest: invalid runtime status")
    require(manifest["frozen_base_commit"] == "ca114ebf6a2a92155aa6a1d6f9e48b934c76b528", "manifest: unexpected frozen base commit")
    require(manifest["encoding"] == "UTF-8" and manifest["newline"] == "LF", "manifest: deterministic byte contract changed")
    limits = manifest["protocol_limits"]
    require(limits == {"max_raw_text_bytes": 4096, "max_segments": 500, "max_segment_text_characters": 4000}, "manifest: protocol limits changed")
    entries = manifest["cases"]
    require(isinstance(entries, list) and 30 <= len(entries) <= 50, "manifest: corpus must contain 30-50 cases")
    require(entries == sorted(entries, key=lambda item: item["path"]), "manifest: cases must be sorted by path")

    root = manifest_path.parent.resolve()
    expected_files: set[str] = set()
    ids: set[str] = set()
    split_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    coverage_counts: Counter[str] = Counter()
    outcome_counts: Counter[str] = Counter()
    holdout_lines: list[str] = []
    for index, entry in enumerate(entries):
        require_exact_keys(entry, {"path", "case_id", "split", "byte_length", "sha256"}, f"manifest.cases[{index}]")
        relative = PurePosixPath(entry["path"])
        require(not relative.is_absolute() and ".." not in relative.parts and relative.parts[0] == "cases" and relative.suffix == ".json", f"manifest.cases[{index}]: unsafe case path")
        require(entry["path"] not in expected_files, f"manifest: duplicate path {entry['path']}")
        require(entry["case_id"] not in ids, f"manifest: duplicate case_id {entry['case_id']}")
        require(entry["split"] in SPLITS, f"manifest: invalid split for {entry['path']}")
        require(type(entry["byte_length"]) is int and entry["byte_length"] > 0, f"manifest: invalid byte_length")
        require(re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]) is not None, f"manifest: invalid sha256")
        target = (root / Path(*relative.parts)).resolve()
        require(os.path.commonpath([str(root), str(target)]) == str(root), f"manifest: case path escapes corpus root")
        case, raw = read_json_bytes(target, entry["path"])
        digest = hashlib.sha256(raw).hexdigest()
        require(len(raw) == entry["byte_length"], f"{entry['path']}: byte_length mismatch")
        require(digest == entry["sha256"], f"{entry['path']}: sha256 mismatch")
        validate_case(case, entry, limits)
        expected_files.add(entry["path"])
        ids.add(entry["case_id"])
        split_counts[entry["split"]] += 1
        category_counts[case["category"]] += 1
        coverage_counts.update(case["coverage_tags"])
        outcome_counts[case["expected_normalize_outcome"]] += 1
        if entry["split"] == "frozen_holdout":
            holdout_lines.append(f"{entry['path']}\t{entry['byte_length']}\t{entry['sha256']}\n")

    actual_files = {path.relative_to(root).as_posix() for path in (root / "cases").glob("*.json")}
    require(actual_files == expected_files, f"manifest: case file set differs; missing={sorted(expected_files-actual_files)}, extra={sorted(actual_files-expected_files)}")
    require(dict(split_counts) == manifest["splits"], "manifest: declared split counts differ from corpus")
    require(split_counts["development"] > 0 and split_counts["frozen_holdout"] > 0, "manifest: both splits are required")
    require(set(outcome_counts) == OUTCOMES, "corpus: ACCEPT, NEEDS_REVIEW and REJECT must all be represented")
    missing_coverage = REQUIRED_COVERAGE - set(coverage_counts)
    require(not missing_coverage, f"corpus: missing required coverage tags {sorted(missing_coverage)}")
    require(manifest["frozen_holdout_digest_algorithm"] == "sha256(path<TAB>byte_length<TAB>sha256<LF>, sorted by path)", "manifest: holdout digest algorithm changed")
    holdout_digest = hashlib.sha256("".join(holdout_lines).encode("utf-8")).hexdigest()
    require(holdout_digest == manifest["frozen_holdout_digest"], "manifest: frozen holdout digest mismatch")
    return {
        "case_count": len(entries),
        "split_counts": dict(sorted(split_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "coverage_counts": dict(sorted(coverage_counts.items())),
        "outcome_counts": dict(sorted(outcome_counts.items())),
        "verified_hashes": len(entries),
        "frozen_holdout_digest": holdout_digest,
    }


def print_report(summary: dict[str, Any]) -> None:
    print("FROZEN_CORPUS")
    print("RUNTIME_EVALUATED_SEPARATELY")
    # Level-accurate marker: this script validates the frozen corpus, not D3 as
    # a whole. The authoritative D3 completion state is the D3 Exit Gate, never
    # a self-reported status emitted here.
    print("CORPUS_VALIDATION_PASS")
    print("VALIDATION_PASS")
    print(f"cases: {summary['case_count']}")
    print("splits: " + json.dumps(summary["split_counts"], sort_keys=True))
    print("outcomes: " + json.dumps(summary["outcome_counts"], sort_keys=True))
    print("categories: " + json.dumps(summary["category_counts"], sort_keys=True))
    print("coverage_tags: " + json.dumps(summary["coverage_counts"], sort_keys=True))
    print(f"manifest_hashes_verified: {summary['verified_hashes']}/{summary['case_count']}")
    print(f"frozen_holdout_digest_verified: {summary['frozen_holdout_digest']}")
    print("runtime_metrics_command: --evaluate-runtime")


def _rate(correct: int, total: int) -> float | None:
    return round(correct / total, 6) if total else None


def _text_leaves(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [leaf for child in value.values() for leaf in _text_leaves(child)]
    if isinstance(value, list):
        return [leaf for child in value for leaf in _text_leaves(child)]
    return []


def _load_cases(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest, _ = read_json_bytes(manifest_path, "manifest")
    root = manifest_path.parent
    cases = [read_json_bytes(root / entry["path"], entry["path"])[0] for entry in manifest["cases"]]
    return manifest, cases


def _new_runtime_counters() -> dict[str, Any]:
    return {
        "normalize_correct": 0,
        "normalize_total": 0,
        "speaker_correct": 0,
        "speaker_total": 0,
        "ambiguous_blocked": 0,
        "ambiguous_total": 0,
        "silent_speaker_invention": 0,
        "silent_truncation": 0,
        "redaction_misses": 0,
        "redaction_expectations": 0,
        "anchor_success": 0,
        "anchor_total": 0,
        "unanchorable_blocked": 0,
        "unanchorable_total": 0,
        "fallback_entity_gold": Counter(),
        "fallback_entity_predicted": Counter(),
        "fallback_entity_true_positive": Counter(),
        "fallback_cases": 0,
        "fallback_candidates": 0,
        "fallback_unanchored_candidates": 0,
        "provider_annotated_cases": 0,
        "conflict_annotated_cases": 0,
        "conflict_positive_cases": 0,
    }


def _finalize_runtime_counters(counter: dict[str, Any]) -> dict[str, Any]:
    gold = sum(counter["fallback_entity_gold"].values())
    predicted = sum(counter["fallback_entity_predicted"].values())
    true_positive = sum(counter["fallback_entity_true_positive"].values())
    task_gold = sum(
        count for (entity_type, _), count in counter["fallback_entity_gold"].items() if entity_type == "task"
    )
    task_predicted = sum(
        count for (entity_type, _), count in counter["fallback_entity_predicted"].items() if entity_type == "task"
    )
    task_true_positive = sum(
        count for (entity_type, _), count in counter["fallback_entity_true_positive"].items() if entity_type == "task"
    )
    return {
        "normalize_outcome": {
            "correct": counter["normalize_correct"],
            "total": counter["normalize_total"],
            "accuracy": _rate(counter["normalize_correct"], counter["normalize_total"]),
        },
        "speaker_mapping": {
            "correct": counter["speaker_correct"],
            "total": counter["speaker_total"],
            "accuracy": _rate(counter["speaker_correct"], counter["speaker_total"]),
        },
        "unsupported_ambiguous_blocking": {
            "correct": counter["ambiguous_blocked"],
            "total": counter["ambiguous_total"],
            "rate": _rate(counter["ambiguous_blocked"], counter["ambiguous_total"]),
        },
        "silent_speaker_invention_count": counter["silent_speaker_invention"],
        "silent_truncation_count": counter["silent_truncation"],
        "phi_redaction": {
            "misses": counter["redaction_misses"],
            "expectations": counter["redaction_expectations"],
        },
        "exact_quote_restore_anchor": {
            "success": counter["anchor_success"],
            "total": counter["anchor_total"],
            "rate": _rate(counter["anchor_success"], counter["anchor_total"]),
        },
        "unanchorable_quotes_blocked": {
            "correct": counter["unanchorable_blocked"],
            "total": counter["unanchorable_total"],
            "rate": _rate(counter["unanchorable_blocked"], counter["unanchorable_total"]),
        },
        "deterministic_fallback": {
            "cases": counter["fallback_cases"],
            "candidates": counter["fallback_candidates"],
            "entity_exact_precision": _rate(true_positive, predicted),
            "entity_exact_recall": _rate(true_positive, gold),
            "entity_true_positive": true_positive,
            "entity_predicted": predicted,
            "entity_gold": gold,
            "task_exact_precision": _rate(task_true_positive, task_predicted),
            "task_exact_recall": _rate(task_true_positive, task_gold),
            "task_true_positive": task_true_positive,
            "task_predicted": task_predicted,
            "task_gold": task_gold,
            "hallucinated_or_unanchored_candidate_count": counter["fallback_unanchored_candidates"],
        },
        "provider_layer": {
            "status": "NOT_RUN",
            "annotated_cases": counter["provider_annotated_cases"],
            "reason": "deepseek provider requires an env key and is not exercised; the frozen runner makes no network/provider calls",
        },
        "conflict_flag": {
            "status": "NOT_EVALUATED",
            "annotated_cases": counter["conflict_annotated_cases"],
            "positive_cases": counter["conflict_positive_cases"],
            "reason": "standalone corpus has no authorized patient DB or clinician-note comparison context",
        },
    }


def evaluate_runtime(manifest_path: Path) -> dict[str, Any]:
    """Run deterministic local layers only; never call a provider or persist data."""
    backend_root = Path(__file__).resolve().parents[1]
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))
    normalizer = importlib.import_module("app.transcript_normalizer")
    redaction = importlib.import_module("app.redaction")
    highlights = importlib.import_module("app.highlights")
    fallback = importlib.import_module("app.deterministic_pipeline")

    manifest, cases = _load_cases(manifest_path)
    by_split = {split: _new_runtime_counters() for split in sorted(SPLITS)}
    for case in cases:
        counter = by_split[case["split"]]
        raw_text = case["raw_text"]
        expected_outcome = case["expected_normalize_outcome"]
        result = normalizer.normalize_transcript(raw_text)
        counter["normalize_total"] += 1
        if result.outcome == expected_outcome:
            counter["normalize_correct"] += 1

        expected_segments = case["expected_canonical_segments"]
        if expected_segments is not None:
            counter["speaker_total"] += len(expected_segments)
            for index, expected in enumerate(expected_segments):
                if index < len(result.segments) and result.segments[index].speaker_candidate == expected["speaker"]:
                    counter["speaker_correct"] += 1
        else:
            counter["ambiguous_total"] += 1
            if result.outcome == expected_outcome and result.outcome != "ACCEPT":
                counter["ambiguous_blocked"] += 1
            if result.outcome == "ACCEPT":
                counter["silent_speaker_invention"] += 1

        if "overlong_input" in case["coverage_tags"] and not (
            result.outcome == "REJECT" and result.reason == "INPUT_TOO_LONG"
        ):
            counter["silent_truncation"] += 1

        if result.outcome != "ACCEPT" or any(
            segment.speaker_candidate is None for segment in result.segments
        ):
            continue
        content = {
            "segments": [
                {"index": segment.index, "speaker": segment.speaker_candidate, "text": segment.text}
                for segment in result.segments
            ]
        }
        redaction_expectation = case["redaction_expectations"]
        known_names = redaction_expectation["known_names"] or []
        redacted = redaction.redact_content(content, known_names)
        redacted_text = "\n".join(_text_leaves(redacted.redacted.content)).lower()
        for item in redaction_expectation["expected_redactions"] or []:
            counter["redaction_expectations"] += item["occurrences"]
            if item["text"].lower() in redacted_text:
                counter["redaction_misses"] += item["occurrences"]

        anchor_expectation = case["anchor_expectations"]
        for item in anchor_expectation["quotes"] or []:
            quote = item["quote"]
            if item["expected_outcome"] == "ANCHORABLE":
                counter["anchor_total"] += 1
                redacted_quote = quote
                for placeholder, original in redacted.placeholder_mapping.items():
                    redacted_quote = redacted_quote.replace(original, placeholder)
                restored = redaction.restore_placeholders(redacted_quote, redacted.placeholder_mapping)
                span = highlights.locate_span(content, restored)
                if span is not None and highlights.extract_text(content, span) == quote:
                    counter["anchor_success"] += 1
            elif item["expected_outcome"] == "UNANCHORABLE":
                counter["unanchorable_total"] += 1
                if highlights.locate_span(content, quote) is None:
                    counter["unanchorable_blocked"] += 1

        extraction = case["extraction_expectations"]
        if extraction["annotation_status"] == "ANNOTATED":
            output = fallback.build_fallback(content, "ai_doctor_consult_summary")
            counter["fallback_cases"] += 1
            predicted = Counter((candidate.entity_type, candidate.quote) for candidate in output.candidates)
            gold = Counter(
                (
                    entity["entity_type"],
                    raw_text[
                        entity["source_range"]["source_start"] : entity["source_range"]["source_end"]
                    ],
                )
                for entity in extraction["entities"]
            )
            counter["fallback_entity_predicted"].update(predicted)
            counter["fallback_entity_gold"].update(gold)
            counter["fallback_entity_true_positive"].update(predicted & gold)
            counter["fallback_candidates"] += len(output.candidates)
            counter["fallback_unanchored_candidates"] += sum(
                1 for candidate in output.candidates if highlights.locate_span(content, candidate.quote) is None
            )

        if case["provider_expectations"]["scenario"] != "not_applicable":
            counter["provider_annotated_cases"] += 1
        if extraction["conflict_expected"] is not None:
            counter["conflict_annotated_cases"] += 1
            if extraction["conflict_expected"] is True:
                counter["conflict_positive_cases"] += 1

    finalized = {split: _finalize_runtime_counters(counter) for split, counter in by_split.items()}
    hard_gates = {
        "silent_speaker_invention": sum(
            result["silent_speaker_invention_count"] for result in finalized.values()
        ),
        "silent_truncation": sum(result["silent_truncation_count"] for result in finalized.values()),
        "known_phi_unredacted_payload": sum(
            result["phi_redaction"]["misses"] for result in finalized.values()
        ),
        "fallback_unanchored_candidate": sum(
            result["deterministic_fallback"]["hallucinated_or_unanchored_candidate_count"]
            for result in finalized.values()
        ),
    }
    normalizer_path = backend_root / "app" / "transcript_normalizer.py"
    return {
        "corpus_cases": len(cases),
        "frozen_holdout_digest": manifest["frozen_holdout_digest"],
        "normalizer_sha256": hashlib.sha256(normalizer_path.read_bytes()).hexdigest(),
        "splits": finalized,
        "hard_gates": hard_gates,
        "raw_source_overwritten": "COVERED_BY_INTEGRATION_TESTS",
        "unanchored_highlight_persisted": "COVERED_BY_INTEGRATION_TESTS",
    }


def print_runtime_report(report: dict[str, Any]) -> None:
    print("D3_RUNTIME_EVALUATION")
    print("PROVIDER_LAYER_NOT_RUN")
    print("DETERMINISTIC_FALLBACK_REPORTED_SEPARATELY")
    print(f"corpus_cases: {report['corpus_cases']}")
    print(f"frozen_holdout_digest: {report['frozen_holdout_digest']}")
    print(f"normalizer_sha256: {report['normalizer_sha256']}")
    for split, result in report["splits"].items():
        print(f"split_{split}: " + json.dumps(result, sort_keys=True))
    print("hard_gates: " + json.dumps(report["hard_gates"], sort_keys=True))
    print(f"raw_source_overwritten: {report['raw_source_overwritten']}")
    print(f"unanchored_highlight_persisted: {report['unanchored_highlight_persisted']}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate or evaluate the frozen synthetic transcript corpus.")
    parser.add_argument("--validate-corpus", action="store_true", help="run corpus/manifest/schema/hash validation")
    parser.add_argument("--evaluate-runtime", action="store_true", help="evaluate deterministic local runtime layers; never calls a provider")
    parser.add_argument("--manifest", type=Path, default=Path(__file__).resolve().parents[1] / "evals" / "transcripts" / "manifest.json")
    args = parser.parse_args(argv)
    if args.validate_corpus == args.evaluate_runtime:
        parser.error("choose exactly one of --validate-corpus or --evaluate-runtime")
    try:
        summary = validate_manifest(args.manifest.resolve())
    except ValidationFailure as exc:
        print("CORPUS_PREPARATION_ONLY", file=sys.stderr)
        print("RUNTIME_NOT_EVALUATED", file=sys.stderr)
        print(f"VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 2
    if args.validate_corpus:
        print_report(summary)
        return 0
    report = evaluate_runtime(args.manifest.resolve())
    print_runtime_report(report)
    if any(value != 0 for value in report["hard_gates"].values()):
        print("HARD_GATE_FAILED", file=sys.stderr)
        return 3
    print("HARD_GATES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
