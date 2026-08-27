# AGENTS.md — Nightingale 72 Hour Build Execution Contract

## 0. Mission

Build a working, safe prototype of a shared longitudinal patient care record system.

The product is NOT:

- a generic EHR clone;
- a generic Notion page;
- a standalone AI chatbot;
- an LLM-only summarization demo;
- a model-training project.

The system must demonstrate a coherent care workflow across time, roles, AI-generated content, clinician-authored content, provenance, permissions, and prioritized information.

Primary product principle:

> Timeline = what happened.
> Glance View = what matters now.
> Patient View = what the patient needs to know/do.

Do not deviate from this model without explicit owner approval.

---

## 1. Product Invariants

### 1.1 One longitudinal record

All patient history must be organized around one longitudinal patient record.

Do NOT create disconnected conceptual silos such as:

- doctor database;
- patient database;
- AI database;
- nurse database.

Physical storage may use multiple tables/services, but the product model must remain one connected longitudinal record.

---

### 1.2 Event is the timeline unit

Timeline should primarily display real-world Events, not flatten all underlying documents.

Examples:

- patient_ai_preconsult
- nurse_consult
- doctor_consult
- patient_followup
- clinician_review

Each Event may own multiple Artifacts.

---

### 1.3 Artifacts are parallel representations

An Event may produce:

- raw_conversation
- recording
- transcript
- ai_summary
- clinician_note
- staff_note
- patient_instruction
- task

Do not overwrite raw source with AI summary.

Do not overwrite AI summary with clinician note.

Do not treat AI summary as equivalent to clinician-authored assessment.

---

### 1.4 Clinician authority

If AI/patient-derived information conflicts with clinician-authored information:

- clinician-authored information has higher authority, OR
- explicitly flag the conflict for review.

Never silently merge conflicting statements.

---

## 2. Core Data Model

Implement an explicit relationship similar to:

```text
Patient
  ↓
Optional Care Episode (longitudinal grouping, e.g. a multi-week headache workup)
  ↓
Event
  ↓
Artifact
  ↓
Span
```

Design principle:

> The patient record is a multi-scale longitudinal structure. The main Timeline organizes real-world clinical Events, while each Event preserves the chronological lifecycle of its artifacts, collaboration, tasks, revisions, and provenance.

Rules:

- Event remains the core display unit of the main Timeline; Care Episode is an optional upper grouping and must NOT expand the MVP scope.
- An Event internally preserves its chronological lifecycle: raw consult / transcript, AI summary, clinician note, staff/nurse supplement, comments / thread, tasks, revisions / revert, later review actions.
- Distinguish two time axes explicitly:
  - `event_time / started_at / ended_at` — when the real-world clinical event happened;
  - `created_at / updated_at` — when information about the event was produced or modified.
- Later modifications belong to the original Event; they must NOT surface as new medical events merely because the modification happened on another day.
- UI uses progressive disclosure instead of infinitely nested timelines: longitudinal history / episode → Event detail → Artifact / thread / revision detail → provenance source span.
- The data model may support finer-grained time structure, but the UI must NOT flatten all audit/activity into the patient main Timeline.

AI-scribed artifact contract:

- `author_role = "system"` for all AI-scribed artifacts.
- Minimum supported types:

```text
ai_doctor_consult_summary
ai_nurse_consult_summary
ai_patient_session_summary
```

- AI-scribed artifacts must:
  - be stored independently from human-authored notes;
  - have an Event association;
  - carry a provenance pointer (e.g. session_id for AI-patient interactions);
  - never overwrite clinician/staff-authored artifacts.

Minimum conceptual entities:

- Patient
- Event
- Artifact
- Span / source location
- Highlight
- Comment
- Version
- Task
- AuditLog
- User
- Role / Clinic scope

Recommended minimum Event fields:

```text
event_id
patient_id
event_type
started_at
ended_at
created_at
clinic_id
```

Recommended minimum Artifact fields:

```text
artifact_id
event_id
artifact_type
author_role
author_id
content
created_at
version
provenance_pointer
```

Recommended Highlight fields:

```text
highlight_id
patient_id
event_id
artifact_id
source_span
text
importance_score
risk_reason
status
created_at
```

`source_span` must be able to resolve to a specific location when possible:

- message id;
- paragraph;
- transcript segment;
- timestamp range;
- structured section.

### 2.1 Terminology mapping to Candidate Brief (Entry → Event/Artifact)

The internal model uses finer granularity than the Brief's `Entry`; do NOT regress to a coarse `Entry`. The final Technical Brief must explicitly show this mapping so reviewers can map our schema to the Brief's required schema (Entries ↔ Comments ↔ Versions ↔ Highlights ↔ Provenance ↔ AI_Scribed_Notes):

```text
Brief "Entry"                  → internal Event (real-world clinical event)
                                  + its Artifacts (parallel representations)
Brief AI-scribed note / Entry  → AI-summary Artifact (author_role = system)
Brief "exact source" / msg     → internal Span (source location within an Artifact)
Brief Comments / Thread        → internal Comment (attached to Artifact / Event)
Brief Versions / Revision      → internal Version (snapshot/diff of an editable Artifact)
Brief Highlights               → internal Highlight (points to Artifact + Span)
Brief Provenance pointer       → provenance_pointer = Event → Artifact → Span
```

Keep `Event → Artifact → Span` as the canonical internal model.

---

## 3. Provenance Is Mandatory

Every AI-derived or highlighted item must remain traceable.

Required logical chain:

```text
Glance Highlight
    ↓
Derived Artifact / AI Summary
    ↓
Source Artifact
    ↓
Exact source span
```

A click from Glance View must resolve to the source timeline entry/span.

Do not implement provenance as decorative metadata only.

The system should be able to answer:

1. Which Event produced this information?
2. Which Artifact contains it?
3. Which exact source span supports it?
4. Who/what authored the source?
5. When was it created?

---

## 4. Views

### 4.1 Timeline View

Must show chronological patient Events.

Each Event should be expandable to show related Artifacts.

Support filters such as:

- All
- AI Summaries
- Original Records
- Clinician Notes
- Staff Notes
- Patient Updates
- Tasks
- Risks

These are filters/projections over connected data, not separate data stores.

---

### 4.2 Glance View

Must be readable/actionable in under 10 seconds.

Do not send the full patient history to an LLM on every page load.

Glance should contain only the highest-value current items.

Candidate factors:

- recency;
- explicit clinical risk;
- unresolved tasks;
- clinician-confirmed items;
- symptom change;
- medications;
- allergies;
- chief complaint;
- repeated mentions;
- stale/resolved penalty.

Every highlight must include:

- text;
- risk_reason;
- provenance pointer;
- accept/reject capability;
- source navigation.

Optional:

- pin;
- clinician edit;
- confidence marker.

---

### 4.3 Patient View

Patient View must NOT expose the full clinician workspace.

Allowed content:

- patient-facing summaries;
- instructions;
- tasks;
- follow-up schedule;
- recovery guidance;
- patient AI interaction.

Forbidden:

- internal clinician comments;
- internal staff comments;
- raw AI-scribed clinical notes;
- unauthorized internal clinical reasoning.

---

## 5. AI Responsibilities

### 5.1 Use AI for language understanding

AI may:

- summarize patient sessions;
- summarize consult transcripts;
- extract symptoms;
- extract medications;
- extract tasks;
- extract candidate risks;
- generate patient-facing language;
- generate candidate highlights;
- suggest structured entities.

### 5.2 Do not make the LLM the sole ranking authority

MVP importance ranking should be transparent and deterministic.

Use rule-based or weighted scoring first.

Example conceptual score:

```text
score =
  recency_weight
+ risk_weight
+ unresolved_task_weight
+ clinician_confirmed_weight
+ symptom_change_weight
+ repeated_mentions_weight
- stale_penalty
- resolved_penalty
```

Do NOT fine-tune a model merely to imitate synthetic labels.

---

## 6. Self-Learning Bonus

Only implement after the core product works.

Collect interactions:

- accept;
- reject;
- pin;
- edit;
- comment.

A minimal adaptive system is acceptable:

```text
pin candidate of type X
→ increase X-related weight

reject candidate of type Y
→ decrease Y-related weight
```

Store the feedback and resulting weight changes.

Bonus test should demonstrate that similar future items receive increased/decreased priority.

Do not build a complex learned ranking model unless core gates are already passing.

---

## 7. RBAC

Roles:

- patient
- staff
- clinician
- admin

Enforcement must be server-side.

Minimum rules:

### Patient

Can:

- view patient-facing summaries/instructions;
- interact with patient AI flow.

Cannot:

- view internal clinician comments;
- view internal staff comments;
- access raw clinical AI-scribed notes.

### Staff

Can:

- view/add staff notes within clinic scope.

Cannot:

- overwrite clinician notes;
- access another clinic's patient data.

### Clinician

Can:

- view/edit clinician sections;
- view staff notes;
- view AI-scribed notes;
- access data only within clinic scope.

Cannot:

- overwrite staff-authored content as if authored by clinician.

### Admin

Clinic-scoped oversight.

Never rely on frontend-only guards.

---

## 8. Revision / Audit / Collaboration

Required behavior:

- every editable note has a version;
- edit increments version;
- store full snapshots or diffs (architectural choice);
- previous versions remain retrievable;
- "view changes since X" must be supported (diff view);
- revert restores previous content;
- audit metadata records actor/action/time;
- concurrent edits to different sections must not overwrite each other;
- same-section conflict must use a deterministic strategy.

Preferred optional collaboration:

- threaded comments;
- resolve/unresolve;
- @mentions;
- assignments.

---

## 9. Privacy / Security

Use synthetic data only.

Before any text is sent to an LLM, include a redaction step for:

- names;
- IC / ID numbers;
- phone numbers.

Architecture must explicitly represent:

- PHI-redaction-before-LLM;
- TLS in transit;
- encryption at rest;
- sanitized logs.

Do not log raw patient content unnecessarily.

---

## 10. Performance

Warm-path Glance View target:

```text
P95 <= 300 ms
```

Design accordingly:

- precompute candidate highlights;
- update rankings incrementally;
- cache read-heavy glance data;
- avoid synchronous full-history LLM calls.

Document the measurement/approximation method.

---

## 11. Required Tests — Hard Gate

Do not declare MVP complete unless these pass:

### `test_rbac_scope.py`

Must assert:

- staff cannot write/edit as clinician;
- clinician cannot write/edit as staff;
- patient cannot access internal comments;
- patient cannot access raw AI-scribed clinical notes;
- clinic scope is enforced.

### `test_revision_history.py`

Must assert:

- edit increments version;
- revert restores previous content;
- audit metadata records who changed what.

### `test_highlight_provenance.py`

Must assert:

- generated highlights have provenance;
- provenance resolves to Event/Artifact/span.

### `test_concurrent_edits.py`

Must assert:

- different-section edits do not overwrite;
- same-section conflict uses deterministic resolution.

### Bonus: `test_self_learning_importance.py`

Demonstrate that simulated clinician feedback changes future ranking.

---

## 12. Build Order

Follow this order unless blocked:

### M1 — Skeleton + Data Model

- project scaffold;
- synthetic users/clinics/patients;
- Event/Artifact/Highlight schema;
- provenance relationships.

Exit gate:
- sample patient can have multiple Events and Artifacts;
- source links resolve correctly.

### M2 — Timeline

- chronological Event list;
- Event expansion;
- Artifact filters;
- source navigation.

Exit gate:
- one patient journey can be followed end-to-end.

### M3 — Glance View

- candidate extraction;
- deterministic importance ranking;
- top items;
- risk reasons;
- provenance navigation.

Exit gate:
- Glance is useful without reading full Timeline.

### M4 — Patient View

- patient-facing summary;
- instructions;
- tasks/follow-up;
- patient AI interaction.

Exit gate:
- patient cannot access internal clinical content.

### M5 — RBAC + Audit

- server-side authorization;
- versioning;
- revert;
- audit.

Exit gate:
- RBAC + revision tests pass.

### M6 — AI Flow

- patient AI summary;
- consult transcript summary;
- candidate extraction;
- source linkage.

Exit gate:
- AI content is clearly labeled and traceable.

### M7 — Test Completion

All required micro-tests passing.

### M8 — Bonus

Only if core is stable (required gates + required tests passing); bonus work must never block the MVP:

- adaptive importance;
- Ambient Voice Capture, with hard boundaries:
  - patient voice capture: patient view only (PWA mobile; redact PHI before LLM; transcribe; extract structured facts; generate patient consult session summary);
  - clinical/staff voice capture: clinical view only (PWA mobile or laptop; speaker-labelled transcript, timestamps, confidence markers, code-switching support, clinical summary, provenance back to source segments);
  - noisy environments, diarization, overlap handling, multilingual medical terminology, multi-device capture = extra bonus, not current priority;
- Hybrid Storage / Data Decay:
  - recent / clinically important information stays highly accessible;
  - older low-value data may be summarized / compressed / archived;
  - raw source and provenance must never be lost to compression;
  - clinician-confirmed / unresolved / high-risk information must not simply decay.

---

## 13. Demo Data Requirement

Build a synthetic longitudinal story that demonstrates change over time.

Recommended patient example:

### Event 1 — Pre-consult

- headache once weekly → near daily;
- nausea;
- AI summary generated.

### Event 2 — Nurse consult

- elevated BP;
- AI nurse summary.

### Event 3 — Doctor consult

- transcript;
- AI doctor summary;
- clinician assessment;
- blood test ordered;
- follow-up scheduled.

### Event 4 — Patient follow-up

- headache improves;
- nausea persists;
- incomplete task.

### Event 5 — Clinician review

- updated plan;
- timeline and glance change.

The same synthetic journey should power:

- Timeline demo;
- Glance demo;
- Patient View;
- provenance;
- revision;
- self-learning bonus if implemented.

Include 1–2 earlier historical Events (cross-month or cross-year, e.g. an initial headache workup in 2025-04-15 and a medication review in 2026-02-06) that connect into the current 2026-08 care episode, so the demo shows true longitudinal context rather than a single week.

Avoid building many shallow fake patients when one deep longitudinal example is more useful.

---

## 14. UX Principle

Do not optimize for feature count.

The primary UX test is:

> Can a clinician open the page and understand the patient's current state and next actions in under 10 seconds?

Secondary test:

> Can the clinician verify where every important statement came from?

Patient UX test:

> Can the patient understand what to do next without seeing internal clinical workspace content?

---

## 15. Explicit Non-Goals for MVP

Do not prioritize before required gates pass:

- model fine-tuning;
- custom foundation model;
- complex multi-agent architecture;
- advanced RAG framework;
- production-grade medical diagnosis;
- sophisticated voice diarization;
- multilingual medical NLP;
- personalized learned ranking;
- large-scale data pipeline;
- visual polish beyond demo clarity.

---

## 16. Completion Definition

The build is considered core-complete when:

1. A synthetic patient journey exists across multiple dates.
2. Events and Artifacts are correctly connected.
3. Timeline supports chronological and typed browsing.
4. Glance View surfaces current priorities.
5. Every Glance item has working provenance.
6. Patient View exposes only authorized patient-facing content.
7. Clinician/staff boundaries are server-enforced.
8. AI summaries remain distinct from clinician notes.
9. Revision history and revert work.
10. Required tests pass.
11. README explains setup & run instructions, how to run the automated tests, where redaction happens, how RBAC is enforced, architecture, and trade-offs.
12. Demo can clearly show the three main scenarios.
13. All final deliverables exist:
    - working Git repository with clear commit history;
    - automated tests (the required micro-tests in §11);
    - 2–3 page Technical Brief: architecture diagram + explanation, comprehensive schema (Entries/Events ↔ Artifacts ↔ Comments ↔ Versions ↔ Highlights ↔ Provenance ↔ AI-scribed notes ↔ learning mechanism), assumptions / first-principles / trade-offs;
    - `ATTRIBUTION.txt` listing all external libraries, models, and their licenses;
    - demo video clearly demonstrating the chosen scenarios.

---

## 17. Deadline & Submission

```text
Deadline: 2026-08-28 17:30 SGT/MYT
To:      irakumar@ntngale.com
CC:      frank.ng@ntu.edu.sg, carrene.teo@ntu.edu.sg
Subject: Nightingale 72HR Build -- <Your Name>
```

Final submission includes: repo link (or zip), technical brief, and all required deliverables. Submit by email with the subject line above; the email must reach the To/CC addresses by the deadline.

Under deadline pressure, execution priority is:

```text
required gates > bonus features > polish
```

---

## 18. Agent Working Rule

When uncertain, prefer:

1. correctness;
2. provenance;
3. access control;
4. coherent end-to-end workflow;
5. deterministic behavior;
6. demo clarity;

over:

- extra features;
- architectural cleverness;
- model complexity;
- UI polish.

If a proposed feature weakens provenance, role boundaries, or the main longitudinal workflow, do not implement it without explicit owner approval.

---

## 19. M1–M4 Implementation Status (2026-08-26)

M1 (skeleton + canonical fixture), M2 (Glance → Provenance vertical slice), and M3 (collaboration + revision + RBAC + concurrency) are complete. Concrete conventions that later phases MUST respect:

- **Schema location**: `backend/app/models.py`. Current tables: `clinics` / `users` / `patients` / `events` / `artifacts` / `highlights` / `comments` / `artifact_versions` / `audit_logs`. Task table is Phase 3-remainder (assignment) — not yet added.
- **Span is NOT a table**: expressed as a JSON pointer `{"kind", "index", "offset"}` where `kind ∈ segment|message|paragraph|timestamp_range|section`. Artifact spans live in `Artifact.provenance_pointer`; Highlight spans live in `Highlight.source_span`.
- **Canonical fixture = single source of truth**: `backend/seed/fixture.py` (IDs + 6 FACTS + `HIGHLIGHT_CANDIDATES`). Fixture now has 2 clinics, 2 patients, 6 users (for RBAC isolation tests). Any new narrative must stay consistent with `FACTS` and `tests/test_seed_integrity.py`.
- **author_role semantics**: AI summaries = `system` (author_id null); raw_conversation = `patient`; transcript = `system`; clinician_note/patient_instruction = `clinician`; staff_note = `staff`.
- **Span anchoring rule (permanent)**: candidates carry a verbatim `quote`; spans are located by deterministic string matching in `app/highlights.py` (`locate_span` / `extract_text`). A failed match DROPS the candidate — never fabricate a span. Phase 4 LLM must follow this same contract.
- **Importance scoring**: transparent constant weights in `app/highlights.py` (`WEIGHTS` + `compute_score`), precomputed at write time; Glance read path does zero computation. `GLANCE_LIMIT = 5`.
- **Authorization (M3, permanent)**: ALL RBAC lives in `backend/app/authz.py` (`authorize(action, clinic_id, patient_id)` + `PERMISSIONS`). Identity/role authority is the DB `User` in `backend/app/role_context.py`; `X-Role` is a demo-only consistency assertion (mismatch → 403, never escalation). Endpoints use `require_auth` (401) + `authorize` (same-clinic no-permission 403 / cross-clinic or not-own-patient 404). Absent, cross-clinic, and not-own-patient resources return the same generic 404 body; scope checks must run before artifact-type/action branching. `User.patient_id` maps a patient-role user to their own record.
- **Revision strategy (M3)**: full snapshots in `artifact_versions` (unique `(artifact_id, version)`); diffs are computed on read with `difflib` (`app/revisions.py`); revert copies the target snapshot into a NEW version and never mutates history. New note creates Artifact(v1) + ArtifactVersion(v1) + AuditLog in one transaction.
- **Concurrency (M3)**: editable artifacts require `expected_version`; stale write → 409 via atomic conditional UPDATE (`WHERE version=?`), plus a `conflict` AuditLog in its own transaction. Different sections (role-owned `staff_note`/`clinician_note`) never overwrite each other.
- **Audit (M3)**: `backend/app/audit.py` `add_audit(...)` — metadata only (no raw content). `Highlight.status_history` is still present but highlight-status changes also write AuditLog now (Phase 7 feedback reads AuditLog).
- **Collaboration (M3)**: comments may anchor to Event or Artifact; replies preserve the parent's anchor, mentions are same-clinic staff/clinician only, and the Event feed includes both anchor types. The frontend supports anchor selection, threaded replies, resolve/unresolve, and remounts the whole patient workspace on role change so provenance cannot leak across roles.
- **DB**: SQLite at `backend/nantingale.db` (gitignored); tests override via `NANTINGALE_DB_URL` env var (see `backend/tests/conftest.py`). Tests re-seed before every test (function-scoped autouse) for isolation.
- **Two time axes**: Timeline sorts by `Event.started_at` only; `created_at` is record-keeping.
- **Run/tests**: `cd backend && .venv/Scripts/python.exe -m pytest` (118 tests green as of M5).

M4 (AI pipeline + redaction + deterministic prioritization) is complete. Conventions added:

- **Provider protocol**: only `mock` (key-free deterministic) and `deepseek` (live adapter) are wired; chosen via `NANTINGALE_LLM_PROVIDER` (default `deepseek`). `deepseek` reads its key from env only — a missing key, provider error, or schema-invalid output falls back to `deterministic_fallback`. No other provider is wired (see `backend/docs/gate0_provider_status.md` for the dated Gate 0 smoke-check record).
- **Redaction**: `backend/app/redaction.py` (`redact_content` / `restore_placeholders`). Deterministic coverage for known names + IC/ID + phone; `placeholder_mapping` is in-memory only. `backend/app/ai_pipeline.py` redacts BEFORE any provider call.
- **LLM egress**: `backend/app/llm_client.py` `LLMClient` protocol is the ONLY provider exit; accepts `RedactedContent` only. No module may call an SDK/HTTP provider directly.
- **Span anchoring (permanent)**: provider quotes are over REDACTED text; pipeline restores placeholders locally, then `locate_span` against the RAW source; a failed restore/anchore drops the candidate (never fuzzy match).
- **Extraction**: `backend/app/extraction.py` strict Pydantic schema; `entity_key` is server-recomputed from `entity_type + normalized token` (never trusted from the LLM).
- **Deterministic fallback**: `backend/app/deterministic_pipeline.py` is fixture-independent (never imports seed); conservative extractive summary + keyword candidates; 0 highlights allowed.
- **Conflict**: `backend/app/conflicts.py` bounded medication/dose + task/status comparison vs clinician notes only; conflict => `review_status=needs_review` + `conflict_with_artifact_id`; never modifies clinician artifacts.
- **Scoring**: `unresolved_task=false` in M4; `recency` computed from injected `as_of`; `repeated_mentions` from same `entity_key` across ≥2 events (both sides recomputed); `clinician_confirmed` only set when a clinician accept/pin (score recomputed).
- **Ingestion**: `backend/app/api/sources.py` (source/session endpoints), idempotent via namespaced `Artifact.ingestion_key` + stable-derived IDs; raw source persisted BEFORE derived; patient session response hides internal summary/highlight ids.

M5 (longitudinal demo data) is complete. Conventions added:

- **Timeline (7 events)**: `2025-04-15` historical → `2026-02-06` historical → `2026-08-20` pre-consult → `08-21` nurse → `08-21` doctor → `08-24` follow-up → `08-26` clinician_review (Event 5, `evt_review_0826`). Sorted by `started_at` only.
- **Seed scoring is structural, not hand-filled**: `backend/seed/highlights.py` computes `recency` from frozen `SEED_AS_OF = 2026-08-26 12:00`, `unresolved_task=false` (no Task model), and `repeated_mentions` from the SAME exact `entity_key` across ≥2 distinct Events (both sides recomputed). Quotes anchor via `locate_span`; a failed match drops the candidate and excludes it from repeated counting.
- **Cross-event entities (demo)**: `symptom:headache frequency` spans `evt_hist_2025` / `evt_hist_2026` / `evt_pre_0820`; `task:blood test` spans `evt_doc_0821` / `evt_review_0826`.
- **Synthea decision**: NOT adopted. Demo data is a hand-written canonical fixture (fully satisfies "Synthetic Data Only"). See README demo-data note.

M6 (Patient View) is complete. Conventions added:

- **Endpoint**: `GET /api/patients/{patient_id}/patient-view` in `backend/app/api/patient_view.py`; read-only aggregate, deterministic read-time projection (NO LLM, NO second summary artifact, NO fallback to clinician/staff notes). Registered in `app/main.py`.
- **RBAC action**: `read_patient_view` in `PERMISSIONS`, granted to `patient` only. Endpoint uses unified `authorize` (scope-first 404 / same-scope non-patient 403 / anonymous 401).
- **Explicit field projection (anti-leak core)**: only `patient_instruction` artifacts whose `author_role=clinician`, `author_id` resolves to a same-clinic clinician `User`, and `content.instruction` is a non-empty string are projected; only `instruction` + `follow_up` (optional non-empty string) are copied. Response schemas in `app/schemas.py` (`PatientViewOut` / `PatientViewSummary` / `PatientViewInstruction` / `PatientViewUpcoming` / `PatientViewSession`) use `extra="forbid"`. No `highlight_ids`/`review_status`/`importance_score`/`entity_key`/`provenance_pointer`/span/comment/audit/version/author_id/generation metadata ever appear.
- **Ordering**: `current_summary` = latest by `Event.started_at` desc, then `Artifact.created_at` desc, then `artifact_id` desc. `instructions`/`upcoming` by `event_time` desc; `sessions` by `started_at` desc. All with stable id tie-break.
- **Sessions**: only this patient's `patient_ai_preconsult|patient_followup` Events that have a `raw_conversation` authored by this patient user (`author_id == ctx.user_id`). No persisted processing status is returned or fabricated.
- **Frontend**: `PatientViewPage` (`frontend/src/pages/PatientViewPage.tsx`) — patient-role route; `App.tsx` does role-level binary render (patient → PatientViewPage, others → PatientPage) with whole-tree remount via `key={roleKey}`. Patient view only calls `patient-view` (initial load) + existing session POST (then refresh); it never requests events/artifacts/glance/highlights/comments/audit/revisions.
- **Tests**: `tests/test_patient_view.py` (15 tests) locks exact key sets, sentinel-based leak scans, clinician-authorship validation, latest-summary selection, upcoming projection, own-session filtering, RBAC 401/403/404 matrix, and M3 whitelist regression. 133 tests green.

---

## 20. Current Execution Phase C — Clinician Consult Workflow（2026-08-26）

M1–M6 remain complete. Before Phase 6 Performance + Core Hardening, execute two task cards in order:

1. `Task_Card/C1_Task_Card.md` — Encounter + Manual Doctor Consult Backend;
2. `Task_Card/C2_Task_Card.md` — Clinician Workspace + Consult Review UX.

Phase C is a productization pass over existing contracts, not authorization to add Voice, Task, Doctor AI Assistant, model training, external dataset ingestion, production auth, Patient Experience redesign, or a dedicated Nurse Workspace.

Permanent Phase C decisions:

- **New Consult semantics**: `New Consult` is an operation that creates a new real-world `doctor_consult` Event on the main Timeline. It must never continue writing to the hard-coded `evt_doc_0821`.
- **Clinic Visit grouping**: add optional `Event.encounter_id` (string; no Encounter table in C1). Events with the same non-empty encounter id may be presented as one `Clinic Visit` in the UI. Nurse and Doctor Consults remain separate Events with separate authorship, permissions and Artifacts. Never group by date alone.
- **Clinician-first scope**: C implements Doctor Consult input and the clinician workspace. Existing staff RBAC, Staff Note, Comment and Nurse AI Summary paths must remain green, but Nurse input/UI is deferred.
- **Input boundary**: only manual speaker-labelled text transcripts are added. Canonical segments use continuous indexes and `speaker ∈ doctor|patient`; unknown speakers, empty text and invented timestamps fail closed. No audio/ASR/OCR/EHR import.
- **Synthetic data**: the C demo transcript is hand-written and must remain consistent with `backend/seed/fixture.py` FACTS. Public datasets such as PriMock57 may inform structure only; do not import them into the canonical record unless separately authorized and attributed.
- **Authority**: transcript is immutable raw source (`artifact_type=transcript`, `author_role=system`); AI Doctor Summary remains an independent system Artifact; formal assessment/plan is a clinician-owned note. Corrections use Comment + Clinician Note, never raw overwrite.
- **Backend orchestration**: C1 adds clinician-only `POST /api/patients/{patient_id}/doctor-consults`, creates Event + raw Transcript first, then reuses the existing `app/api/sources.py` / `LLMClient` / redaction / fallback / provenance path. Do not create a second LLM exit.
- **Frontend target**: C2 implements the confirmed three-column desktop clinician shell: clinician identity + `Clinic Patients`; center `Glance | Timeline | Notes`; right contextual Source/Comments/Versions/Audit. Do not display fake Tasks, `My Patients`, AI Assistant, appointment or assignment states.
- **Timeline hierarchy**: main Timeline = Event / explicit Clinic Visit group; Event Detail = Artifact/Comment/Revision lifecycle ordered by record time; Artifact Reader = Transcript/AI Summary/Clinician Note; provenance resolves to exact Span. Comments and audit activity never become new medical Events.
- **Comment boundary**: retain existing Event/Artifact anchors, reply, same-clinic mentions, resolve/unresolve and audit. Comment is collaboration, not clinical authority or a Task substitute. Span-level comments are out of C.
- **State isolation**: patientId remains a workspace remount/security boundary; switching patient/role must clear source, Event detail, comments, draft and pending responses. Patient continues to render the independent M6 Patient View and must not request clinical endpoints.
- **Gate order**: C1 Exit Gate → C2 Exit Gate → Phase 6 Performance. Do not begin P95 measurement/Bonus while the clinician input/review workflow is incomplete.

---

## 21. C1 Implementation Status（2026-08-26）

C1 (Encounter + Manual Doctor Consult Backend) is complete. C2 is now the active task card. Conventions added:

- **Encounter grouping**: `Event.encounter_id` is optional and returned by `EventOut`; canonical `evt_nurse_0821` / `evt_doc_0821` share `enc_visit_20260821`. Null/different identities never group, including Events on the same date. No Encounter table exists.
- **Strict manual transcript**: `DoctorTranscriptSegment` / `DoctorTranscriptContent` / `DoctorConsultCreate` in `backend/app/schemas.py`; 0-based continuous indexes, `speaker ∈ doctor|patient`, trimmed non-empty text, no timestamps/unknown keys. `backend/seed/fixture.py::C1_DEMO_DOCTOR_TRANSCRIPT` is hand-written and FACTS-consistent.
- **New Consult endpoint**: clinician-only `POST /api/patients/{patient_id}/doctor-consults` in `backend/app/api/sources.py`. Stable Event/encounter/source IDs derive from clinic + patient + consult identity; namespaced idempotency prevents duplicate Events/Artifacts and a reused consult with a different ingestion key fails 409.
- **Raw-first + authority**: Event + immutable system-authored Transcript + metadata-only audit commit before `_ingest_common`; derived processing reuses the existing redaction → `LLMClient` → extraction/conflict/scoring/provenance pipeline. AI Doctor Summary and Highlights are independent rows; Transcript remains forbidden through edit/revert APIs.
- **C2 API handoff**: enhanced `GET /api/me`, clinic-scoped `GET /api/patients`, Event `encounter_id`, and frontend `CurrentIdentity` / `DoctorConsultResult` / `createDoctorConsult` types are frozen.
- **Tests**: `backend/tests/test_doctor_consult_ingestion.py` plus encounter/fixture regressions; **156 pytest passed** and frontend production build passed at C1 Exit Gate.

---

## 22. C2 Implementation Status（2026-08-26）

C2 (Clinician Workspace + Consult Review UX) is complete. Phase 6 Performance + Core Hardening is now the active phase. Conventions added:

- **Role-level shell boundary**: `frontend/src/App.tsx` renders patient → independent `PatientViewPage`, clinician → `ClinicianWorkspacePage`, staff/admin → retained minimal `PatientPage`. The demo role toolbar is structurally outside product shells. Role change remounts the complete product root.
- **Clinician shell**: `ClinicianWorkspacePage.tsx` owns DB-authoritative identity, factual Clinic dashboard, `Clinic Patients` directory/search, patient switching and URL/history state. It displays no Tasks, My Patients, assignment, appointment, Mentions inbox or AI Assistant fiction.
- **Patient isolation**: patient workspace is keyed by `roleKey:patientId`; switching patient clears provenance, Event/Artifact context, comments, New Consult draft and pending UI responses. Clinical loads use AbortController/stale-response guards. Patient browser QA confirms no Timeline/Glance/Artifact/Comment/Audit requests.
- **Main views**: center navigation is exactly `Glance | Timeline | Notes`. `ClinicalTimeline` groups only identical non-empty `encounter_id`; same-date Events are never inferred as one visit. `ClinicalNotesView` is a client projection whose cards navigate back to canonical Event/Artifact anchors.
- **Event hierarchy**: `ClinicalEventDetail` shows real-world Event time separately from Artifact/Comment/Audit record-time lifecycle. Artifact Reader handles Transcript, AI Summary and human notes; immutable Transcript has no edit/revert. Formal correction is Comment + clinician-owned note.
- **Context panel**: only real Source/Comments/Versions/Audit capabilities appear. Glance provenance remains in the right panel with exact `<mark>` span; unresolved source explicitly fails closed. Existing comment anchor/reply/mention/resolve, revision/diff/revert and metadata audit APIs are reused.
- **New Consult**: `NewDoctorConsult.tsx` has a strict manual `DOCTOR:` / `PATIENT:` parser, 0-based continuous preview, no inferred timestamps/speakers, stable retry IDs, retained draft on failure and explicit raw/derived/fallback states. Datetime-local is sent as clinic-local naive time to preserve the Event time axis. Success navigates to the new Event and refreshes Timeline/Glance.
- **Responsive target**: full three-column shell at ≥1280px; reduced layouts fail safely below that. C2 browser QA passed at 1280×800 and 1440×900 without critical horizontal overflow.
- **Exit Gate**: New Consult → AI fallback summary/highlights → new Transcript exact span → Comment/@mention/resolve → Clinician Note edit/version/revert → Audit was exercised end-to-end. Backend **156 passed**, frontend TypeScript/Vite production build passed. Performance/Bonus was not started during C2.

---

## 23. M7 Implementation Status（2026-08-26）

M7 (Performance + Core Hardening) is complete. At M7 close the next planned work was Milestone 6 deliverables; owner review has since replaced that sequence with Phase D in §24. M7 conventions added:

- **H1 Glance ordering determinism**: the read sort key is `(status != pinned, -importance_score, created_at, highlight_id)` in `backend/app/api/highlights.py`; `tests/test_glance_ordering.py` locks the final tiebreak and pinned priority.
- **H2 write-after-read**: clinician accept/pin still recomputes `clinician_confirmed` + score at write time and the next Glance read reflects it (locked in `test_glance_ordering.py`).
- **H3 highlight status concurrency**: `update_status` now uses an atomic conditional `UPDATE ... WHERE status = old_status`; a stale writer matches 0 rows and returns a deterministic 409 `conflict` (with a metadata-only conflict audit), never a silent last-write-wins merge. Locked by a concurrent-accept test asserting exactly one transition wins and history has a single entry.
- **H4 read-path LLM-free guard**: `tests/test_read_path_no_llm.py` imports glance / patient-view / events / patients each in a clean interpreter subprocess and asserts their transitive import delta contains none of `ai_pipeline`, `llm_client`, `extraction`, `redaction`, `deterministic_pipeline`, `conflicts`.
- **Measurement**: `backend/scripts/measure_glance.py` samples glance / events / patient-view (100 samples, 10 warm-up) on a throwaway seeded SQLite, reporting Layer A (TestClient in-process) and Layer B (uvicorn HTTP) and writes `backend/docs/perf_baseline.md`. Glance Layer A P95 ≈ 3.8 ms on this machine; no index/cache work was needed.
- **Honesty clause**: the baseline explicitly states single-user local SQLite numbers only prove the warm path has no synchronous LLM/full-history scan, not production capacity.
- **Regression**: backend **161 passed**, frontend TypeScript/Vite production build passed.

---

## 24. Current Execution Phase D - Product Completion（2026-08-26）

Owner review supersedes the prior "M7 -> immediate deliverables" sequence. The current system is classified as a strong technical vertical slice, not yet a usable product Demo. Phase D is now active; architecture-diagram, Technical Brief, demo recording and Bonus work remain paused until D1-D5 complete.

Canonical plan and task order:

1. `docs/phase_d_product_completion_plan.md` - Phase D master contract;
2. `Task_Card/D1_Identity_Access_Task_Card.md` - invite/register/login/session/logout;
3. `Task_Card/D2_Care_Tasks_Patient_Experience_Task_Card.md` - first-class Task lifecycle + patient product;
4. `Task_Card/D3_Transcript_Reliability_Task_Card.md` - raw import preview + frozen transcript evaluation;
5. `Task_Card/D4_Clinician_Copilot_Task_Card.md` - patient-scoped, evidence-bound, draft-only Copilot;
6. `Task_Card/D5_Security_Integration_Task_Card.md` - TLS/at-rest evidence + cross-role E2E/usability gate.

Permanent Phase D decisions:

- **Identity**: clinical roles and patients register through scoped, single-use invites. Public self-selection of clinician/admin role and patient record search/claim are forbidden. Server-side session + DB User replace demo headers as product identity; demo headers may exist only behind an explicit development flag.
- **Task authority**: Task is a first-class entity. Patient may report an assigned patient-visible Task as `reported_done`; only staff/clinician may confirm `completed`. Task transitions are audited, scope-checked, provenance-linked and use deterministic optimistic concurrency.
- **Patient product**: patient shell is `Today | Care Plan | Check-in | Visit Summaries`, implemented through explicit allowlisted projections. It never becomes a filtered copy of the clinical workspace.
- **Transcript boundary**: raw text is normalized without persistence/LLM, shown in a review preview, and blocked on unknown/ambiguous speakers. Only user-confirmed continuous `doctor|patient` canonical segments create an immutable Transcript and enter the existing redaction/LLM/provenance path. No audio/ASR/OCR/EHR import.
- **Copilot authority**: Copilot reads only the authorized current patient, returns server-validated evidence for every clinical fact, marks inference/unknown, and creates preview drafts only. It never directly writes a note, completes a Task, changes author, or treats provider output as permission/provenance authority.
- **Security evidence**: TLS, database/volume/backup encryption at rest, secure cookies, secrets and restore behavior must be demonstrated on the current deployment. Documentation-only claims do not pass. SQLite remains acceptable for unit tests; deployment database choice is a D5 Decision Gate.
- **Gate order**: D1 -> D2 -> D3 -> D4 -> D5 by default. D2 UI design and D3 corpus preparation may overlap, but D4 cannot start before D2/D3 Exit Gates. No Task Card may relax RBAC, provenance, clinician authority, patient anti-leak or raw-source preservation.
- **Out of scope**: real PHI, production medical use, Voice/ASR, model training, self-learning ranking, data decay, appointment/billing/prescription systems, multi-clinic membership and a dedicated Nurse Workspace.

---

## 24. D1 Implementation Status（2026-08-27 审查修复后重验）

D1 (Identity, Invite, Login and Session) is complete. D2 is the next task card. Conventions added:

- **New tables**: `invites` / `user_credentials` / `auth_sessions` in `backend/app/models.py` (model classes `Invite` / `UserCredential` / `AuthSession`). `AuditLog.actor_id/actor_role/clinic_id/patient_id` became nullable for auth events (e.g. unknown-email `login_failure`); clinical events always populate them.
- **Passwords**: Argon2id via `argon2-cffi` (MIT, bundled reference impl CC0/Apache-2.0; ATTRIBUTION updated) in `backend/app/auth_security.py` (`hash_password`/`verify_password`). Plaintext passwords never touch DB, logs or AuditLog. Unknown/disabled-account login still verifies one process-local dummy Argon2id hash, preventing the active-email timing branch; auth validation 422 responses are fixed and never serialize rejected passwords/tokens or internal paths.
- **Tokens**: invite and session tokens are 256-bit `secrets.token_urlsafe(32)`; only SHA-256 hashes are persisted (`hash_token`). The raw invite link is returned exactly once from `POST /api/auth/invites`.
- **Auth API** (`backend/app/api/auth.py`): `POST /api/auth/invites` (admin, clinic-scoped; patient invites MUST bind a same-clinic patient; clinical invites MUST NOT carry patient_id), `GET /api/auth/invites` (admin list, no tokens), `GET /api/auth/invites/{token}/preview` (masked email/role/clinic/patient; unknown token → uniform 404; used/expired distinct only for a held token), `POST /api/auth/register` (conditional compare-and-set consumes the invite exactly once under concurrency; consumption + User + UserCredential remain one transaction; invite role/clinic/patient binding can never be overridden; patient register links the EXISTING Patient record and never creates a second one; no auto-login), `POST /api/auth/login` (uniform body and one Argon2 verification for unknown email / wrong password / disabled; issues HttpOnly + SameSite=Lax cookie, `Secure` gated by `NANTINGALE_SECURE_COOKIES=true`), `POST /api/auth/logout` (atomic conditional UPDATE revoke + `logout`/`session_revoked` audits in one transaction + cookie clear), `GET /api/auth/session` (identity restore for refresh).
- **RoleContext rework** (`backend/app/role_context.py`, permanent): resolution order per request = (1) valid server-side session cookie → DB User (role/clinic/patient always from DB; disabled credential / expired / revoked → unauthenticated); (2) legacy `X-User-Id/X-Role` ONLY when `NANTINGALE_DEMO_AUTH=true` (default off; X-Role mismatch still hard-403); (3) unauthenticated. A session cookie wins over headers; stale headers can never escalate. `last_seen_at` refreshes throttled (60s).
- **RBAC additions**: `create_invite`/`list_invites` are admin-only in `PERMISSIONS` (`backend/app/authz.py`). Clinic comes from the inviter's session — never from the request.
- **Seed**: all 6 fixture users get Argon2id credentials sharing demo password `nightingale-demo` (hash computed once per process); demo emails in `fixture.DEMO_EMAILS` (`doctor@demo.clinic` clinician, `staff@…`, `alice@…` patient, `admin@…`, plus isolation users). `seed.py` clears D1 tables FK-safely.
- **Tests**: `tests/conftest.py` sets `NANTINGALE_DEMO_AUTH=true` for the existing header fixtures (zero regression, 161 legacy tests green). Auth files: `tests/test_auth_invites.py` (25), `tests/test_auth_sessions.py` (22), `tests/test_auth_routing_scope.py` (13), plus seed credential integrity. **222 backend tests green**; frontend TypeScript/Vite production build green. Review regressions cover secret-free 422, one password verification on unknown/disabled login, real concurrent invite registration (201 + 409), `session_revoked`, and revoke/audit rollback on injected audit failure.
- **Frontend**: product mode (`VITE_DEMO_AUTH` unset, default) boots via `GET /api/auth/session`, renders `LoginPage`/`RegisterPage` (valid/used/expired/invalid states) when unauthenticated, and routes by session role: patient → `PatientViewPage` (patientId from identity), clinician → `ClinicianWorkspacePage`, staff → minimal `PatientPage`, admin → `PatientPage` + `AdminInvitesPage` (`/admin/invites`). Any 401 clears identity and returns to Login; logout unmounts the whole product root (drafts/source/comments cleared). No role is ever read from localStorage. Demo toolbar + header simulation require `VITE_DEMO_AUTH=true` AND backend `NANTINGALE_DEMO_AUTH=true`.
- **Audit actions added**: `invite_created`, `register`, `login_success`, `login_failure`, `logout`, `session_revoked` (metadata only; failed-login emails are never logged). Logout state transition and both logout/revoke audits commit atomically.
- **README**: Demo auth flow, demo accounts, env vars, and the demo-vs-production identity boundary are documented (§7 + §15).
- **Live E2E verified**: invite → register → login → session → logout, patient binding (no second Patient row), cross-clinic uniform 404, seeded four-role logins all exercised over real HTTP (uvicorn + curl).

---

## 25. D2 Implementation Status（2026-08-27 审查修复后重验）

D2 (Care Task Lifecycle + Patient Experience) is complete. At D2 close, D3/D4/D5 remained untouched; D3 has since completed under the separate authorization recorded in §26.

- **First-class Task**: `Task` in `backend/app/models.py` requires patient/clinic/origin Event and stores optional paired Artifact/Span provenance, assignment, patient visibility, due time and terminal actor/timestamps. There is no parallel Task history table; metadata-only `AuditLog.details` is the single status-history authority.
- **State machine / concurrency**: `backend/app/tasks.py` freezes `open -> in_progress|reported_done|cancelled`, `in_progress -> reported_done|cancelled`, `reported_done -> completed|cancelled`; `completed|cancelled` have no outgoing transitions. `POST /api/tasks/{task_id}/transition` uses atomic `UPDATE ... WHERE status=expected_status`; stale writes return deterministic 409.
- **Authority / scope**: D2 actions remain centralized in `backend/app/authz.py`. API handlers in `backend/app/api/tasks.py` load the resource and enforce clinic/patient scope before parsing assignment, status or provenance content. patient may only Start/Report done on their own `patient_visible`, assigned-patient Task; staff/clinician confirm completion or cancel within clinic; cross-scope and hidden/unassigned patient Tasks use the uniform 404.
- **Provenance**: every Task has an origin Event. Artifact and Span are supplied together and validated by strict, exact, non-empty, in-bounds resolution (`resolve_exact_span`); invalid provenance fails closed. `GET /api/tasks/{task_id}/provenance` resolves Event → Artifact → exact quote for clinical roles.
- **Glance write path**: the Task↔Glance mapping is ALWAYS explicit and database-enforced (`Highlight.task_id` FK + unique constraint). `link_task_highlight` uses conditional UPDATE/CAS to adopt an exact patient/event/source_artifact/source_span match only when the candidate remains unowned and is not rejected; a race loser or non-match creates a dedicated row. Event-only Tasks never flag unrelated Highlights. `recompute_task_highlights` updates only the matching `task_id`; terminal statuses clear unresolved weight and dedicated rows receive accurate completed/cancelled wording. Autoflush is disabled, so `create_task` explicitly flushes after linking. Glance reads remain precomputed and LLM-free.
- **Provenance hardening**: `resolve_exact_span` fails closed on ANY abnormal structure (content not a dict, segments/messages not lists, non-dict members, wrong member types, malformed span keys/offsets/floats/bools) and returns None — callers translate it into deterministic 422 (create) / 404 (read), never a 500. Exact provenance is saved ONLY when the user explicitly picks a quote AND confirms it in `TaskCreateForm`; otherwise the Task is Event-level (`source_artifact_id/source_span` null). Glance's Open Task navigates to the SPECIFIC task card (scroll + focus + provenance), never a generic list.
- **Patient API allowlist**: patient Task rows expose exactly `task_id`, `title`, `status`, `due_at`, `updated_at`, `reported_done_at`, `completed_at`, `patient_visible`. They never expose description, assignee/creator metadata, Artifact/Span, audit, importance or risk reasoning. The aggregate is exactly `patient_id`, `display_name`, `today`, `care_plan`, `check_in`, `visit_summaries`; it only consumes explicit Task/Instruction/session rows and never infers actions from clinician notes.
- **Frontend**: `PatientViewPage` is now `Today | Care Plan | Check-in | Visit Summaries`, with loading/empty/error, Start/Report done, waiting-for-clinic-verification, Check-in send/retry and session/role reset. `ClinicalTasksView` gives clinician/staff the shared clinic-shell Task list/create/transition/provenance flow; Event Detail can create from the selected Artifact exact span. No Nurse Workspace was added.
- **Canonical story**: `task_blood_test` is currently open and drives the Glance unresolved weight. `task_symptom_diary` is completed with seeded `open -> reported_done -> completed` AuditLog evidence.
- **Verification**: five D2 test files plus review regressions now cover explicit mapping isolation, event-only Glance entry, rejected-candidate exclusion, FK/unique schema enforcement, concurrent CAS adoption, terminal wording, adoption-not-duplication, malformed-span 422-not-500 and seed mapping lock; backend **258 passed**, frontend TypeScript/Vite production build passed. Local browser QA verified patient report done → waiting clinic verification → clinician verify complete → Glance refresh, staff shared shell, and zero console warnings/errors.
- **Non-goals preserved**: no appointment, lab-order system, billing, recurrence, notification provider, patient direct chat, D3 transcript normalization/evals, D4 Copilot or D5 security integration was implemented.

---

## 26. D3 Implementation Status（2026-08-27）

D3 (Transcript Import, Normalization and Reliability Evaluation) is complete. D4 is the next task card; D3 completion does not authorize Copilot or D5 work.

- **Pure normalize boundary**: `backend/app/transcript_normalizer.py` is deterministic and frozen (`SHA-256 1ac0e01e92401b1728e7b938541e71f8d95e81cca137376004953eb2cd371476`). `POST /api/transcripts/normalize` is clinician-only and performs no patient DB read, persistence, AuditLog write, LLM/provider call or timestamp invention.
- **Outcome contract**: preview returns `ACCEPT|NEEDS_REVIEW|REJECT` plus exact character ranges, nullable speaker candidate, deterministic confidence marker and issues. Frozen mapping supports DOCTOR/PATIENT case variants and Dr/Pt; unknown/third-party/unlabelled/empty input fails closed. UNKNOWN never becomes doctor, patient or another default.
- **Limits**: raw text is capped at 4096 UTF-8 bytes (413); canonical preview is capped at 500 segments and 4000 characters per segment (422). There is no silent truncation.
- **Confirm authority**: only reviewed, continuous `doctor|patient` canonical segments cross the existing C1 Doctor Consult endpoint. Event + immutable system-authored Transcript commit first; M4 redaction/provider-or-fallback/provenance remains the only derived path. Preview metadata and raw labels do not persist; derived failure preserves raw.
- **Frontend**: `NewDoctorConsult.tsx` is a real `Paste → Review → Confirm` workflow with raw/preview comparison, visible unknown blocking, speaker/text edits, split/merge, explicit reject state, stable retry identity and patient-switch reset. No fake ASR confidence/timestamp is shown.
- **Frozen evaluation**: 40 synthetic cases (development 26 / frozen_holdout 14), UTF-8/LF bytes, per-file SHA-256, manifest hash and composite holdout digest. Holdout normalize outcome 14/14, speaker 12/12, ambiguous blocking 8/8; silent invention/truncation/redaction miss/fallback unanchored candidate all zero. No rule was changed after first holdout evaluation.
- **Layered honesty**: the deepseek provider requires an env key and is not exercised by the frozen runner; the runner reports provider `NOT_RUN`. Deterministic fallback is separate: development exact entity precision 0.888889/recall 0.571429 and task precision 1.0/recall 0.5; holdout lacks entity gold and reports null. Standalone corpus conflict accuracy is `NOT_EVALUATED` because clinician-note DB context is absent.
- **Verification**: backend **296 passed**; corpus validation and deterministic runtime runner exit 0; frontend production build passed. Review re-verification added canonical-boundary regressions (`tests/test_transcript_preview_contract.py`) plus a non-BMP code-point contract (`tests/test_transcript_non_bmp.py`, which runs the Node `frontend/tests/transcriptRange.test.ts`) locking that preview source ranges can never enter the canonical Transcript and that emoji/non-BMP text is split with code-point accuracy, plus `CORPUS_VALIDATION_PASS` and the unified mock/deepseek provider wording. Browser QA covered ACCEPT/NEEDS_REVIEW/REJECT, resolve/split/merge, confirm → fallback → exact source, patient-switch isolation, and zero console warnings/errors.
- **Permanent stop rules**: never default unknown speakers, never call an LLM or persist at normalize time, never tune rules case-by-case against frozen holdout, never merge provider/fallback scores, and never persist an unanchored candidate.
