# Glance warm-path performance baseline

> Generated 2026-08-26T20:45:42 by `backend/scripts/measure_glance.py`.

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
| glance | 3.233 | 3.926 | 3.288 | 6.126 |
| events | 5.67 | 6.269 | 5.624 | 7.124 |
| patient-view | 3.585 | 4.273 | 3.619 | 5.04 |

### Layer B — HTTP round trip (local)

| Endpoint | P50 | P95 | Mean | Max |
|---|---|---|---|---|
| glance | 3.312 | 3.797 | 3.311 | 4.336 |
| events | 4.739 | 5.512 | 4.83 | 5.894 |
| patient-view | 3.501 | 4.36 | 3.599 | 4.586 |

## Read-path LLM-free guard

`tests/test_read_path_no_llm.py` imports each read module in a clean
interpreter and asserts its transitive import graph contains none of
`ai_pipeline`, `llm_client`, `extraction`, `redaction`,
`deterministic_pipeline` or `conflicts`. Glance/patient-view/events do
zero LLM calls and zero extraction at read time.

## Honesty clause

These numbers come from a **single-user local SQLite** database and prove
only that the warm read path performs no synchronous LLM call and no
full-history scan. They do **not** establish distributed or
production-scale capacity, and must not be presented as such.
