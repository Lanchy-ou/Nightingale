# Nightingale Technical Brief

**Status:** Synthetic-data prototype — verified with explicit limits

**Baseline:** `main` after the 03 Sep 2026 feedback hardening
**Scope note:** The supplied clinic feedback contains numbered scenarios 1–16, followed by a cross-cutting capability checklist. This brief treats that checklist as synthesis item 17; it does not imply that the source document contained a separately numbered scenario 17.

## 1. Current build and integration model

Nightingale is one shared longitudinal care record. A real-world **Event** is the Timeline unit; parallel **Artifacts** preserve the transcript/raw conversation, AI summary, clinician note, staff note, patient instruction, comments, Tasks, revisions, and audit trail without overwriting each other. Every derived Highlight binds to the source Artifact version, exact Span, verbatim quote, and quote hash. The three product projections remain distinct: Timeline explains what happened, Glance shows what matters now, and Patient View shows only what the patient needs to know or do.

```text
Patient -> Event -> Artifact -> exact Span/version/hash
                  |-> Comments / Tasks / Versions / Audit
                  `-> AI summary -> Highlight -> verified raw source

Browser/session -> FastAPI -> RBAC + clinic-scoped loaders -> SQLCipher/SQLite
                              |-> deterministic ranking/read projections
                              `-> redact -> one LLM egress -> validate -> exact anchor
```

The server owns role/clinic/patient scope, authorship, state transitions, safety rules, Task authority, publication gates, and provenance. Provider output may assist language processing but cannot authorize access, modify clinician/staff authority, complete a Task, publish patient instructions, or become its own source. Formal Glance serving remains deterministic `base_only`; experimental learning is Shadow-only.

## 2. Feedback traceability: scenarios 1–9

| # | Assessment | Integration, first failure, and remaining gap |
|---:|---|---|
| 1 | **DOES NOT** | Product login is email/password. A phone/WhatsApp-only patient cannot enter the portal. Server sessions improved identity integrity, but verified phone OTP, consented delivery, and a clinic-assisted offline path do not exist. |
| 2 | **PARTIAL** | `authz.py`, one-query clinic-scoped loaders, foreign keys, ownership triggers, scope indexes, uniform 404s, and a bypass test protect tested routes. A missed route can still leak under SQLite because there is no database row-level security; PostgreSQL RLS and production tenancy certification remain. |
| 3 | **PARTIAL** | Structured logs use allowlisted fields, value validators, PHI scrubbing, metadata-only AuditLog, fixed Voice error codes, and disabled Caddy access logs. Host stderr retention, crash dumps, third-party monitoring, and Provider retention are deployment-owned and not established. |
| 4 | **SURVIVES** | Raw content is recursively redacted before the sole `LLMClient` egress. Placeholders are restored locally and altered placeholders or non-exact quotes fail closed. A future direct SDK/HTTP call is the main regression risk, guarded by tests and the single-egress contract. |
| 5 | **PARTIAL** | Clinic, Admin bootstrap, inherited settings, strict CSV preview/commit, stable external IDs, and conflict/idempotency handling support another clinic without a schema rewrite. Public organisation verification, provisioning, per-clinic billing/support, and RLS-backed tenancy remain absent. |
| 6 | **PARTIAL** | UTF-8 mixed-language text, manual speaker labels, continuous indexes, source review attestations, and exact-span downstream processing are integrated. Local ASR misrecognized two Malay phrases and deterministic fallback is mainly English-keyword based; multilingual clinical validity is unproven. |
| 7 | **DOES NOT** | Voice is record -> stop -> upload -> transcribe -> review. An allergy stated at minute two is not known during the consult. Streaming chunks, incremental risk detection, latency targets, and an alert acknowledgement/escalation lifecycle require a separate product path. |
| 8 | **PARTIAL** | One 30-second total Provider deadline cancels the async request. Consult/Check-in preserve raw input and return labelled deterministic fallback; Copilot becomes unavailable; key verification fails without saving the key. Cancellation was proven locally, not against an intentionally hung live DeepSeek request. |
| 9 | **SURVIVES** | Missing key, 503, timeout, invalid schema, and invalid provenance converge on a server-owned, labelled deterministic fallback. It may conservatively produce zero Highlights and is not equivalent to multilingual Provider understanding. |

## 3. Feedback traceability: scenarios 10–17

| # | Assessment | Integration, first failure, and remaining gap |
|---:|---|---|
| 10 | **SURVIVES** | Optimistic compare-and-swap makes one same-note writer win and gives the stale writer a visible 409/current version. Role-owned sections remain separate; snapshots, diff, revert-as-new-version, and metadata audit explain the outcome. Distributed multi-writer certification and live presence are absent. |
| 11 | **PARTIAL** | Exact-version in-product instruction receipts distinguish Not viewed, Viewed, and Acknowledged. No email/SMS/WhatsApp sender, delivery receipt, retry, bounce, or escalation exists, so a generated external link is not claimed as delivered. |
| 12 | **PARTIAL** | AI output remains a draft until clinician publication. Correction creates a new published version; withdrawal hides active portal content while preserving history and old receipts. External copies cannot be recalled, and medication correctness still relies on clinician review rather than a validated reference service. |
| 13 | **SURVIVES** | Contradictory allergy assertions preserve both exact sources and surface `needs_review` ahead of routine Glance items. The system does not choose which statement is true. The parser is bounded English logic, not validated general clinical NLP. |
| 14 | **PARTIAL** | Importance is explicitly a retrieval-order score, not risk probability. Versioned factors, explanations, protected conflicts/unresolved work, exact sources, and Coverage Review make it falsifiable. No prospective sensitivity/specificity, clinical calibration, or outcome study exists. |
| 15 | **PARTIAL** | Ranking decisions include surfaced, unsurfaced, and excluded candidates; signals are clinic-scoped/content-free with caps, hard protections, replay, freeze, and rollback. Exposure and fatigue bias remain, no real clinician label volume exists, and no trained model is promoted; formal serving stays `base_only`. |
| 16 | **SURVIVES** | Provenance binds source version + exact Span + SHA-256 quote. After edit, the historical snapshot is verified and labelled updated; missing snapshot/span/hash mismatch fails closed. There is no single-screen dependency graph or production archival certification. |
| 17 | **PARTIAL (synthesis)** | The concluding capability checklist integrates immutable provenance, bounded conflict handling, audience-specific projections, post-consult Voice, human speaker/dosage review, CAS collaboration, and Shadow learning. It still fails real-time streaming, diarization, noisy-clinic validation, automatic medical-reference confirmation, user-facing AI regeneration, and production learning. |

**Numbered 1–16 result:** 5 SURVIVE / 9 PARTIAL / 2 DOES NOT. **Cross-cutting item 17:** PARTIAL.

## 4. What we tried, where it failed or stopped

- The first Anthropic-format DeepSeek reproduction spent all 2,000 output tokens on reasoning and returned no final content. The adapter was moved to the OpenAI-compatible final-content protocol with no generated-token limit; one synthetic mixed-language rerun returned a complete strict summary and 4/4 exact anchors. This is contract evidence, not clinical validation.
- Local faster-whisper proved offline mechanics on supplied synthetic audio, but two Malay phrases were misrecognized and there is no diarization. We stopped at explicit human correction/attestation instead of claiming automatic speaker or multilingual accuracy.
- SQLite cannot provide PostgreSQL-style row-level security. Scoped loaders, triggers, foreign keys, indexes, and fault-injection tests reduce blast radius, but production tenancy remains blocked on a database/platform decision.
- The observed-feedback compiler found zero eligible real-clinician pairs. Training correctly stopped; frozen synthetic models remain Shadow-only and no learned model serves Glance.
- A local never-responding HTTP server proved Provider cancellation. We did not deliberately hang the live Provider. External messaging, crash monitoring/retention, streaming alerts, and recall of already-sent content were also not built or falsely simulated.

## 5. Assumptions re-evaluated

**Still stand:** one longitudinal Event -> Artifact -> Span model; raw-source immutability; clinician/staff authority; server-side scope; patient-safe projection; deterministic ranking before learned ranking; synthetic single-machine prototype boundary.

**No longer stand:** email identity is adequate for all patients; redaction-before-model alone closes privacy risk; batch ASR can support real-time alerts; creating a link proves delivery; feedback only on surfaced items is adequate learning evidence; Provider failure means only a returned error rather than a hang.

## 6. Verification and foreseeable failure boundary

Current repository evidence records 714 backend tests collected, 712 passed, and two default-skipped tests that require ignored local-ASR inputs; those two passed when the supplied synthetic inputs were explicitly provided. Frontend contract checks and the 112-module production build passed in the final environment. Scenario-linked tests are indexed in the README.

The most likely first production failures are phone-only patient exclusion, ungoverned host/third-party retention, code-switching ASR error propagation, absence of in-consult alerts, undelivered external links, and over-trust in an uncalibrated ranking score. The build therefore remains a synthetic-data prototype with explicit human gates and fail-closed provenance—not production medical software, clinical validation, production multi-tenancy, or regulatory evidence.
