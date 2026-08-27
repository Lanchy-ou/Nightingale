# Glance warm-path performance baseline

> Generated 2026-08-28T00:21:06 by `backend/scripts/measure_glance.py`.

## Environment

- OS: `Windows-11-10.0.22000-SP0`
- Python: `3.13.5`
- SQLite: `3.50.2`
- Database: throwaway seeded SQLite (single user, local)
- Row counts: {'events': 7, 'artifacts': 14, 'highlights': 9}
- Samples per endpoint per layer: **100** (first **10** discarded as warm-up)

## Method / timing scope

| Layer | Scope | Primary for gate? |
|---|---|---|
| A | FastAPI TestClient in-process: application logic + SQLite query; no network, no browser rendering | **Yes (P95 <= 300 ms)** |
| B | real uvicorn + localhost HTTP round trip: Layer A + ASGI/serialization/loopback overhead | Reference only |

## Results (ms)

### Layer A — in-process handler

| Endpoint | P50 | P95 | Mean | Max |
|---|---|---|---|---|
| glance | 3.814 | 4.429 | 3.868 | 4.668 |
| events | 6.374 | 7.096 | 6.416 | 7.523 |
| patient-view | 5.284 | 6.078 | 5.32 | 6.672 |

### Layer B — HTTP round trip (local)

| Endpoint | P50 | P95 | Mean | Max |
|---|---|---|---|---|
| glance | 3.872 | 4.447 | 3.877 | 4.994 |
| events | 6.335 | 7.025 | 6.386 | 7.335 |
| patient-view | 5.394 | 6.094 | 5.392 | 6.324 |

## E2 / E3 Glance comparison

| Run | Layer A Glance P50 | Layer A Glance P95 |
|---|---:|---:|
| E2 baseline (2026-08-27) | 3.978 | 4.515 |
| E3 (current run) | 3.814 | 4.429 |

These are separate local runs. The difference is reported, not
attributed to E3 as a causal performance effect. Both remain far
below the 300 ms prototype gate. E3 maintenance timing is measured
separately by `scripts/measure_storage_policy.py`.

## Read-path dependency and query guard

`tests/test_read_path_no_llm.py` imports each read module in a clean
interpreter and asserts its transitive import graph contains none of
`ai_pipeline`, `llm_client`, `extraction`, `redaction`,
`deterministic_pipeline`, `conflicts`, `importance_learning` or
`data_decay`. E3 tests also reject Glance queries of storage state,
Artifact or Event history. Glance/patient-view/events do zero LLM
calls and zero extraction at read time.

## Honesty clause

These numbers come from a **single-user local SQLite** database and prove
only that the warm read path performs no synchronous LLM call and no
full-history scan. They do **not** establish distributed or
production-scale capacity, and must not be presented as such.
