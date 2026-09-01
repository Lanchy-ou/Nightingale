# Nightingale Real-Clinic Readiness Status

> Snapshot date: 2026-08-31
> Scope: current repository working tree after the allergy-conflict and immutable-provenance repairs.
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

### Current regression evidence

- Backend collection: 538 tests.
- Result: 536 passed; 2 existing real-local-ASR input-dependent tests skipped.
- Frontend TypeScript/Vite production build: passed, 60 modules transformed.
- `git diff --check`: passed.

The two skips mean the ignored local ASR model/audio inputs were unavailable; they are not reported as passes.

## Implemented with limits

### Multi-clinic support

- The schema and application authorization support multiple `Clinic` rows and clinic-scoped users, patients, Events, Tasks, feedback, and audit records.
- The current fixture and tests exercise two clinics.
- There is no product workflow to create a clinic, bootstrap its first administrator, or import its patients.
- Direct object access still relies heavily on the central authorization check; there is no database row-level security or equivalent second tenant-policy engine.
- AI/Voice settings are device-level rather than clinic-level.
- Deployment remains a single-machine SQLite/SQLCipher prototype.

### Logging and operational privacy

- Application error bodies and application-owned log messages avoid raw clinical content.
- Production access logging is disabled in the documented secure-demo topology.
- Audit rows contain metadata rather than note/transcript bodies.
- No production log-retention/deletion policy, central log scrubber, long-running production log audit, or third-party crash/monitoring evidence exists.
- Provider-side request retention and regional-processing policy are not implemented as a product control.

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
- Selection bias remains: only surfaced candidates receive review feedback.
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
