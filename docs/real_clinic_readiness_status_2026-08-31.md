# Nightingale Real-Clinic Readiness Status

> Snapshot date: 2026-09-03
> Scope: current repository after F1/A, B5/B11/B12, SL1/SL2 and the SL3 observed-feedback training bridge.
> Product boundary: synthetic-data prototype; not a production medical system, clinical-safety certification, compliance assessment, or public-host readiness claim.

## Purpose

This is the current, plain-language capability ledger for the real-clinic feedback review. It separates what is implemented and verified from what is partial, not implemented, or not run. Plans and intended behavior are never counted as completed capability.

Status meanings:

- `IMPLEMENTED_AND_VERIFIED` — current code exists and relevant automated/runtime evidence passed.
- `IMPLEMENTED_WITH_LIMITS` — the mechanism exists, but important real-world evidence or operating capability is missing.
- `NOT_IMPLEMENTED` — no complete product path exists.
- `NOT_RUN` — the code or protocol may exist, but the named real-world validation was not executed.

## Final 16-scenario status

| # | Status | First visible break / limit | Current improvement |
|---:|---|---|---|
| 1 | `NOT_IMPLEMENTED` | Email/password is still required | Server-session patient identity; no fake phone/WhatsApp path |
| 2 | `IMPLEMENTED_WITH_LIMITS` | No PostgreSQL RLS/production multi-tenant certification | Scoped loaders, uniform 404 and SQLite/SQLCipher ownership defense |
| 3 | `IMPLEMENTED_WITH_LIMITS` | Host/crash/Provider retention not established | Allowlisted scrubbed logs and edge/failure-code boundaries |
| 4 | `IMPLEMENTED_AND_VERIFIED` | No production PHI certification | Raw-first redaction before the single Provider egress |
| 5 | `IMPLEMENTED_WITH_LIMITS` | Deployment-issued setup and synthetic CSV only; no public organization verification/RLS | 24-hour bootstrap, first Admin, idempotent import and clinic AI/Voice overrides |
| 6 | `IMPLEMENTED_WITH_LIMITS` | Clinical code-switching evaluation `NOT_RUN` | Unicode transcript and multilingual local adapter boundaries |
| 7 | `NOT_IMPLEMENTED` | No streaming ASR/in-consult alert | Post-consult processing remains clearly labelled |
| 8 | `IMPLEMENTED_WITH_LIMITS` | External Provider timeout `NOT_RUN` | Total deadline, async cancellation, raw preservation and distinct fallback |
| 9 | `IMPLEMENTED_AND_VERIFIED` | Live error rate not measured | Returning errors enter labelled deterministic fallback |
| 10 | `IMPLEMENTED_AND_VERIFIED` | No distributed writer certification | CAS/409, version/diff/revert and retry UX |
| 11 | `IMPLEMENTED_WITH_LIMITS` | No Email/SMS/WhatsApp delivery, retry, bounce or escalation | Exact-version Patient portal open/ack receipt; no fake external delivery status |
| 12 | `IMPLEMENTED_WITH_LIMITS` | No external notification/recall channel or production clinical validation | Exact-version draft/publish/correct/withdraw lifecycle integrated with B11 receipts |
| 13 | `IMPLEMENTED_AND_VERIFIED` | Bounded English extraction, not clinical NLP validation | Preserve both allergy sources, human review and exact provenance |
| 14 | `IMPLEMENTED_WITH_LIMITS` | No medical calibration/risk probability | Explainable deterministic ranking and correction workflow |
| 15 | `IMPLEMENTED_WITH_LIMITS` | No authorized real label volume or served model | Frozen-synthetic SL2 models plus automatic observed-feedback dataset bridge; Shadow only and serving base-only |
| 16 | `IMPLEMENTED_AND_VERIFIED` | No production archival/DR certification | Version/hash binding, historical resolution and fail-closed mismatch |

## Implemented and verified

### Longitudinal record and role workspaces

- One connected `Patient -> Event -> Artifact -> Span` record model.
- Timeline, Glance, Tasks, clinician/staff workspace, independent Patient View, and Admin oversight.
- AI summaries, raw sources, staff notes, clinician notes, and patient instructions remain separate artifacts.
- Patient View uses an explicit server-side allowlist and does not expose internal notes, comments, audit, scores, or raw clinical AI content.

### Server-side identity and clinic scope

- Product login uses an HttpOnly server session resolved to the database User.
- Role, `clinic_id`, and patient ownership come from the database, not the browser.
- Central authorization rejects cross-clinic access and another patient's record.
- Patient-directory queries are independently filtered by `clinic_id`.
- Cross-clinic and cross-patient automated tests pass.

This verifies the current application logic. It is not a claim of database row-level security or production multi-tenant defense in depth.

### AI boundary, redaction, and fallback

- Raw patient/consult content is committed before derived AI work.
- Known names, IC/ID patterns, and phone-number patterns are redacted before the LLM call.
- `LLMClient` is the single supported model-egress boundary.
- Provider error, missing provider, invalid schema, and invalid provenance can fall back to a deterministic local result.
- Mock, fallback, live-provider, and `NOT_RUN` evidence are reported separately.

### Collaboration and concurrency

- Clinician and staff notes have separate authorship and permissions.
- Editable notes use optimistic concurrency with `expected_version`.
- Same-note concurrent writes produce one winner and a deterministic `409` for the stale writer.
- Full version snapshots, diff, revert, comments, resolution state, Tasks, and metadata-only AuditLog are implemented.

### Allergy-conflict safety repair

- Patient/AI allergy denials are deterministically compared with clinician notes, staff notes, and confirmed Nurse Consult transcripts.
- Contradictions preserve both sources and receive `needs_review`; the system does not decide which statement is true.
- Unresolved clinical conflicts surface ahead of ordinary Glance suggestions.
- `needs_review` blocks negative learning and unsafe decay.

### Immutable Highlight provenance repair

- New Highlights bind to source Artifact ID, source version, exact Span, and SHA-256 of the original quote.
- If an editable source changes, provenance resolves and verifies the historical snapshot instead of applying the old offset to current text.
- Missing snapshots, invalid spans, and hash mismatches fail closed with no claimed quote.
- Copilot does not substitute changed current text for historical Highlight evidence.
- Self-Learning does not learn from a current source that no longer matches the stored binding.
- The migration adds and idempotently backfills the new binding fields for eligible existing Highlights.

### Deterministic Glance and Patient Review workflow (F_A2)

- Each submitted Patient Check-in creates one stable, internal Nurse (`staff`) review Task; approved exact-source patient-reported priority signals also create one clinician review Task.
- AI routing is explicitly unverified and limited to four controlled reason codes. Invalid provenance, invalid output and fallback remain routine Nurse review.
- Nurse verification and clinician review are separate role-scoped actions. Clinicians record outcome and time-sensitivity labels; the system does not turn these into clinical truth.
- Production review/escalation defaults to 720 minutes. Tests use an injected five-minute policy and verify `T+4:59`, `T+5:00` and idempotent repeat behavior without sleeping.
- Role-specific Glance projections are precomputed and PHI-free. Terminal Tasks do not consume the dynamic top five; clinician-confirmed allergy context is returned separately.
- Candidate-level Nurse decisions are persisted; corrected candidates require a same-Event Staff Note, and incomplete candidate review blocks session closure.
- A clinician cannot close `action_required` without linking an active downstream Care Task owned by that clinician or the Nurse queue; time-sensitive action requires a due time.
- Glance exposes the persisted priority band, factor arithmetic and rule versions without running a Provider on read.
- A normal server-session browser journey passed from synthetic patient submission through Nurse verification and clinician completion. No external notification, real-time clinic alert or clinical-validity claim is made.

### Current regression evidence

- Backend collection: 702 tests.
- Result: 700 passed; 2 existing real-local-ASR input-dependent tests skipped.
- Frontend TypeScript/Vite production build: passed, 65 modules transformed.
- `git diff --check`: passed.
- Secret scan: `SECRET_SCAN_PASS`.

The two skips mean the ignored local ASR model/audio inputs were unavailable; they are not reported as passes.

## Implemented with limits

### Multi-clinic support

- The schema and application authorization support multiple `Clinic` rows and clinic-scoped users, patients, Events, Tasks, feedback, and audit records.
- The current fixture exercises two clinics, five patients and eleven users; it is synthetic prototype evidence rather than production-scale coverage.
- F_B5 adds a deployment-issued, 24-hour, single-use setup link that atomically
  creates one Clinic, its first Admin and inherited ClinicSettings, followed by
  the normal Login/Session path.
- Clinic Admin patient import provides strict UTF-8 CSV preview/commit,
  clinic/source external identity, row-level errors/conflicts and idempotent
  repeated/concurrent commit without name-based merge or overwrite.
- F_A3 adds one-query scoped resource loaders, uniform-404 fault-injection tests, an AST bypass gate, active SQLite/SQLCipher foreign keys, metadata-only ownership preflight, ownership triggers and validated scope indexes. A no-op `authorize_scope` cannot expose the tested cross-clinic patient-bound resources.
- This remains application query isolation plus SQLite/SQLCipher ownership enforcement. There is no database Row-Level Security or production multi-tenant certification.
- Provider credentials and Voice model preparation remain device-owned. Each
  Clinic independently chooses inherited/local/online AI and inherited/enabled/
  disabled Voice settings; runtime resolution uses server-authoritative clinic
  scope.
- Deployment remains a single-machine SQLite/SQLCipher prototype.
- This is not public organization verification, real-PHI import certification,
  per-clinic Provider billing, platform administration or PostgreSQL RLS.

### Logging and operational privacy (F_A4 implemented, rev 3, 2026-09-02)

- Application operational logs are allowlisted structured JSON to stderr only, with **per-field value validators** (not just field names): `error_type` must be exception-name shaped, `model` a fixed allowlist, `route_template` is accepted only from the matched Starlette route object, `request_id` a server-generated id, `method`/`error_code` fixed enums, numerics typed/ranged. Invalid values and raw path strings are dropped; a deterministic scrubber (IC/ID, phone, placeholder, long token) is the last layer. `emit_log` never raises.
- All four existing application log events use the allowlist emitter; exception text and raw paths are never logged.
- A real-uvicorn process test proves a raw 500 traceback and 422 rejected value never reach stderr: the handler marks the exact exception after emitting the sanitized record, and the uvicorn filter suppresses only the duplicate traceback for that marked exception; unmarked server errors remain visible.
- ASR `failure_reason` is a frozen fixed-code set enforced at BOTH the `ASRResult` contract and the capture state machine `fail_capture`; Voice audit `details` records `error_code`.
- The committed Caddyfile has `admin off` and a global error-log `discard`; access logging is NOT ENABLED (no per-site `log` blocks), verified by executable `caddy adapt` assertions over the committed file. Edge error-log suppression costs edge fault diagnosis (502/TLS/cert) — edge observability is PARTIAL.
- Seed output no longer prints the database URL/path.
- Failure-first evidence is per-sink/per-field (`PASS`/`PARTIAL`/`NOT_ESTABLISHED`), never an aggregate “log security passed”.
- Not implemented / not established: clinical `AuditLog` purge (NEEDS_OWNER_POLICY), host-side stderr capture/retention, third-party crash monitoring, and Provider-side retention (external policy; redaction is not a deletion guarantee). Uvicorn access logging is operator-controlled (`--no-access-log`), not code-enforced.

### Explicit model-call total timeout (F_A5 implemented, 2026-09-02)

- All four DeepSeek entries (`verify_connection`, `summarize`, `copilot`, Check-in turn/summary) share a 30-second total wall-clock deadline (MVP interaction policy, not a Provider SLA) with bounded connect/pool 5 s, write 10 s, read 30 s phase timeouts and `max_retries=0`.
- Provider calls use the SDK-compatible `anthropic.Timeout` and run through an async client under `asyncio.wait_for`, so a timeout CANCELS the underlying network request rather than leaving a blocking sync thread running.
- A distinct `ProviderTimeoutError` is explicitly caught in all four flows: Consult/Check-in → `fallback_reason="provider_timeout"` + deterministic fallback (raw preserved); Copilot → `unavailable` with no substitute answer; key verification → 503 with no key saved.
- Timeout is logged as the fixed `provider_timeout` reason (not a Python class name) and carries no clinical content.
- A real `AsyncAnthropic` request to a local never-responding HTTP server verifies deadline return and socket disconnect. Check-in also displays patient-safe saved-source + timeout + fallback copy.
- A real server-session patient login opened the independent Check-in page with zero browser warning/error; the timeout-specific state remains API/frontend-contract tested rather than live-Provider browser tested.
- Remaining limit: no live DeepSeek key or external service was used, so a real external Provider timeout was not observed.

### Voice and multilingual consultations

- Manual speaker-labelled Unicode transcripts preserve mixed-language text as entered.
- The local Faster Whisper adapter is multilingual and fail-closed on unknown speaker/low-confidence review issues.
- There is no diarization and no validated Malay-English-Hokkien code-switching accuracy.
- Physical-microphone, noisy-clinic, clinical-entity accuracy, and production-throughput evidence remain `NOT_RUN` in the current environment.
- Deterministic fallback extraction is primarily English keyword based.

### Importance and Self-Learning

- Importance is a transparent retrieval-order heuristic, not a clinical-risk probability.
- Bounded clinic-scoped feedback from real review actions adjusts future candidates by type.
- Caps and hard protections limit negative learning.
- F_A2 now records versioned score factors, role-specific inclusion/exclusion reasons, deterministic priority bands and two-axis clinician review labels.
- F_A1/SL1 records immutable content-free decisions for surfaced, unsurfaced and excluded candidates. Serving is base-only; Hide/Confirm/Pin do not train. Coverage Review and Admin Shadow controls support explicit role-bounded signals, replay, freeze and rollback without serving promotion.
- SL2 trains byte-reproducible staff and clinician pairwise linear models from a frozen 30-scenario synthetic dataset. They run only in Shadow and do not change eligibility, priority bands, protection or formal Glance.
- SL3 automatically compiles eligible explicit outcome labels into a content-free, scope-bound pairwise dataset and exposes an explicit offline training command. It does not infer labels from clicks or missing feedback, does not train on page load and does not serve a model.
- Selection bias remains: only surfaced candidates receive review feedback.
- No real-feedback model has been trained or validated. The current seeded database has zero eligible observed pairs, so SL3 correctly blocks artifact creation. Bayesian adaptation, Bandits, automatic retraining and serving promotion remain unimplemented.
- There is no unsurfaced-candidate sampling, shadow-ranking gate, fatigue/bulk-dismiss detection, clinical-outcome calibration, or clinician usability study.

### Final reason-code stability matrix

- Four approved priority reason codes were evaluated separately across clear positive, negation, historical-only, resolved, ambiguous, correction, multiple people/pronouns and source/span mismatch.
- Mock plus the server validator: `32/32` expected outcomes.
- Deterministic fallback: `28/28` language cases carried no clinician-priority reason code.
- Exact source mismatch: `4/4` dropped.
- Live Provider: `NOT_RUN`; no live pass rate is inferred.
- The first run exposed 19 false-positive mock routes. The final fail-closed validator sends uncertain cases to routine Nurse review while preserving the patient report. This is rule conformance, not medical validity.

### Patient-facing publication

- Patient View exposes only clinician-authored `patient_instruction` artifacts and patient-safe Tasks.
- Copilot-generated patient-instruction drafts require clinician editing and confirmation before creation.
- Exact-version Patient portal receipts distinguish Not viewed, Viewed and Acknowledged; normal Patient View loading does not mark an instruction opened.
- Acknowledgement records only that the authenticated patient read the portal instruction; it is not consent or Task completion.
- Clinician-only publication separates draft, published, superseded and withdrawn states by exact Artifact version and lineage revision.
- Correction preserves historical wording and acknowledgement while creating a new published, Not viewed receipt target.
- Withdrawal hides active Patient View content without deleting Artifact, version, receipt or audit history.
- “Notify” is limited to the in-product new/Not viewed Patient portal state; there is no external notification or recall guarantee.

## Not implemented

### Patient access without email

- Registration and login currently require an email identity and password.
- Phone OTP, WhatsApp authentication, magic-link delivery, clinic-assisted access, and a non-digital patient-delivery path are not implemented.

### External delivery

- The application creates a one-time registration link but sends no real email, SMS, or WhatsApp message.
- Appointment-link delivery, external delivery receipts, retries, bounce/failure handling, and escalation are not implemented.
- Patient portal instruction open/acknowledgement is implemented separately and must not be described as external delivery.

### In-consult real-time clinical alerting

- Consult processing runs after a transcript is submitted or a Voice transcript is reviewed and confirmed.
- There is no streaming ASR plus incremental allergy/risk detection during the consultation.
- Exact provenance is implemented, but it does not make post-consult processing real time.

## Not run or not established

- Real-clinician usability study.
- Production medical-safety validation.
- Malay-English-Hokkien clinical code-switching evaluation.
- Physical microphone and noisy-clinic ASR evaluation in the current final environment.
- Public hosting and external-certificate operations.
- Production multi-user/load/capacity test.
- Penetration test, regulatory assessment, disaster recovery, and compliance certification.
- Production log-retention and third-party monitoring audit.

## Current remediation order

1. Design phone/WhatsApp/non-email patient identity separately from message delivery.
2. Reconsider external delivery only when a real delivery channel is available; do not build a fake provider abstraction.
3. Keep Voice/ASR/dialect/noise validation deferred until it becomes a product priority.
4. Keep real-feedback training and serving promotion blocked while real-clinician evidence is unavailable.
5. Design real-time alerting as a separately validated product capability; do not relabel post-consult processing as real time.

## Maintenance rule

Update this document only when current code/evidence changes. Each status change should identify the relevant implementation, test or runtime evidence. Never convert a planned feature, mock result, fallback result, skipped test, historical run, or owner-reported external action into a verified-current claim.
