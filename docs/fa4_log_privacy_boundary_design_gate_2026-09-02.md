# F_A4 Design Gate Review — Log and Operational Privacy Boundary

> Status: `DESIGN_GATE` — current-state review only. No implementation is authorized.
> Date: 2026-09-02
> Scope: scenario 3 (log and operational privacy). This document records the现状审查, sink/data/retention/access inventory, sensitive-field analysis, an allowlist operational-log schema proposal, and a failure-first acceptance plan. It stops at the owner decision point.

## 1. Boundary statements (permanent, unchanged by this review)

- Operational logs (process stderr / stdout) are **not** the clinical `AuditLog`. `AuditLog` is a clinical-scope table inside the encrypted SQLCipher database with its own RBAC read path (`GET /api/events/{id}/audit`, admin `GET /api/access-audit`). The two must keep distinct content and retention contracts.
- Synthetic data only. No real PHI exists in the repository; sentinel journeys are the only honest way to exercise log paths.
- Third-party crash monitoring and Provider-side retention cannot be "proven" by local tests. They are classified `NOT_ESTABLISHED` (crash monitoring) and external-policy (Provider retention) below.

## 2. Current-state review (现状审查)

### 2.1 Application-owned operational logs (Python `logging`)

There is **no** `logging.basicConfig`, `logging.config`, `fileConfig`, `FileHandler`, `StreamHandler`, or log-rotation configuration anywhere in `backend/app`. Python defaults apply: messages at WARNING and above go to **stderr**, no file sink, no rotation, no retention, no deletion. Three named loggers exist and exactly four sites emit:

| Site | Message | Sensitive content? |
|---|---|---|
| `app/main.py:82` | `Patient review sweep failed type=%s` (`type(exc).__name__`) | type name only — safe |
| `app/main.py:146` | `Unhandled application error path=%s type=%s` | **`request.url.path` is a raw path** — see §4 finding F1 |
| `app/ai_pipeline.py:149` | `provider error: %s` (`type(e).__name__`) | type name only — safe |
| `app/llm_client.py:392` | `deepseek usage model=%s input=%s output=%s` | model name + token counts — safe (no content) |

### 2.2 Exception / error responses

- `app/main.py` `RequestValidationError` handler → fixed `422 {"error":{"code":"validation_error","message":"Request validation failed"}}`, never serializes `str(exc)` (which contains rejected input values and internal source locations).
- `app/main.py` unhandled `Exception` handler → generic `500` envelope + the single `path`/`type` log line above. Locked by `tests/security/test_log_sanitization.py`.

### 2.3 Clinical AuditLog

`app/audit.py::add_audit` writes metadata-only rows: `actor_id/actor_role/action/target_type/target_id/from_version/to_version/clinic_id/patient_id/event_id/details(JSON)/created_at`. I reviewed every `details=` write site. `details` carries **structured metadata only** — statuses, reason codes, internal IDs, counts, `confirmation_id` (an identifier, not the HMAC token), provider name, latency, evidence/segment counts, ASR stage/failure_reason. No note/transcript/raw body, no password, no token, no email. `login_failure` deliberately stores `target_id="unknown"` and never the submitted email (`app/api/auth.py:366-376`).

### 2.4 Edge (Caddy) and Uvicorn

- Uvicorn access log: disabled via the documented launch flag `--no-access-log` (`docs/d5_deployment_security_decisions.md:54`). Operator-controlled; **not code-enforced and not asserted by any startup test**.
- Committed `deploy/Caddyfile` contains **no** `log` directive and **no** `admin off`. The only `admin off` / `log {` directives in the repo are in the *test-only* Caddyfile (`tests/security/test_caddy_failure_log_sanitization.py`) and temporary pytest artifacts. This means the committed production Caddyfile relies on Caddy defaults, which enable JSON access logging to stderr and the admin API on localhost:2019. See finding F2.

### 2.5 Frontend

No `console.*` calls exist in `frontend/src`. No analytics/error-tracking SDK in `frontend/package.json` (only React + ReactDOM + Vite/TS tooling).

### 2.6 Third-party crash/monitoring

No Sentry / Datadog / New Relic / etc. SDK in application code. (Grep hits are vendored transitive files under `.tools` only.) → `NOT_ESTABLISHED`.

### 2.7 Provider side

`app/llm_client.py` is the single egress; it accepts `RedactedContent` only, and `app/ai_pipeline.py` redacts before any provider call. Provider-side request retention, logging and regional processing are external policy — **not** code-verified → `NOT_ESTABLISHED` as a product control.

### 2.8 CLI scripts / seed

`seed/seed.py:136` prints `engine.url`. Verified SQLAlchemy masks the SQLCipher password as `***` in both `str()` and `repr()`, but it **does reveal the full DB file path** (e.g. `C:/private/nantingale.encrypted.db`). Other scripts print only status tokens.

## 3. Sink / data / retention / access inventory

| # | Sink | Storage location | Operator access | Retention/deletion | Classification |
|---|---|---|---|---|---|
| 1 | App operational logs | stderr → operator terminal / process manager (no file) | Single-machine operator | **None implemented** | Owned, not retained |
| 2 | Uvicorn access log | disabled via `--no-access-log` | n/a (when off) | n/a | Owned config (operator-controlled) |
| 3 | Caddy access log | stderr (default, JSON) | Single-machine operator | **None implemented** | Owned, **status unverified** (see F2) |
| 4 | Caddy admin API | loopback `:2019` | Local process only | n/a | Access surface (not a log) — **unverified** |
| 5 | Clinical `AuditLog` | encrypted SQLCipher DB | RBAC: `read_audit` (clinical), `admin_read_access_audit` (admin) | No retention policy / no purge | Owned clinical record, encrypted at rest |
| 6 | Error response bodies | HTTP responses | Client | n/a | Owned, fixed envelopes |
| 7 | Seed/script stdout | operator terminal | Single-machine operator | None | Owned CLI output (DB path revealed) |
| 8 | Provider (DeepSeek) payloads | DeepSeek servers (redacted content) | Provider | External policy | **`NOT_ESTABLISHED`** as control |
| 9 | Third-party crash monitoring | — (none present) | — | — | **`NOT_ESTABLISHED`** |
| 10 | Browser console | browser | End user | n/a | No `console.*` in product |
| 11 | Local ASR (faster-whisper) stderr | stderr (library-internal) | Single-machine operator | None | Not captured/controlled |

## 4. Sensitive-field analysis (fields that remain sensitive **without** note text)

1. **Raw request path with resource IDs** (`request.url.path`) — `patient_id`, `event_id`, `artifact_id`, `task_id`, `capture_id`, `session_id`, `decision_id`, etc. are quasi-identifiers that link a request to a specific synthetic person's record. Currently emitted verbatim by `main.py:146`.
2. **Query string** (any future GET param) — Caddy default access logs include the full URI including query; an ID or token in query would be logged.
3. **DB file path** — reveals storage location (seed stdout).
4. **ASR `failure_reason`** (free-form string ≤256 chars stored in `AuditLog.details`, `app/api/voice.py:567`) — sourced from the ASR library; may contain file/model paths. Needs a fixed-code or truncation contract if it remains in audit.
5. **Token counts + model name** — benign individually; acceptable but should stay on the allowlist explicitly.
6. **Identifiers in `AuditLog.details`** — `user_id`, `session_id`, `confirmation_id`, `highlight_id`, `decision_id`, `correction_artifact_id` are internal IDs, already inside the encrypted clinical record, governed by `read_audit` RBAC. They are not operational-log content but are the ceiling for what operational logs must never mirror.

## 5. Findings and first-visible-failure analysis

- **F1 (application-owned gap):** `main.py:146` logs a **raw path**, not a route template. An unhandled 500 on `/api/patients/pat_x/events/evt_y/...` writes `pat_x`/`evt_y` into the operational log. Fix candidate: log the matched route template (`request.scope["route"].path`) and an error code, drop the raw path.
- **F2 (edge-config gap, highest-visibility challenge):** the committed `deploy/Caddyfile` does **not** disable access logging, contradicting `d5_deployment_security_decisions.md:30` ("Production access logging remains disabled"). The existing offline-upstream test proves only that Caddy does not log the request *body* (the fake token was in the JSON body), **not** that access logging is off. Caddy default access log emits `method/uri/status/duration/client_ip` — the URI includes the patient/event/task IDs and any query string. This must be resolved empirically (run the committed Caddyfile, hit sentinel-ID paths, inspect stderr) and then either a `log { output discard }` + `admin off` directive added or the claim reworded.
- **F3 (retention gap):** no operational-log file/rotation/retention/deletion exists at all; operational logs are stderr-only. No clinical `AuditLog` retention/purge exists either. Retention durations are an **owner decision** — this review does not invent them.
- **F4 (minor):** `seed.py` reveals the DB path (not the key) to stdout; ASR `failure_reason` is a free-form audit field.

## 6. Operational-log vs clinical AuditLog separation

- **Operational logs** (allowlisted, stderr/file, non-clinical): route template, method, status, latency, request-id, error code, error type name. Short retention. Never: bodies, transcripts, messages, provider payloads, credentials, tokens, exception text, raw paths, IDs.
- **Clinical `AuditLog`** (encrypted DB, RBAC-read): who/acted-on-what/when + structured metadata. Already metadata-only. Distinct content, distinct retention contract. A4 must **not** add clinical content to operational logs nor operational noise into the clinical audit.

## 7. Allowlist operational-log schema (proposal)

Single structured record, emitted only by the two existing error sites plus an optional access record if the owner re-enables access logging:

```text
{
  "ts": "<iso8601>",
  "level": "error|warning|info",
  "event": "unhandled_error | provider_error | sweep_error | access (optional)",
  "method": "GET|POST|...",            # omit for background tasks
  "route_template": "/api/patients/{patient_id}/events/{event_id}/audit",  # matched route, never raw path
  "status_code": 500,                   # omit for background tasks
  "error_code": "internal_error",       # fixed enum, not exception text
  "error_type": "RuntimeError",         # type name only
  "latency_ms": 12,                     # access record only
  "request_id": "req_..."               # correlation id, not a patient/event id
}
```

Invariants:
- Values come from a fixed allowlist of keys and fixed enums; unknown keys are dropped.
- Route templates are the Starlette matched-route pattern (contains `{param}` placeholders, never values).
- No path, no query, no IDs, no bodies, no headers, no exception text.
- A final synthetic scrubber (regex for IC/ID, phone, `[NAME_n]`/`[ID_n]`/`[PHONE_n]` placeholders, token-like strings) runs as defense in depth — the **last** layer, never the permission to log unsafe values.

## 8. Failure-first acceptance plan (synthetic sentinels → real sinks)

Sentinel set (synthetic only):
- `name`: "SENTINEL_NAME_ALICE_9F3A"
- `ic`: `660101-01-6001` (synthetic IC-format)
- `phone`: `+6012-345-6789`
- `token`: `FA4_SENTINEL_TOKEN_MUST_NEVER_APPEAR`
- `patient_message`: "SENTINEL_PATIENT_MSG_I_FEEL_WORSE_TODAY"
- `provider_payload`: "SENTINEL_PROVIDER_PAYLOAD_SECRET_7D2C"
- `patient_id`/`event_id`/`task_id`: synthetic resource-ID sentinels

Journeys to run and then scan **every actual generated sink**:
1. Validation 422 (rejected body containing name/IC/phone/token sentinels).
2. 404 direct-object route with sentinel `patient_id` in path.
3. Unhandled 500 route with sentinel `patient_id` in path (assert raw path absent, route template present).
4. Provider failure / invalid-output path with `provider_payload` sentinel (assert fallback + no payload in logs).
5. ASR failure path with a sentinel in the failure_reason path (assert audit `details` stays bounded).
6. Caddy upstream-failure and access-log path using the **committed** `deploy/Caddyfile` (assert access-log behavior is what is documented, or the doc is corrected).

Scan targets: process stderr capture, Caddy stderr, seed/script stdout, `AuditLog.details`, HTTP response bodies, and the SQLCipher DB (readable only with the key). A sink passes only when it is **sentinel-free** for the sentinels it must never contain.

Pass/fail is per-sink, so a gap in one sink is reported as a distinct `PARTIAL` rather than masked by an overall green.

## 9. Decisions required from the owner (blocking)

A4 cannot be implemented until these are approved:

1. **Access-log stance (edge):** keep disabled (then the committed Caddyfile must actually be made to disable it — `admin off` + `log { output discard }`) OR adopt the approved minimal format (route-template/status/latency/request-id). This is the F2 resolution.
2. **Operational-log destination & retention period:** stderr-only (no retention) vs. a rotated file; if a file, the retention/deletion duration must be set by the owner (I will not invent durations).
3. **Clinical `AuditLog` retention:** whether a purge/retention window is required at all, and if so its duration and ownership (owner-supplied; distinct from operational retention).
4. **Crash monitoring stance:** remain `NOT_ESTABLISHED` (no SDK) — confirm no third-party crash dashboard is desired for this synthetic demo.
5. **Provider retention stance:** record DeepSeek/Anthropic-compatible retention and regional-processing as **external policy** (`NOT_ESTABLISHED` as a product control) — confirm.
6. **Allowlist schema:** approve the schema in §7 and the `main.py:146` route-template fix (F1).

## 10. Non-claims

This review does not claim regulatory compliance, production-monitoring certification, Provider-side deletion, or a successful audit from empty local logs. It records the current state and the gaps the owner must decide before any F_A4 implementation begins.
