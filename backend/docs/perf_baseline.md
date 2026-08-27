# Glance warm-path performance baseline

> Generated 2026-08-28T03:01:15 by `backend/scripts/measure_glance.py`.

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
| glance | 4.026 | 4.626 | 4.068 | 7.148 |
| events | 7.289 | 8.03 | 7.313 | 8.373 |
| patient-view | 5.867 | 6.521 | 5.822 | 6.87 |

### Layer B — HTTP round trip (local)

| Endpoint | P50 | P95 | Mean | Max |
|---|---|---|---|---|
| glance | 4.402 | 5.115 | 4.381 | 5.484 |
| events | 7.155 | 8.189 | 7.241 | 9.488 |
| patient-view | 5.727 | 6.434 | 5.712 | 6.65 |

## E2 / E3 Glance comparison

| Run | Layer A Glance P50 | Layer A Glance P95 |
|---|---:|---:|
| E2 baseline (2026-08-27) | 3.978 | 4.515 |
| E3 (current run) | 4.026 | 4.626 |

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
