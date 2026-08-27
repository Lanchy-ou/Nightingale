"""Measure E3 maintenance paths separately from clinical request latency."""
from __future__ import annotations

import argparse
from datetime import datetime
import json
import os
import platform
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _summary(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    p95_index = round(0.95 * (len(ordered) - 1))
    return {
        "p50_ms": round(statistics.median(ordered), 4),
        "p95_ms": round(ordered[p95_index], 4),
        "mean_ms": round(statistics.mean(ordered), 4),
        "max_ms": round(max(ordered), 4),
    }


def _timed(callable_):
    started = time.perf_counter()
    value = callable_()
    return value, (time.perf_counter() - started) * 1000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--roundtrip-samples", type=int, default=1000)
    args = parser.parse_args()
    if args.roundtrip_samples < 1:
        parser.error("roundtrip-samples must be positive")

    temporary = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    temporary.close()
    os.environ["NANTINGALE_DB_URL"] = f"sqlite:///{temporary.name}"

    from app.data_decay import (
        CODEC,
        build_shadow_archive,
        restore_shadow_archive,
        run_storage_policy,
    )
    from app.db import SessionLocal, engine
    from app.models import Artifact
    from seed import fixture
    from seed.seed import create_schema, seed

    as_of = datetime(2026, 8, 26, 23, 59, 59)
    create_schema(engine)
    with SessionLocal() as db:
        seed(db)
        dry, dry_ms = _timed(
            lambda: run_storage_policy(db, as_of=as_of, apply=False)
        )
        db.rollback()
        first, first_ms = _timed(
            lambda: run_storage_policy(db, as_of=as_of, apply=True)
        )
        second, second_ms = _timed(
            lambda: run_storage_policy(db, as_of=as_of, apply=True)
        )
        content = db.get(Artifact, fixture.ART_HIST_2025_NOTE).content

        roundtrip_ms: list[float] = []
        for _ in range(args.roundtrip_samples):
            def roundtrip():
                archive = build_shadow_archive(content)
                state = SimpleNamespace(
                    codec=CODEC,
                    compressed_payload=archive.compressed_payload,
                    source_sha256=archive.source_sha256,
                )
                return restore_shadow_archive(state)

            restored, elapsed = _timed(roundtrip)
            assert restored == content
            roundtrip_ms.append(elapsed)

        output = {
            "environment": {
                "os": platform.platform(),
                "python": sys.version.split()[0],
                "sqlite": sqlite3.sqlite_version,
                "database": "throwaway seeded SQLite (single user, local)",
                "artifact_count": len(dry.artifacts),
                "roundtrip_samples": args.roundtrip_samples,
            },
            "policy_version": dry.policy_version,
            "as_of": dry.as_of.isoformat(),
            "tier_counts": dry.tier_counts,
            "dry_run_ms": round(dry_ms, 4),
            "first_apply_ms": round(first_ms, 4),
            "identical_rerun_ms": round(second_ms, 4),
            "first_apply_updates": {
                "storage_state": first.updated_count,
                "highlight": first.highlight_updated_count,
            },
            "identical_rerun_updates": {
                "storage_state": second.updated_count,
                "highlight": second.highlight_updated_count,
            },
            "archive_build_restore": _summary(roundtrip_ms),
            "archive_bytes": {
                "original": first.original_bytes,
                "compressed": first.compressed_bytes,
            },
            "limitation": (
                "Synthetic local maintenance-path timings only; shadow payload "
                "coexists with authoritative Artifact.content and is not total "
                "database storage savings."
            ),
        }
        print(json.dumps(output, indent=2, sort_keys=True))

    engine.dispose()
    try:
        os.unlink(temporary.name)
    except OSError:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
