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

## 19. M1–M2 Implementation Status (2026-08-25)

M1 (skeleton + canonical fixture) and M2 (Glance → Provenance vertical slice) are complete. Concrete conventions that later phases MUST respect:

- **Schema location**: `backend/app/models.py`. Current tables: `clinics` / `users` / `patients` / `events` / `artifacts` / `highlights`. Comment / Version / Task / AuditLog are Phase 3 — do NOT add them early.
- **Span is NOT a table**: expressed as a JSON pointer `{"kind", "index", "offset"}` where `kind ∈ segment|message|paragraph|timestamp_range|section`. Artifact spans live in `Artifact.provenance_pointer`; Highlight spans live in `Highlight.source_span`.
- **Canonical fixture = single source of truth**: `backend/seed/fixture.py` (IDs + 6 FACTS + `HIGHLIGHT_CANDIDATES`). Any new narrative must stay consistent with `FACTS` and `tests/test_seed_integrity.py`.
- **author_role semantics**: AI summaries = `system` (author_id null); raw_conversation = `patient`; transcript = `system`; clinician_note/patient_instruction = `clinician`.
- **Span anchoring rule (M2, permanent)**: candidates carry a verbatim `quote`; spans are located by deterministic string matching in `app/highlights.py` (`locate_span` / `extract_text`). A failed match DROPS the candidate — never fabricate a span. Phase 4 LLM must follow this same contract.
- **Importance scoring**: transparent constant weights in `app/highlights.py` (`WEIGHTS` + `compute_score`), precomputed at write time; Glance read path does zero computation. `GLANCE_LIMIT = 5`.
- **Highlight status machine**: `suggested → accepted|rejected|pinned` etc. (see `status_transitions()`); changes append to `Highlight.status_history` (JSON, temporary — folds into AuditLog in Phase 3).
- **Role context**: `backend/app/role_context.py` parses `X-User-Id`/`X-Role` headers → `request.state.role_context`. Parse-only; enforcement lands in Phase 3. `GET /api/me` echoes it for tests.
- **DB**: SQLite at `backend/nantingale.db` (gitignored); tests override via `NANTINGALE_DB_URL` env var (see `backend/tests/conftest.py`).
- **Two time axes**: Timeline sorts by `Event.started_at` only; `created_at` is record-keeping.
- **Run/tests**: `cd backend && .venv/Scripts/python.exe -m pytest` (27 tests green as of M2).
