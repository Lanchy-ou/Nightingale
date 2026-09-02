# F_A4 Log and Operational Privacy — Evidence — 2026-09-02 (rev 3)

Status: `IMPLEMENTED_WITH_LIMITS` — revised after owner review round 3. Per-sink, per-field conclusions only; no aggregate "log security passed" claim.

## Boundary

A4 separates operational logs (process stderr, allowlisted structured JSON) from the clinical `AuditLog` (encrypted SQLCipher DB, role-scoped read). It proves what synthetic sentinels can and cannot leave through each sink, and classifies third-party behavior separately. It does not claim regulatory compliance, production-monitoring certification, Provider-side deletion, or a successful audit from empty local logs.

## Review round 2 findings and fixes

| # | Finding | Fix |
|---|---|---|
| P1 | Allowlist restricted field names only; a short free-text value could pass | Per-field **value validators** (`operational_logging.py`): `error_type` must be an exception-name shape (`…Error`/`…Exception`), `model` a fixed allowlist, `route_template` must be sourced from the matched Starlette `BaseRoute`, `request_id` a server-id shape, `method`/`error_code` fixed enums, numerics typed/ranged. Invalid values are DROPPED. |
| P1 | Evidence exceeded actual test coverage (caplog vs real stderr; simplified Caddy config) | Added real-process tests: `tests/security/test_operational_logging_process.py` (real `uvicorn --no-access-log` stderr for 500 + 422, and seed stdout subprocess). |
| P2 | ASR fixed code not enforced at the state machine | `fail_capture()` now rejects any reason outside `CAPTURE_FAILURE_CODES` (ASR codes + `capture_upload_error`); `test_voice_capture_state_machine.py` locks rejection of free text and a file path. |
| P2 | Caddy access log was "enabled then discarded", not off | Removed the two per-site `log` blocks; access logging is now NOT ENABLED (adapted config has no `srv*.logs`). Global error log remains `discard`, with the cost recorded as PARTIAL edge observability. |
| P2 | `emit_log` "never raises" was false (unhashable event escaped) | Whole body wrapped; `isinstance(event, str)` guard before allowlist lookup; JSON `default=str`; validated before scrub. Locked by `test_emit_log_never_raises_on_poisoned_inputs`. |

## Additional real-process finding (round 2)

Starlette 1.6.0 wires the `Exception` handler into `ServerErrorMiddleware`, which **always re-raises** after the handler returns so the server can log it. uvicorn then logs `Exception in ASGI application` with the full raw traceback — including exception text — to `uvicorn.error` stderr. Our sanitized `unhandled_error` record is emitted, but the server's duplicate traceback defeated it. The application handler now marks the exact exception after emitting its sanitized record; `suppress_server_duplicate_tracebacks()` drops a duplicate only when `record.exc_info` contains that marked exception. Unmarked server/middleware exceptions remain visible. Locked by unit filter-boundary tests and the real-uvicorn process journey.

## Review round 3 findings and fixes

| # | Finding | Fix |
|---|---|---|
| P1 | A raw patient/event path still matched the route-template string regex | `emit_log` now accepts `route_template` only as a matched Starlette `BaseRoute` and serializes its code-defined `.path`; plain strings are rejected even when path-shaped. |
| P1 | The uvicorn filter suppressed every record with the standard ASGI error message | The handler marks the exact sanitized exception; the filter suppresses only that marked `exc_info` and preserves unmarked server errors. |
| P2 | The Caddy runtime probe used a reduced config rather than proving the committed config's adapted shape | A new executable test runs `caddy adapt` on `deploy/Caddyfile` and asserts `admin.disabled`, global discard, and the absence of per-server `logs`; the reduced runtime probe is retained only for the upstream-error sentinel. |

## Changes (file:line)

- `backend/app/operational_logging.py` (new): allowlisted events/fields, **per-field value validators**, matched-`BaseRoute` normalization, `_scrub` defense-in-depth, never-raising `emit_log`, and marked-exception-only `suppress_server_duplicate_tracebacks`.
- `backend/app/security.py:116` `generate_request_id`; `:121` `RequestIdMiddleware` (server-generated id, never trusts a client header).
- `backend/app/main.py:81` sweep error → `emit_log("sweep_error", …)`; `:102` registers `RequestIdMiddleware`; `:148` unhandled handler → route template (no raw path); module-level call to `suppress_server_duplicate_tracebacks()`.
- `backend/app/ai_pipeline.py:147` provider error → `emit_log("provider_error", error_type=type(e).__name__)`.
- `backend/app/llm_client.py:390` usage → `emit_log("provider_usage", model, input_tokens, output_tokens)`.
- `backend/app/voice/contracts.py:19` `ASR_FAILURE_CODES`; `:103` fail-closed validator on `ASRResult.failure_reason`.
- `backend/app/voice/state_machine.py` `CAPTURE_FAILURE_CODES` + `fail_capture` fixed-code enforcement.
- `backend/app/api/voice.py:567` audit `details` key `reason` → `error_code`.
- `backend/seed/seed.py:138` prints a path-free message.
- `deploy/Caddyfile`: `admin off` + global `log { output discard }` only (no per-site `log` blocks — access logging not enabled).

## Sink / data / retention / access conclusions (per sink, per field)

| Sink | Field | Conclusion | Evidence |
|---|---|---|---|
| App operational logs (stderr) | route template (never raw path/id) | `PASS` | `test_unhandled_error_logs_route_template_not_raw_path`; `test_emit_log_rejects_raw_path_shaped_as_route_template` |
| App operational logs (stderr) | server request id (never client header) | `PASS` | `…::test_request_id_is_server_generated_not_client_header` |
| App operational logs (stderr) | unknown keys/events | `PASS` | `…::test_emit_log_drops_unknown_fields_and_events` |
| App operational logs (stderr) | invalid field VALUES (free text) | `PASS` | `…::test_emit_log_drops_invalid_field_values` |
| App operational logs (stderr) | scrubber (IC/phone/placeholder/token) | `PASS` | `…::test_scrubber_redacts_phi_patterns` |
| App operational logs (stderr) | never raises on poisoned input | `PASS` | `…::test_emit_log_never_raises_on_poisoned_inputs` |
| App operational logs (stderr) | four events structured JSON | `PASS` | `…::test_all_four_existing_events_are_allowlisted` + `test_structured_events_are_valid_json` |
| Real uvicorn stderr | 500 exception text, 422 rejected value, path id, server traceback | `PASS` | `test_operational_logging_process.py::test_uvicorn_stderr_is_sentinel_free` |
| Seed stdout | DB path | `PASS` | `…::test_seed_stdout_omits_database_path` |
| Provider failure | exception payload / source text | `PASS` | `…::test_provider_failure_never_logs_payload_or_source` |
| ASR failure → AuditLog/DB/API | free-text reason | `PASS` | `test_voice_asr_contract.py::test_failure_reason_must_be_a_fixed_code`; `test_voice_capture_api_lifecycle.py::test_asr_failure_audit_and_db_use_fixed_error_code`; `test_voice_capture_state_machine.py::test_fail_capture_rejects_free_text_reason` |
| Exception body | exception text / rejected input | `PASS` | existing `tests/security/test_log_sanitization.py` still green |
| Caddy access log | request URI | `PASS` (not enabled — no site `log` blocks) | committed-config `caddy adapt` assertion in `test_caddy_access_log_disabled.py` |
| Caddy error log | request URI on upstream failure | `PASS` (global `log { output discard }`) but edge observability `PARTIAL` | same test |
| Caddy admin API | — | `PASS` (`admin off`) | static assertion |
| Uvicorn access log | — | `PARTIAL` (operator `--no-access-log`, not code-enforced) | static assertion (README documents the flag) |
| Clinical `AuditLog` retention/purge | — | `NOT_IMPLEMENTED` / `NEEDS_OWNER_POLICY` | no purge code |
| Host-side stderr capture/retention | — | `NOT_ESTABLISHED` | no log shipper/rotation/retention |
| Third-party crash monitoring | — | `NOT_ESTABLISHED` | no SDK present |
| Provider (DeepSeek) retention | — | external policy; `NOT_ESTABLISHED` as product control | redaction is egress-scrubbing, not a deletion guarantee |

## Regression evidence

- Backend: `601 collected`; `599 passed, 2 skipped` (the 2 skips are the existing local-ASR-input tests).
- Frontend: TypeScript/Vite production build passed (62 modules).
- `git diff --check`: passed. Secret scan: `SECRET_SCAN_PASS`. Caddy `validate`: passed.

## Non-claims

No production log corpus, retention/deletion runtime, third-party crash dashboard, or Provider-retention audit was produced. The uvicorn-stderr journey is a single synthetic subprocess, not a production host. Local synthetic results do not establish production capacity, compliance, or a human-observed monitoring outcome.
