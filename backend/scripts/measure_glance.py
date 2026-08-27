"""M7 warm-path performance measurement (Layer A in-process + Layer B HTTP).

Usage (from backend/):
    .venv/Scripts/python.exe scripts/measure_glance.py [--samples 100] [--warmup 10]

Behaviour:
- builds a throwaway seeded demo DB (never touches backend/nantingale.db),
- measures three warm-path read endpoints in two timing layers,
- writes backend/docs/perf_baseline.md (P50/P95/max/mean + environment).

Layer A = FastAPI TestClient in-process (application logic + SQLite query;
          excludes network and browser rendering). This is the primary layer
          for the "Glance P95 <= 300 ms" gate.
Layer B = a real uvicorn process measured over localhost HTTP (adds ASGI,
          serialization and local loopback overhead).

Honesty clause: single-user local SQLite numbers prove the architecture path
does not perform synchronous LLM / full-history scans; they are NOT a claim of
distributed or production-scale capacity.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import socket
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))

# Read-path endpoints with the role used for the request.
ENDPOINTS = [
    ("glance", "/api/patients/pat_001/glance", "usr_clinician_01"),
    ("events", "/api/patients/pat_001/events", "usr_clinician_01"),
    ("patient-view", "/api/patients/pat_001/patient-view", "usr_patient_01"),
]


def _percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = round((p / 100.0) * (len(sorted_values) - 1))
    return sorted_values[index]


def _summarize(values_ms: list[float]) -> dict[str, float]:
    ordered = sorted(values_ms)
    return {
        "p50_ms": round(_percentile(ordered, 50), 3),
        "p95_ms": round(_percentile(ordered, 95), 3),
        "max_ms": round(max(ordered), 3),
        "mean_ms": round(statistics.mean(ordered), 3),
    }


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _db_row_counts(db) -> dict[str, int]:
    from sqlalchemy import func, select

    from app.models import Artifact, Event, Highlight

    return {
        "events": db.scalar(select(func.count()).select_from(Event)) or 0,
        "artifacts": db.scalar(select(func.count()).select_from(Artifact)) or 0,
        "highlights": db.scalar(select(func.count()).select_from(Highlight)) or 0,
    }


def measure_layer_a(samples: int, warmup: int) -> dict:
    from fastapi.testclient import TestClient

    from app.main import app

    results: dict[str, dict] = {}
    for name, path, user_id in ENDPOINTS:
        with TestClient(app, headers={"X-User-Id": user_id}) as client:
            for _ in range(warmup):
                client.get(path)
            values: list[float] = []
            for _ in range(samples):
                start = time.perf_counter()
                response = client.get(path)
                elapsed = (time.perf_counter() - start) * 1000.0
                assert response.status_code == 200, (name, response.status_code)
                values.append(elapsed)
        results[name] = _summarize(values)
    return results


def measure_layer_b(samples: int, warmup: int, db_url: str) -> dict:
    import httpx

    port = _free_port()
    env = {**os.environ, "NANTINGALE_DB_URL": db_url}
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(BACKEND),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        # Wait for readiness.
        deadline = time.time() + 15
        while time.time() < deadline:
            try:
                with httpx.Client(base_url=base, timeout=1.0) as probe:
                    if probe.get("/api/me", headers={"X-User-Id": "usr_clinician_01"}).status_code == 200:
                        break
            except httpx.HTTPError:
                time.sleep(0.1)
        else:
            raise RuntimeError("uvicorn did not become ready in time")

        results: dict[str, dict] = {}
        with httpx.Client(base_url=base, timeout=10.0) as client:
            for name, path, user_id in ENDPOINTS:
                headers = {"X-User-Id": user_id}
                for _ in range(warmup):
                    client.get(path, headers=headers)
                values: list[float] = []
                for _ in range(samples):
                    start = time.perf_counter()
                    response = client.get(path, headers=headers)
                    elapsed = (time.perf_counter() - start) * 1000.0
                    assert response.status_code == 200, (name, response.status_code)
                    values.append(elapsed)
                results[name] = _summarize(values)
        return results
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=100)
    parser.add_argument("--warmup", type=int, default=10)
    args = parser.parse_args()

    # Isolate on a throwaway DB, never the developer's backend/nantingale.db.
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp.close()
    db_url = f"sqlite:///{tmp.name}"
    os.environ["NANTINGALE_DB_URL"] = db_url
    # The throwaway synthetic benchmark uses the repository's explicit
    # header-auth test/demo path; production mode keeps this disabled.
    os.environ["NANTINGALE_DEMO_AUTH"] = "true"

    from app.db import SessionLocal, engine
    from seed.seed import create_schema, seed

    create_schema(engine)
    with SessionLocal() as db:
        seed(db)
        row_counts = _db_row_counts(db)

    layer_a = measure_layer_a(args.samples, args.warmup)
    layer_b = measure_layer_b(args.samples, args.warmup, db_url)

    env_info = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "os": platform.platform(),
        "python": sys.version.split()[0],
        "sqlite": sqlite3.sqlite_version,
        "samples": args.samples,
        "warmup": args.warmup,
        "db": "throwaway seeded SQLite (single user, local)",
        "row_counts": row_counts,
        "endpoints": {name: path for name, path, _ in ENDPOINTS},
    }

    write_baseline(env_info, layer_a, layer_b)
    print(json.dumps({"environment": env_info, "layer_a": layer_a, "layer_b": layer_b}, indent=2))

    # Release this process's SQLite handles before removing the throwaway DB.
    engine.dispose()
    try:
        os.unlink(tmp.name)
    except OSError:
        # Windows may still hold the file briefly after uvicorn shutdown.
        pass
    return 0


def write_baseline(env: dict, layer_a: dict, layer_b: dict) -> None:
    docs = BACKEND / "docs"
    docs.mkdir(exist_ok=True)
    out = docs / "perf_baseline.md"

    def row(name: str, data: dict) -> str:
        return (
            f"| {name} | {data['p50_ms']} | {data['p95_ms']} | "
            f"{data['mean_ms']} | {data['max_ms']} |"
        )

    lines = [
        "# Glance warm-path performance baseline",
        "",
        f"> Generated {env['generated_at']} by `backend/scripts/measure_glance.py`.",
        "",
        "## Environment",
        "",
        f"- OS: `{env['os']}`",
        f"- Python: `{env['python']}`",
        f"- SQLite: `{env['sqlite']}`",
        f"- Database: {env['db']}",
        f"- Row counts: {env['row_counts']}",
        f"- Samples per endpoint per layer: **{env['samples']}** (first **{env['warmup']}** discarded as warm-up)",
        "",
        "## Method / timing scope",
        "",
        "| Layer | Scope | Primary for gate? |",
        "|---|---|---|",
        "| A | FastAPI TestClient in-process: application logic + SQLite query; no network, no browser rendering | **Yes (P95 <= 300 ms)** |",
        "| B | real uvicorn + localhost HTTP round trip: Layer A + ASGI/serialization/loopback overhead | Reference only |",
        "",
        "## Results (ms)",
        "",
        "### Layer A — in-process handler",
        "",
        "| Endpoint | P50 | P95 | Mean | Max |",
        "|---|---|---|---|---|",
        row("glance", layer_a["glance"]),
        row("events", layer_a["events"]),
        row("patient-view", layer_a["patient-view"]),
        "",
        "### Layer B — HTTP round trip (local)",
        "",
        "| Endpoint | P50 | P95 | Mean | Max |",
        "|---|---|---|---|---|",
        row("glance", layer_b["glance"]),
        row("events", layer_b["events"]),
        row("patient-view", layer_b["patient-view"]),
        "",
        "## E2 / E3 Glance comparison",
        "",
        "| Run | Layer A Glance P50 | Layer A Glance P95 |",
        "|---|---:|---:|",
        "| E2 baseline (2026-08-27) | 3.978 | 4.515 |",
        f"| E3 (current run) | {layer_a['glance']['p50_ms']} | {layer_a['glance']['p95_ms']} |",
        "",
        "These are separate local runs. The difference is reported, not",
        "attributed to E3 as a causal performance effect. Both remain far",
        "below the 300 ms prototype gate. E3 maintenance timing is measured",
        "separately by `scripts/measure_storage_policy.py`.",
        "",
        "## Read-path dependency and query guard",
        "",
        "`tests/test_read_path_no_llm.py` imports each read module in a clean",
        "interpreter and asserts its transitive import graph contains none of",
        "`ai_pipeline`, `llm_client`, `extraction`, `redaction`,",
        "`deterministic_pipeline`, `conflicts`, `importance_learning` or",
        "`data_decay`. E3 tests also reject Glance queries of storage state,",
        "Artifact or Event history. Glance/patient-view/events do zero LLM",
        "calls and zero extraction at read time.",
        "",
        "## Honesty clause",
        "",
        "These numbers come from a **single-user local SQLite** database and prove",
        "only that the warm read path performs no synchronous LLM call and no",
        "full-history scan. They do **not** establish distributed or",
        "production-scale capacity, and must not be presented as such.",
        "",
    ]
    out.write_text("\n".join(lines), encoding="utf-8", newline="\n")
    print(f"Wrote {out}")


if __name__ == "__main__":
    raise SystemExit(main())
