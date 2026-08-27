# Glance warm-path performance baseline

> Generated 2026-08-27T23:31:00 by `backend/scripts/measure_glance.py`.

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
| glance | 3.978 | 4.515 | 3.982 | 4.793 |
| events | 6.607 | 7.298 | 6.605 | 7.474 |
| patient-view | 5.695 | 6.474 | 5.719 | 7.069 |

### Layer B — HTTP round trip (local)

| Endpoint | P50 | P95 | Mean | Max |
|---|---|---|---|---|
| glance | 3.998 | 4.613 | 4.049 | 5.05 |
| events | 6.517 | 7.184 | 6.502 | 7.541 |
| patient-view | 5.396 | 6.34 | 5.436 | 6.99 |

## E2 pre/post comparison

| Run | Layer A Glance P50 | Layer A Glance P95 |
|---|---:|---:|
| E1 baseline (2026-08-26) | 3.233 | 3.926 |
| E2 (2026-08-27) | 3.978 | 4.515 |

These are separate local runs. The difference is reported, not attributed to
E2 as a causal performance effect. Both remain far below the 300 ms prototype
gate.

## Read-path dependency and query guard

`tests/test_read_path_no_llm.py` imports each read module in a clean
interpreter and asserts its transitive import graph contains none of
`ai_pipeline`, `llm_client`, `extraction`, `redaction`,
`deterministic_pipeline`, `conflicts` or `importance_learning`. The E2 required
test additionally captures Glance SQL and rejects any query of
`importance_feedback`, Artifacts or AuditLog. Glance/patient-view/events do
zero LLM calls and zero extraction at read time.

## Honesty clause

These numbers come from a **single-user local SQLite** database and prove
only that the warm read path performs no synchronous LLM call, feedback
aggregation or full-history scan. They do **not** establish distributed or
production-scale capacity, and must not be presented as such.
