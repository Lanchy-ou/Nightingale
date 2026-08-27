# Patient Multiturn Check-in — Vertical Task Card

> Status: **COMPLETE — INDEPENDENT REVIEW AND EXIT GATES VERIFIED (2026-08-28)**
>
> Frozen baseline: `7b6da1d63245f45c60143e3a1bd6ac6b406255e4`
>
> Branch: `codex/patient-multiturn-checkin`

## 1. Outcome

Implement one bounded, persistent Patient Check-in journey inside the existing longitudinal record:

```text
Patient
  -> Patient Check-in Event
  -> raw_conversation (stable patient and AI messages)
  -> ai_patient_session_summary (only after patient confirmation)
  -> candidate Highlight
  -> exact patient-message Span
```

The assistant leads a non-emergency information-collection flow. It is not an open medical chatbot and cannot diagnose, prescribe, alter doses, interpret tests as normal, change the care plan, author clinical notes/instructions, complete Tasks, or claim that the clinic was notified.

## 2. Frozen product journey

1. Patient starts or resumes the single active Check-in for their own record.
2. The first screen states the non-emergency and non-diagnostic boundary.
3. Nightingale AI asks one question at a time. Allowed question types are `severity`, `change`, `associated_symptoms`, `task_progress`, and `patient_concern`.
4. Patient may answer freely, correct, skip, proactively add information, choose “nothing else”, finish, or abandon.
5. Every patient message receives a stable client-generated `message_id`. The server commits it before safety rules, redaction, or provider work.
6. Duplicate requests with the same `message_id` return the original patient message and original AI result. A different payload under the same id is a conflict.
7. Deterministic safety rules, not the provider, stop ordinary questioning and persist `safety_escalated` with bounded help text.
8. At most four AI clarification questions are stored. Provider output cannot exceed the server state machine or reopen a terminal session.
9. `awaiting_confirmation` shows a patient-readable, source-preserving recap. The patient may return to supplement/correct or confirm; they cannot edit AI prose into a new fact.
10. Confirmation creates the formal AI Summary and candidate Highlights atomically. Each candidate must resolve by patient `message_id` plus verbatim quote to an exact non-empty patient-message Span; otherwise it is dropped.
11. Clinician/Staff Timeline and Event Detail show the submitted or safety-escalated Event, patient words, AI questions, AI Summary, safety state, and provenance separately.
12. A reported Task update remains narrative evidence only. It never changes Task state; the existing `reported_done -> clinic confirmation` contract remains authoritative.

## 3. Minimal state and visibility contract

Session states:

```text
active
awaiting_confirmation
submitted
safety_escalated
abandoned
```

- `active` and `awaiting_confirmation`: patient-owned draft, refreshable, hidden from clinical Timeline.
- `submitted`: immutable completed Check-in visible to same-clinic clinical readers.
- `safety_escalated`: ordinary questioning stops immediately; visible to same-clinic clinical readers with an explicit disclaimer that no notification was sent.
- `abandoned`: retained for data integrity/audit, not shown as a completed Timeline event.
- Only one `active|awaiting_confirmation` session may exist per patient user.

## 4. Authority and data rules

- DB session identity and `authorize()` remain the only role/scope authority.
- Patient may manage/read only their own Check-in. Same-clinic clinician/staff/admin may read visible Check-in Events through existing read paths; admin receives no new authoring permission.
- Patient messages, AI messages, and the AI Summary are distinct persisted records. AI messages are never patient facts or Highlight sources.
- Provider input is a bounded, redacted conversation context. `LLMClient` remains the only LLM egress and supports only `mock` and `deepseek`; all failures/schema violations use deterministic fallback.
- Turn output strict schema: `acknowledgement`, `next_question`, bounded `question_type`, bounded `conversation_action`, and `referenced_patient_message_ids`.
- Summary candidate strict schema includes patient `message_id` and verbatim `quote`; the server re-resolves both after placeholder restoration.
- Audit, logs, errors, and generation metadata contain identifiers/counts/status only, never patient message text.
- Existing E4 Voice remains default-off and independently lifecycle-gated. This card does not extend ASR, audio, speaker, or Voice-to-multiturn behavior.

## 5. Deterministic safety boundary

Use a small transparent rule set for explicit self-harm/suicide language and clear emergency symptom phrases such as severe breathing difficulty, stroke-like deficit, or uncontrolled severe bleeding. Matching is case-insensitive and phrase-based. The rule engine:

- runs only after the original patient message commit;
- records reason codes, never raw text, in session/audit metadata;
- stops ordinary questions without consulting the LLM;
- displays emergency-service / trusted-person guidance without diagnosing or claiming formal triage;
- never claims the clinic was notified.

## 6. File allowlist

Implementation may touch only:

```text
Task_Card/Patient_Multiturn_Checkin_Task_Card.md
backend/app/models.py
backend/app/db.py
backend/app/schemas.py
backend/app/authz.py
backend/app/highlights.py
backend/app/tasks.py
backend/app/llm_client.py
backend/app/checkins.py
backend/app/checkin_visibility.py
backend/app/api/checkins.py
backend/app/api/audit.py
backend/app/api/comments.py
backend/app/api/notes.py
backend/app/api/tasks.py
backend/app/api/patients.py
backend/app/api/events.py
backend/app/api/sources.py
backend/app/api/patient_view.py
backend/app/main.py
backend/app/copilot.py
backend/scripts/migrate_patient_checkin_schema.py
backend/scripts/smoke_patient_checkin_live.py
backend/seed/seed.py
backend/tests/test_patient_checkin_*.py
backend/tests/integration/test_patient_checkin_journey.py
backend/tests/security/test_patient_checkin_security.py
backend/tests/test_phase_e_schema_migration.py
backend/tests/test_patient_task_projection.py
frontend/src/patientCheckInMachine.js
frontend/src/patientCheckInMachine.d.ts
frontend/src/components/PatientCheckIn.tsx
frontend/src/components/ClinicalEventDetail.tsx
frontend/src/components/ArtifactContent.tsx
frontend/src/clinical.ts
frontend/src/pages/PatientViewPage.tsx
frontend/src/api.ts
frontend/src/types.ts
frontend/src/index.css
frontend/tests/patientCheckIn.test.mjs
README.md
AGENTS.md
```

Any required file outside this list is a stop-and-review condition before editing.

## 7. Tests and evidence

Backend tests must cover:

- start/resume/refresh/finish/return-to-correct/submit/abandon lifecycle;
- one-active-session invariant and stale/terminal transitions;
- raw-first persistence under provider failure;
- stable message idempotency, lost-response replay, and payload conflict;
- provider schema/bounds/redaction and deterministic fallback;
- free supplement/correction/skip/no-more/Task-progress/medical-advice-request behavior;
- no AI-message or draft-summary fact/Highlight source;
- exact patient `message_id` Span resolution for Summary and every Highlight;
- deterministic safety escalation without LLM;
- patient ownership, same/cross-clinic scope, clinical read visibility, admin non-authoring;
- no Clinician Note, Patient Instruction, Task status, or doctor-plan mutation;
- legacy Patient View/RBAC/provenance/session ingestion and E1–E4 regression.

Frontend tests/build must cover:

- state machine, saving/AI-working/failure/retry/confirmation/safety states;
- retry retains the same message id;
- active/history restoration;
- AbortController and sensitive-state cleanup on patient/role/session boundary and unmount;
- separate Patient / Nightingale AI presentation and clinician artifact separation;
- production TypeScript/Vite build.

Final commands/evidence:

```text
backend full pytest
D3 corpus + runtime evaluators
D4 frozen eval
E1-E4 targeted/integration/security tests
frontend Node tests
frontend production build
git diff --check
pip check
npm ls --depth=0
secret scan
```

Provider evidence must separately report `mock`, `live`, `deterministic_fallback`, and `NOT_RUN`. A missing DeepSeek key is not a failed gate when the deterministic journey passes; it must be reported as `live: NOT_RUN`.

## 8. Exit Gates

1. Patient can start, continue, refresh-resume, finish, abandon, correct/supplement, and confirm one persistent multi-turn Check-in.
2. AI leads with one bounded question at a time, naturally acknowledges new information, and safely refuses medical advice.
3. Every patient message is committed once before downstream work; retry never duplicates the message or an existing AI result.
4. Provider/network/schema failure preserves the original and deterministic fallback completes the journey.
5. Draft/AI messages create no formal patient fact, Summary, Highlight, Task transition, note, instruction, or plan change.
6. Submitted Summary and every Highlight resolve to an exact Span inside a specific patient message id.
7. High-risk rules stop ordinary dialogue without LLM authority and show persistent bounded help text.
8. Patient ownership and uniform cross-patient/cross-clinic denial pass; clinical readers see only visible submitted/safety Events.
9. Frontend aborts requests and clears drafts/replies/sensitive state on patient, role, auth-session, logout, and unmount boundaries.
10. Patient and clinical journeys are complete in the existing UI; Event Detail separates patient words, AI questions, Summary, safety, and sources.
11. Full backend, frontend build, D3/D4, E1–E4, historical Patient View/RBAC/provenance, dependency, secret, and diff checks are green.
12. Final worktree contains only allowlisted feature changes; no merge, rebase, push, E5, or unrelated restyling occurred.

## 9. Stop conditions

Stop and report before continuing if implementation would require:

- a second provider/LLM exit;
- fuzzy provenance or AI-message factual sourcing;
- frontend-only authorization/state authority;
- automatic diagnosis/treatment/Task completion/clinical authoring;
- modifying E4 Voice/ASR contracts to make Check-in pass;
- merge, rebase, push, E5, external dataset ingestion, or out-of-allowlist redesign;
- deleting files/directories in bulk.

## 10. Independent review evidence (2026-08-28)

- Independent review first reproduced and then fixed seven blocking classes: explicit-negation safety false positives; repeated question types after free supplementation; stale Provider references that ignored the newest patient message; unsafe wording for diagnosis/stop/double-dose/test-result requests; concurrent start/save/process races; non-idempotent repeated submit; hidden-draft existence leakage through manage/source-ingest paths. A Copilot evidence-row deduplication indentation regression and late-correction summary truncation were also fixed.
- Backend: **509 passed, 2 skipped** in 64.44 seconds. The two skips are the pre-existing E4 real-local-ASR tests that require explicit ignored model/audio paths; their reason was re-read with `-rs`. Check-in coverage is **29 tests** across lifecycle, concurrency/idempotency, Provider/redaction, safety, RBAC, frontend contracts, security and the patient-to-clinical integration journey. Security/integration directories: **22 passed**.
- Frontend: all three Node checks (`transcriptRange`, `voiceCapture`, `patientCheckIn`) passed; TypeScript/Vite production build passed with **59 modules**. The Check-in component now uses a synchronous in-flight guard and a patient/role/auth-boundary request generation guard, so rapid double-clicks and stale responses cannot update a new identity context.
- D3: 40/40 corpus hashes and frozen holdout digest verified; deterministic runtime hard gates passed; Provider layer remains explicitly `NOT_RUN` and deterministic fallback is reported separately.
- D4: frozen Copilot eval passed with provider `mock`; draft Check-in Events are excluded from Copilot and generic Event read/write paths; submitted raw evidence exposes patient messages only, never AI questions.
- Provider layers:
  - `mock`: full bounded journey passed in automation and browser runtime QA;
  - `deterministic_fallback`: missing/error/schema-invalid Provider, bounded medical-request refusal, raw-first retention and submitted exact provenance passed;
  - `live DeepSeek`: the current synthetic smoke reached a non-degraded live turn, but the strict final Summary failed validation and the server used deterministic fallback. Therefore the full live Check-in journey is **LIVE_NOT_VERIFIED_CURRENT**;
  - D3 frozen Provider layer: `NOT_RUN` by design.
- Browser runtime QA on a fresh synthetic DB covered rapid double-send, refresh restore, free supplement adaptation, Task-completion narrative, medical-advice refusal, four-question cap, return/correct, rapid double-submit, history reopen, explicit safety negation, deterministic high-risk stop, clinician Timeline/Event Detail, AI Summary, exact patient sources, patient/AI separation and role-switch draft clearing. Console warning/error count was 0 and horizontal overflow was false.
- Storage/security: SQLCipher 4.12.0 init, separate-key backup and rotated-key restore passed with **18 tables**, no plaintext header and plain-reader blocking. Caddy 2.11.4 validation, `pip check`, `npm ls --depth=0`, secret scan and `git diff --check` passed.
- Temporary browser-review and SQLCipher database/backup/restore files were verified by exact path and individually removed. The existing gitignored demo DB was not reseeded or overwritten.
