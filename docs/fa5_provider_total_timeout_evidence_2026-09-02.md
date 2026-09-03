# F_A5 Provider Total Timeout — Evidence — 2026-09-02

Status: `IMPLEMENTED_WITH_LIMITS`. Owner-approved policy (30 s total wall-clock deadline; connect/pool 5 s, write 10 s, read 30 s; `max_retries=0`; async cancellation).

Current protocol revision (2026-09-03): the timeout behavior below is preserved,
but `DeepSeekAdapter` now uses the OpenAI-compatible Chat Completions endpoint
through `httpx`. `_chat_create_async` / `_run_chat_create` replace the historical
Anthropic methods; the request sends no generated-token limit, keeps thinking
enabled, and parses only final `message.content`. The renamed real HTTP
cancellation test still proves socket disconnect against a local
never-responding server.

## Boundary

A5 bounds the complete time a clinician/patient waits for a Provider that never returns. It is an MVP interaction policy, NOT a Provider SLA, background-job rewrite, or a claim that a real DeepSeek request was observed timing out in this environment (no live key was used).

## What changed (file:line)

- `backend/app/llm_client.py`:
  - `PROVIDER_TOTAL_DEADLINE_SECONDS = 30.0`; `PROVIDER_CONNECT/POOL/WRITE/READ = 5/5/10/30` (fixed constants, no env/UI config).
  - `ProviderTimeoutError(LLMError)` — distinct classification.
  - `_run_async_with_total_deadline(coro_factory, deadline)` — `asyncio.run(asyncio.wait_for(...))`; on timeout it CANCELS the coroutine (aborting the underlying async httpx request) and raises `ProviderTimeoutError`. No blocking sync thread is left running.
  - `DeepSeekAdapter._messages_create_async` — lazily imports the SDK-compatible `anthropic.Timeout`, builds `AsyncAnthropic(..., timeout=Timeout(connect=5, pool=5, write=10, read=30), max_retries=0)`, maps `APITimeoutError` → `ProviderTimeoutError`, and closes the client.
  - `DeepSeekAdapter._run_messages_create` — single choke point used by `verify_connection`, `summarize`, `copilot`, and `_bounded_json` (turn + summary). All four entries now go through the async deadline.
- `backend/app/ai_pipeline.py:143` — `except ProviderTimeoutError:` → `fallback_reason="provider_timeout"` + `emit_log("provider_error", error_code="provider_timeout")`; deterministic fallback stays `degraded=True`.
- `backend/app/checkins.py` (turn `_bounded_turn` and `_summary_output`) — `except ProviderTimeoutError:` → `fallback_reason="provider_timeout"` → deterministic fallback.
- `backend/app/schemas.py`, `backend/app/checkins.py`, `frontend/src/types.ts`, `frontend/src/components/PatientCheckIn.tsx` — project only the fixed fallback reason and display patient-safe copy that separates saved words, Provider timeout and safe fallback.
- `backend/app/copilot.py:427` — `except ProviderTimeoutError:` → `status="unavailable"`, `claims=[]`, `draft=None`, distinct limitation text. No substitute answer.
- `backend/app/api/system_settings.py:163` — key verification: `except ProviderTimeoutError:` → 503 "verification timed out"; the key is never stored (store happens only after a successful verify).
- `backend/app/operational_logging.py` — `provider_timeout` added to the error-code allowlist; timeout is logged as the fixed `provider_timeout` reason, not a Python class name.

## Per-flow contract (verified by test)

| Flow | Timeout behavior |
|---|---|
| Consult | `fallback_reason="provider_timeout"`, `degraded=True`, `method="deterministic_fallback"`, raw Transcript preserved |
| Check-in turn/summary | `fallback_reason="provider_timeout"`, deterministic fallback, raw message preserved |
| Copilot | `status="unavailable"`, `claims=[]`, `draft=None`, no substitute answer |
| Key verification | 503, key NOT saved |

## Failure-first tests (`tests/test_fa5_provider_timeout.py`, 7 tests)

- `test_total_deadline_raises_provider_timeout_and_cancels`: a never-completing async provider coroutine with an injected 0.2 s deadline → `ProviderTimeoutError` in `<5 s`; the coroutine observed `CancelledError` (the underlying call was actually cancelled).
- `test_real_async_anthropic_request_uses_phase_timeouts_and_is_cancelled`: the real installed `AsyncAnthropic` client connects to a local HTTP server that accepts the request and never responds; the injected total deadline returns `ProviderTimeoutError` and the server observes the socket disconnect.
- `test_consult_timeout_falls_back_provider_timeout_and_preserves_raw`: `run_pipeline` → `provider_timeout` + raw content unchanged.
- `test_checkin_turn_and_summary_timeout_use_provider_timeout_fallback`: endpoint journey; AI turn and submitted summary both carry `fallback_reason="provider_timeout"`.
- `test_copilot_timeout_unavailable_without_answer`: `answer_query` → `unavailable`, empty claims, no draft.
- `test_key_verify_timeout_returns_503_and_does_not_save`: 503 and the vault never receives the key.
- `test_doctor_consult_timeout_retry_does_not_duplicate_raw`: first consult commits raw Event + Transcript + `provider_timeout` summary; identical re-submit is `idempotent_replay=True` with the same Event/Artifact rows and no duplicates.

## Regression

- A5 targeted: 7 passed.
- Final F1/A full backend: `609 passed, 2 skipped` (the 2 skips are the existing local-ASR-input tests).
- Frontend: TypeScript/Vite production build passed (62 modules). Consult shows the saved raw transcript and exact fallback reason; Check-in now shows patient-safe saved-source + timeout + safe-fallback copy.
- Browser: a real server-session login as the synthetic Alice patient opened the independent Check-in page with zero console warning/error. The timeout-specific state was not triggered because no live external Provider timeout was run.
- `git diff --check`: passed. Secret scan: `SECRET_SCAN_PASS`.

## Remaining limits / non-claims

- No live DeepSeek key or external service was used, so a real external Provider timeout was NOT observed. The executable network evidence uses the real installed `AsyncAnthropic` client against a local never-responding HTTP server plus an injected short deadline.
- The timeout-specific browser state remains contract/build tested rather than live-Provider browser tested.
- The async deadline is exercised through `asyncio.run` from the existing synchronous endpoints; this is the single-process prototype path, not a production multi-worker claim.
- No browser session was run in this environment; the frontend build and the already-wired `fallback_reason`/`degraded` fields are the only frontend evidence.
- `LocalLLMClient`/`MockLLMClient` are synchronous and bounded and are intentionally not routed through the async deadline.
