"""Dry-run or apply the deterministic E3 shadow-storage policy."""
from __future__ import annotations

import argparse
from datetime import date, datetime, time
import json
from pathlib import Path
import sys
import time as clock

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _parse_as_of(value: str) -> datetime:
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("as-of must be YYYY-MM-DD") from exc
    return datetime.combine(parsed, time.max.replace(microsecond=0))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", required=True, type=_parse_as_of)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    from app.data_decay import run_storage_policy
    from app.db import SessionLocal, engine, migrate_e3_schema

    if args.apply:
        migrate_e3_schema(engine)

    started = clock.perf_counter()
    with SessionLocal() as db:
        report = run_storage_policy(db, as_of=args.as_of, apply=args.apply)
        if args.dry_run:
            db.rollback()
    output = report.to_safe_dict()
    output["mode"] = "apply" if args.apply else "dry-run"
    output["elapsed_ms"] = round((clock.perf_counter() - started) * 1000, 3)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
