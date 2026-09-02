# Nightingale Real-Clinic Readiness Status

> Snapshot date: 2026-09-01
> Scope: current repository working tree after the F_A2 deterministic Glance and Patient Review implementation.
> Product boundary: synthetic-data prototype; not a production medical system, clinical-safety certification, compliance assessment, or public-host readiness claim.

## Purpose

This is the current, plain-language capability ledger for the real-clinic feedback review. It separates what is implemented and verified from what is partial, not implemented, or not run. Plans and intended behavior are never counted as completed capability.

Status meanings:

- `IMPLEMENTED_AND_VERIFIED` — current code exists and relevant automated/runtime evidence passed.
- `IMPLEMENTED_WITH_LIMITS` — the mechanism exists, but important real-world evidence or operating capability is missing.
- `NOT_IMPLEMENTED` — no complete product path exists.
- `NOT_RUN` — the code or protocol may exist, but the named real-world validation was not executed.

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

- Backend collection: 601 tests.
- Result: 599 passed; 2 existing real-local-ASR input-dependent tests skipped.
- Frontend TypeScript/Vite production build: passed, 62 modules transformed.
- `git diff --check`: passed.
- Secret scan: `SECRET_SCAN_PASS`.

The two skips mean the ignored local ASR model/audio inputs were unavailable; they are not reported as passes.

## Implemented with limits

### Multi-clinic support

- The schema and application authorization support multiple `Clinic` rows and clinic-scoped users, patients, Events, Tasks, feedback, and audit records.
- The current fixture exercises two clinics, five patients and eleven users; it is synthetic prototype evidence rather than production-scale coverage.
- There is no product workflow to create a clinic, bootstrap its first administrator, or import its patients.
- F_A3 adds one-query scoped resource loaders, uniform-404 fault-injection tests, an AST bypass gate, active SQLite/SQLCipher foreign keys, metadata-only ownership preflight, ownership triggers and validated scope indexes. A no-op `authorize_scope` cannot expose the tested cross-clinic patient-bound resources.
- This remains application query isolation plus SQLite/SQLCipher ownership enforcement. There is no database Row-Level Security or production multi-tenant certification.
- AI/Voice settings are device-level rather than clinic-level.
- Deployment remains a single-machine SQLite/SQLCipher prototype.

### Logging and operational privacy (F_A4 implemented, rev 3, 2026-09-02)

- Application operational logs are allowlisted structured JSON to stderr only, with **per-field value validators** (not just field names): `error_type` must be exception-name shaped, `model` a fixed allowlist, `route_template` is accepted only from the matched Starlette route object, `request_id` a server-generated id, `method`/`error_code` fixed enums, numerics typed/ranged. Invalid values and raw path strings are dropped; a deterministic scrubber (IC/ID, phone, placeholder, long token) is the last layer. `emit_log` never raises.
- All four existing application log events use the allowlist emitter; exception text and raw paths are never logged.
- A real-uvicorn process test proves a raw 500 traceback and 422 rejected value never reach stderr: the handler marks the exact exception after emitting the sanitized record, and the uvicorn filter suppresses only the duplicate traceback for that marked exception; unmarked server errors remain visible.
- ASR `failure_reason` is a frozen fixed-code set enforced at BOTH the `ASRResult` contract and the capture state machine `fail_capture`; Voice audit `details` records `error_code`.
- The committed Caddyfile has `admin off` and a global error-log `discard`; access logging is NOT ENABLED (no per-site `log` blocks), verified by executable `caddy adapt` assertions over the committed file. Edge error-log suppression costs edge fault diagnosis (502/TLS/cert) — edge observability is PARTIAL.
- Seed output no longer prints the database URL/path.
- Failure-first evidence is per-sink/per-field (`PASS`/`PARTIAL`/`NOT_ESTABLISHED`), never an aggregate “log security passed”.
- Not implemented / not established: clinical `AuditLog` purge (NEEDS_OWNER_POLICY), host-side stderr capture/retention, third-party crash monitoring, and Provider-side retention (external policy; redaction is not a deletion guarantee). Uvicorn access logging is operator-controlled (`--no-access-log`), not code-enforced.

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
- F_A1 now records immutable content-free decisions for surfaced, unsurfaced and excluded candidates. Serving is base-only; Hide/Confirm/Pin do not train. Coverage Review and Admin Shadow controls support explicit role-bounded signals, replay, freeze and rollback without model training or serving promotion.
- Selection bias remains: only surfaced candidates receive review feedback.
- No Learning-to-Rank, Bayesian adaptation or Bandit is trained; F_A1 remains blocked on evidence quality, coverage and separate approval.
- There is no unsurfaced-candidate sampling, shadow-ranking gate, fatigue/bulk-dismiss detection, clinical-outcome calibration, or clinician usability study.

### Patient-facing publication

- Patient View exposes only clinician-authored `patient_instruction` artifacts and patient-safe Tasks.
- Copilot-generated patient-instruction drafts require clinician editing and confirmation before creation.
- There is no full draft/approve/publish/withdraw/correct/notify/acknowledge lifecycle.
- An incorrect instruction can be superseded by a newer instruction, but the old copy is not recalled from screenshots or external channels.

## Not implemented

### Patient access without email

- Registration and login currently require an email identity and password.
- Phone OTP, WhatsApp authentication, magic-link delivery, clinic-assisted access, and a non-digital patient-delivery path are not implemented.

### Real delivery and receipt tracking

- The application creates a one-time registration link but sends no real email, SMS, or WhatsApp message.
- Appointment-link delivery, delivery receipts, retries, bounce/failure handling, patient-open confirmation, and escalation are not implemented.

### In-consult real-time clinical alerting

- Consult processing runs after a transcript is submitted or a Voice transcript is reviewed and confirmed.
- There is no streaming ASR plus incremental allergy/risk detection during the consultation.
- Exact provenance is implemented, but it does not make post-consult processing real time.

### Explicit model-call total timeout

- Provider errors that return are caught and can trigger deterministic fallback.
- A model request that remains open without returning can continue waiting because the application does not yet set an explicit server-side total timeout.
- The user may remain on “processing” even though the raw transcript was already saved.

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

1. Add an explicit Provider timeout and deterministic timeout fallback.
2. Design phone/WhatsApp/non-email patient identity separately from message delivery.
3. Add delivery status, retry, and receipt tracking for patient links/instructions.
4. Add a patient-instruction publication, correction, withdrawal, and notification lifecycle.
5. Design a small synthetic Malay-English-Hokkien consultation evaluation.
6. Add clinic onboarding and decide whether AI/Voice settings must be clinic-scoped.
7. Add unsurfaced-candidate audit and shadow evaluation before expanding Self-Learning.
8. Design real-time alerting as a separately validated product capability; do not relabel post-consult processing as real time.

## Maintenance rule

Update this document only when current code/evidence changes. Each status change should identify the relevant implementation, test or runtime evidence. Never convert a planned feature, mock result, fallback result, skipped test, historical run, or owner-reported external action into a verified-current claim.
