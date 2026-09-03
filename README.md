# Nightingale 72 Hour Build

Nightingale is a synthetic-data prototype for one shared longitudinal patient record. It connects patient updates, consults, AI-scribed artifacts, clinician and staff work, tasks, collaboration, audit history, and exact provenance without treating AI output as clinical authority.

> Prototype boundary: this is not a production medical system. It does not diagnose, prescribe, adjust medication, replace emergency services, notify a clinic about emergencies, or prove clinical safety, usability, capacity, or regulatory compliance.

## Product model

The application has three deliberately different projections of one record:

- **Timeline**: what happened, ordered by real-world Event time.
- **Clinical Overview (Glance)**: what matters now, using precomputed deterministic ranking.
- **Patient View**: what the patient needs to know or do, using an explicit patient-safe projection.

The canonical internal model is:

```text
Patient
  -> Event
      -> Artifact
          -> exact Span
      -> Comments
      -> Tasks
      -> Audit / Versions

Highlight
  -> AI Summary Artifact
  -> raw source Artifact
  -> exact source Span
```

The Candidate Brief's broad `Entry` maps to an Event plus its parallel Artifacts. AI summaries, raw conversations/transcripts, clinician notes, staff notes, patient instructions, and Tasks remain separate records. Later comments, edits, and audit actions stay attached to the original Event and do not become new medical Events.

## Main user journeys

### Clinician and staff workspace

Clinician and staff users share a clinic-scoped shell with `Clinic Patients`, `Clinical Overview`, `Timeline`, `Notes`, and `Tasks`. Doctor and Nurse Consults remain separate Events even when they share an explicit encounter id. Manual transcripts must be reviewed into continuous, role-bounded speaker segments before confirmation.

Clinical Event Detail separates immutable raw material, AI summaries, role-authored notes, comments, versions, audit history, and source evidence. A clinician can open a Highlight or Copilot citation and resolve it to the exact raw source span.

### Patient workspace

Patient View contains only `Today`, `Care Plan`, `Check-in`, and `Visit Summaries`. It does not call clinical Timeline, Glance, Comment, Audit, revision, or internal-note endpoints.

Patients may start or report a visible Task as done. `reported_done` always waits for clinic verification; it never becomes `completed` because of patient text, AI output, or a Check-in.

### Bounded Patient Multi-turn Check-in

Check-in is a non-emergency information-collection assistant, not an open medical chatbot.

- One patient user can have one active or awaiting-confirmation session.
- Nightingale asks one question at a time from five types: severity, change, associated symptoms, Task progress, or patient concern.
- A maximum of four clarification questions is enforced by the server.
- The patient may answer freely, supplement, correct, skip, choose "nothing else", finish, abandon, return to correct, or confirm.
- Diagnosis, medicine start/stop, dose changes, and test-result interpretation receive a deterministic refusal.
- Transparent high-risk phrases run after raw persistence and before any Provider call. Clear matches stop ordinary questions and show urgent-help guidance without claiming formal triage or clinic notification. Narrow explicit negations are tested to avoid obvious false escalation.
- Rapid duplicate actions, refresh recovery, stale responses, role/session switches, and concurrent API requests are covered by deterministic guards and tests.

The persistent flow is:

```text
Patient
  -> patient_checkin Event
  -> raw_conversation
       - stable patient messages
       - separately marked Nightingale AI messages
  -> ai_patient_session_summary (only after confirmation)
  -> candidate Highlight
  -> exact patient message_id + quote + offset
```

The frontend saves each patient message first, then asks the server to process it. A retry reuses the same `message_id`. Provider or network failure cannot erase or replace the patient's original words. Active, awaiting-confirmation, and abandoned Events are hidden from every clinical Event read/write path; submitted and safety-escalated Events become visible to same-clinic clinical readers.

## AI and Provider boundary

`backend/app/llm_client.py` is the only LLM egress. Supported modes are:

- `mock`: deterministic, key-free test/demo Provider;
- `deepseek`: live adapter using an environment key;
- `deterministic_fallback`: server-owned fallback for missing keys, network/protocol failure, invalid schema, invalid provenance, or bounded medical requests.

There is no second Provider exit. Before egress, recursive redaction removes known names, IC/ID patterns, and phone numbers. Placeholder mappings remain in memory. Logs, audit rows, and error bodies store metadata rather than patient text or raw Provider payloads.

Provider output never decides authorization, safety escalation, question caps, session state, Task state, authorship, care-plan changes, or exact provenance. Strict schemas and server validation reject unknown fields, invalid actions, stale patient references, repeated question types, unsafe language, altered redaction placeholders, and non-exact quotes.

Current evidence distinguishes the layers:

- mock: full journeys verified;
- deterministic fallback: full bounded journeys verified;
- DeepSeek: a current synthetic mixed-language Provider run returned a strict complete summary and four candidates, and all four quotes resolved to exact source spans; this is one contract/provenance evaluation, not multilingual clinical validation or a complete live UI journey;
- D3 frozen Provider layer: `NOT_RUN` by design.

## Provenance and authority

Every suggested Highlight stores its Event, AI Summary Artifact, raw source Artifact, exact source Span, source Artifact version, and SHA-256 of the exact quote. A failed quote restore or span resolution drops the candidate. If an editable source changes later, provenance resolves the verified historical snapshot and labels the source as updated; a missing snapshot or hash mismatch fails closed instead of silently pointing at current text. Fuzzy matching is prohibited.

For Patient Check-in, candidate facts must name one patient `message_id` and copy a verbatim quote from that message. AI questions and acknowledgements can never become patient facts, Highlights, or Copilot evidence. AI summaries are system-authored and clearly separated from clinician/staff-authored material.

If patient/AI-derived content conflicts with a clinician-authored record, the clinician artifact remains authoritative or the candidate is marked for review. Deterministic allergy checks also flag contradictions against human-authored Staff Notes and confirmed Nurse Consult transcripts without choosing which statement is true; unresolved conflicts surface ahead of normal Glance suggestions. AI never overwrites a clinician note, staff note, patient instruction, or raw source.

## RBAC and identity

Roles are `patient`, `staff`, `clinician`, and `admin`. Authorization is server-side in `backend/app/authz.py`; the database User is authoritative for role, clinic, and patient binding.

- Patient: own patient-safe view, own visible Tasks, own Check-in and permitted Voice capture; no internal comments, raw clinical AI notes, clinical authoring, or another patient's record.
- Staff: same-clinic staff notes, Nurse Consult, Tasks, Comments, and permitted review; cannot author/edit as clinician.
- Clinician: same-clinic clinician notes, Doctor Consult, Copilot, Tasks, Comments, provenance, and review; cannot author/edit as staff.
- Admin: clinic-scoped identity/session/invite/access-audit oversight; no clinical Note, Copilot, Task, or plan authoring.

Cross-clinic and not-own-patient resources return the same generic 404. Same-scope missing permission returns 403. Product mode uses invite, Argon2id registration/login, an HttpOnly session cookie, server session restore, and logout revocation. Legacy identity headers and the role selector exist only when both frontend and backend demo-auth flags are explicitly enabled.

Patient, role, auth-session, and patient-record changes remount or reset sensitive UI state. Pending requests are aborted and stale responses are ignored.

## Revision, collaboration, Tasks, and importance

Editable notes use full version snapshots. Edits use optimistic compare-and-swap; stale same-section writes return 409. Revert creates a new version and never rewrites history. Comments support Event/Artifact anchors, replies, mentions, and resolve/unresolve. Audit rows are metadata-only.

Tasks are first-class, clinic-scoped records with an Event origin and optional exact Artifact/Span source. Patients only Start or Report done. Staff/clinicians verify completion or cancel. A Check-in Task statement remains evidence awaiting human review.

Glance ranking is precomputed and deterministic. E2's bounded "self-learning" uses only controlled same-clinic interaction signals keyed by entity type. It does not learn clinical truth, use raw text/PHI as a feature, train a model, or bypass protections for risk, unresolved Tasks, clinician-confirmed, pinned, or review-needed content.

## E3 data-decay boundary

`decay-v1` is a protection-first maintenance policy. It assigns hot/warm/cold shadow state and may create a verified compressed JSON shadow payload for an old low-priority Artifact. Authoritative Artifact content and provenance are never removed or overwritten. Voice recording BLOBs are not compressed by E3.

Current local synthetic evidence is maintenance timing and one shadow compression ratio only. It is not a claim of production retention policy, clinical forgetting, or total database storage savings.

## E4 Voice boundary

Voice is default-off. The local adapter uses pinned `Systran/faster-whisper-base`, CPU int8, `local_files_only=True`, and in-memory PyAV container validation. Audio stays in an encrypted SQLCipher BLOB and never enters `LLMClient` or E3 compression.

The trusted device Admin can manage this instance at `/admin/settings`. `Local Private` and Voice Off are the safe defaults. A DeepSeek key must pass a live connection check before it is stored under a versioned Windows Credential Manager reference; plaintext keys are never stored in the database, browser storage, API responses, Audit, or logs. Saving Admin settings makes the database authoritative immediately, while `DEEPSEEK_API_KEY` remains a first-start compatibility path. Removing a key switches the instance back to Local Private.

The same page reports the pinned Voice model revision and can start one background download into the server-owned ignored model directory. Voice cannot be enabled until the model is ready. Development SQLite is limited to synthetic audio and shows a warning; production Voice requires SQLCipher. Disabling Voice rejects new capture/upload/transcribe/confirm work but preserves existing recordings, transcripts, and provenance.

The adapter does not perform diarization and does not invent confidence. Machine segments begin with unknown speaker and require role-bounded human review, explicit issue resolution, and continuous canonical indexes before confirmation. Physical-microphone capture, noisy/code-switching accuracy, clinical accuracy, and production throughput are not claimed.

The ignored local `Systran/faster-whisper-base` model and generated synthetic WAV were explicitly supplied to the two real-local-ASR tests in the current final environment; both passed. The ordinary full-suite command deliberately omits those private input paths, so the same two tests remain explicit skips there. The observed slice proves local transcription mechanics only: key English clinical phrases were preserved, while two Malay phrases were misrecognized. Physical-microphone, noisy-clinic, diarization, and multilingual clinical accuracy remain unverified.

## Security and deployment

Unit tests use disposable plain SQLite. The single-machine product demo uses SQLCipher whole-database encryption with separate database, backup, and restored-database keys. Existing targets are never overwritten. Caddy terminates local TLS, redirects HTTP to HTTPS, serves the built SPA, and proxies `/api/*` to loopback FastAPI.

The current E5 secure-demo verification observed:

- SQLCipher 4.12.0, 18 tables, no plaintext SQLite header, normal SQLite reader blocked;
- separately keyed backup and rotated-key restore with the same protections;
- Caddy TLS 1.3 with `TLS_AES_128_GCM_SHA256` and an explicitly trusted local CA file;
- secure/HttpOnly/SameSite cookie, exact-origin CSRF/CORS, security headers, logout revocation, and anonymous denial.

This is local synthetic evidence, not a public-host, production-security, penetration-test, or compliance certification.

## Performance

`backend/scripts/measure_glance.py` uses a throwaway seeded SQLite database, 10 warm-ups, and 100 samples per endpoint. It reports both in-process TestClient and local uvicorn/HTTP layers.

Current local synthetic P95:

| Endpoint | Layer A P95 | Layer B P95 |
|---|---:|---:|
| Glance | 4.626 ms | 5.115 ms |
| Events | 8.030 ms | 8.189 ms |
| Patient View | 6.521 ms | 6.434 ms |

The Glance warm path is below the 300 ms requirement in this local fixture. These numbers do not establish production capacity or multi-user performance. See `backend/docs/perf_baseline.md`.

## Repository layout

```text
backend/app/        FastAPI, SQLAlchemy, RBAC, pipelines and domain services
backend/seed/       canonical synthetic longitudinal fixture
backend/tests/      unit, regression, security and integration tests
backend/evals/      frozen D3/D4 synthetic evaluation assets
frontend/src/       React/TypeScript patient and clinical journeys
deploy/             Caddy configuration and environment template (no secrets)
docs/               decisions and dated evidence
output/pdf/         final Technical Brief PDF
```

## Setup

Requirements: Python 3.13+, Node.js 18+, and PowerShell examples below. Use synthetic data only.

### Development/demo mode

```powershell
Set-Location backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt

# Rebuild and seed the local synthetic development database.
.venv\Scripts\python.exe -c "from app.db import engine, SessionLocal; from seed.seed import create_schema, seed; create_schema(engine); db=SessionLocal(); seed(db); db.close()"

$env:NANTINGALE_DEMO_AUTH='true'
$env:NANTINGALE_LLM_PROVIDER='mock'
$env:NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES='5' # local demo/test; production default is 720
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location frontend
npm ci
$env:VITE_DEMO_AUTH='true'
npm run dev
```

Demo mode exposes a role selector and legacy identity headers. Do not use it as deployment evidence.

### Product identity mode

Leave `VITE_DEMO_AUTH` and `NANTINGALE_DEMO_AUTH` unset/false. Open the frontend, log in with a seeded synthetic account, and let the server-side session cookie determine the role and patient binding. The canonical seeded password is documented in `backend/seed/fixture.py` for local synthetic demonstration only.

### New clinic onboarding without seed

The deployment owner creates one 24-hour, single-use setup link. This command
safely creates missing tables and applies the F_B5 migration; it does not run or
clear the synthetic fixture:

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\create_clinic_bootstrap.py --base-url http://localhost:5173
```

Open the printed `/setup#token=...` link once, create the Clinic and its first
Admin, then sign in through the normal login page. Only the token hash is stored.
The raw link is a temporary deployment secret and must not be copied into logs,
screenshots, source control, or support tickets.

After login, the Admin can use **Patient import** to preview and commit a UTF-8
CSV containing exactly `external_patient_id,name` (maximum 1 MB / 1,000 rows).
Valid rows are imported; invalid, duplicate, and conflicting rows remain in the
downloadable report and never overwrite an existing Patient. Account invitations
remain a separate explicit step.

Device Provider credentials and the local Voice model are deployment-owned.
Clinic Admins choose only their own inherited/overridden AI and Voice policy.
Deployment management is local and never accepts an API key as a command-line
argument:

```powershell
.venv\Scripts\python.exe scripts\manage_device_settings.py show
.venv\Scripts\python.exe scripts\manage_device_settings.py set-key
.venv\Scripts\python.exe scripts\manage_device_settings.py set-ai-default local
.venv\Scripts\python.exe scripts\manage_device_settings.py prepare-voice-model
.venv\Scripts\python.exe scripts\manage_device_settings.py set-voice-default enabled
```

`set-key` prompts privately and performs the existing Provider verification. Do
not run it without authorization to use a real Provider.

### Synthetic demo scenarios

The deterministic fixture keeps Alice Tan as the primary seven-Event story and
adds purpose-built records for UI and scope validation:

- Ben Lim: sparse patient with no Events (empty states);
- Maya Rahman: five Events, reported-done patient action, internal staff queue,
  exact-source Glance items, and resolved collaboration;
- Daniel Koh: twelve cross-year Events, long Timeline, current open action, and
  completed historical action;
- Leah Ong: three Events in `Other Demo Clinic`, visible only to that clinic.

The primary clinic also has a second synthetic clinician and nurse. Optional
patient logins are `maya@demo.clinic` and `daniel@demo.clinic`; the other-clinic
journey uses `doctor@other-demo.clinic` and `leah@other-demo.clinic`. All use the
same local synthetic demo password as the original accounts. These records are
hand-written and contain no real patient data or external dataset material.

### Existing schema migration

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\migrate_phase_e_schema.py
.venv\Scripts\python.exe scripts\migrate_patient_checkin_schema.py
.venv\Scripts\python.exe scripts\migrate_fb5_schema.py
```

Migrations are explicit and idempotent. `create_all` is not presented as an old-schema migration.

### SQLCipher + Caddy single-machine demo

Copy `deploy/.env.example` to an untracked private environment file or provide the variables through a secret manager/process environment. Replace every placeholder with three independent 32+ character keys and private absolute paths. The backend does not load `.env` files automatically.

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\init_encrypted_demo.py
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

Build the frontend, then run from `deploy` with private `XDG_DATA_HOME` and `XDG_CONFIG_HOME`:

```powershell
caddy validate --config Caddyfile --adapter caddyfile
caddy run --config Caddyfile --adapter caddyfile
```

Verify without bypassing TLS:

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\verify_secure_demo.py --ca-file <private-caddy-root.crt>
```

Detailed commands and boundaries are in `docs/d5_deployment_security_decisions.md`.

### Optional local Voice preparation

Voice is not required for Patient Multi-turn Check-in and remains default-off. The deployment owner prepares the shared model; each Clinic Admin may then enable or disable Voice only for that clinic. The existing technical/offline preparation command remains available.

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\prepare_local_asr.py --output <private-model-directory>
$env:NANTINGALE_VOICE_ENABLED='true'
$env:NANTINGALE_ASR_PROVIDER='faster_whisper'
$env:NANTINGALE_ASR_MODEL_PATH='<private-model-directory>'
```

Clinical and patient pages poll capability metadata every ten seconds. When Voice is disabled or the model is unavailable, the capture entry remains visible with the exact reason and any active microphone stream is released.

## Verification commands

Run verification in a fresh terminal. Do not inherit the Demo Provider override:

```powershell
Set-Location backend
Remove-Item Env:NANTINGALE_LLM_PROVIDER -ErrorAction SilentlyContinue
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m pytest tests\security tests\integration -q
.venv\Scripts\python.exe scripts\evaluate_transcripts.py --validate-corpus
.venv\Scripts\python.exe scripts\evaluate_transcripts.py --evaluate-runtime
.venv\Scripts\python.exe -B scripts\evaluate_copilot.py
.venv\Scripts\python.exe scripts\measure_glance.py
.venv\Scripts\python.exe scripts\measure_storage_policy.py
.venv\Scripts\python.exe -m pip check
.venv\Scripts\python.exe scripts\check_no_secrets.py

Set-Location ..\frontend
node tests\transcriptRange.test.mjs
node tests\voiceCapture.test.mjs
node tests\patientCheckIn.test.mjs
npm run build
npm ls --depth=0

Set-Location ..
git diff --check
```

Current pre-E5 evidence: backend 509 passed / 2 explicit real-local-ASR-input skips; security/integration 22 passed; Patient Check-in 29 passed; D3 corpus/runtime and D4 frozen eval passed; three frontend Node checks and the 59-module production build passed. The dated final manifest records the final-commit rerun and any later changes.

Post-E5 Admin settings and frontend pre-visual repairs are tracked separately in `docs/frontend_previsual_repair_evidence_2026-08-28.md`. That current working-tree verification collected 524 backend tests (522 passed / 2 explicit local-ASR-input skips), passed the 60-module production build, and re-ran four-role product-session browser acceptance. It does not rewrite the historical E5 evidence.

The later deterministic demo-data expansion collects 532 backend tests (530
passed / the same 2 explicit local-ASR-input skips), preserves Alice's canonical
story, and adds sparse, task-heavy, dense-history, and cross-clinic browser
journeys. This is synthetic UI/authorization coverage, not clinical validation.

Current F Final evidence (2026-09-03): backend 714 collected / 712 passed / the
same 2 explicit local-ASR-input skips; the 9-test Doctor Consult review slice,
75-test provenance/RBAC/publication/concurrency group, 62-test SL1/SL2/SL3
isolation group, and 112-module frontend production build passed. The three
Doctor review attestations and frozen Malay-English-Hokkien transport case are
engineering evidence only, not multilingual clinical validation.

### Automated coverage of the official feedback scenarios

The full backend collection includes every completed or implemented-with-limits behavior below, including negative, scope, timeout, concurrency, and fail-closed paths. `NOT_IMPLEMENTED` rows are stated as product boundaries and are not represented by false-positive feature tests.

| # | Current status | Primary automated evidence |
|---:|---|---|
| 1 | `NOT_IMPLEMENTED` | Email/password identity boundary: `test_auth_sessions.py`, `test_auth_invites.py` |
| 2 | `IMPLEMENTED_WITH_LIMITS` | Clinic isolation and defense in depth: `test_fa3_clinic_isolation.py`, `test_rbac_scope.py`, `security/test_cross_patient_sentinels.py` |
| 3 | `IMPLEMENTED_WITH_LIMITS` | Sanitized application/proxy/Voice logging: `tests/security/test_operational_logging*.py`, `test_caddy_*`, `test_voice_storage_and_logs.py` |
| 4 | `IMPLEMENTED_AND_VERIFIED` | Redaction-before-egress and exact restoration: `test_redaction.py`, `test_ai_pipeline_e2e.py` |
| 5 | `IMPLEMENTED_WITH_LIMITS` | Clinic bootstrap, settings and CSV import: `test_fb5_onboarding.py`, `test_fb5_clinic_settings.py`, `test_fb5_patient_import.py`, `integration/test_fb5_clinic_onboarding_journey.py` |
| 6 | `IMPLEMENTED_WITH_LIMITS` | Mixed-language transport/review/provenance plus live contract evidence: `test_feedback_consult_review.py`, `test_deepseek_provider_contract.py`, `test_voice_local_asr_integration.py` |
| 7 | `NOT_IMPLEMENTED` | Post-consult Voice boundary only: `test_voice_capabilities.py`, `test_voice_capture_api_lifecycle.py`; no streaming alert claim |
| 8 | `IMPLEMENTED_WITH_LIMITS` | Total Provider deadline, cancellation and fallback: `test_fa5_provider_timeout.py` |
| 9 | `IMPLEMENTED_AND_VERIFIED` | Useful deterministic Provider fallback: `test_ai_pipeline_fallback.py` |
| 10 | `IMPLEMENTED_AND_VERIFIED` | Compare-and-swap conflict, versions and revert: `test_concurrent_edits.py`, `test_revision_history.py` |
| 11 | `IMPLEMENTED_WITH_LIMITS` | Exact-version in-product delivery receipt: `test_b11_instruction_receipts.py`; no external channel claim |
| 12 | `IMPLEMENTED_WITH_LIMITS` | Draft/publish/correct/withdraw and human authority: `test_b12_instruction_publication.py`, `test_b12_frontend_contract.py` |
| 13 | `IMPLEMENTED_AND_VERIFIED` | Contradictory allergy sources preserved for review: `test_ai_conflict_authority.py` |
| 14 | `IMPLEMENTED_WITH_LIMITS` | Explainable deterministic priority semantics: `test_fa2_patient_review_workflow.py`, `test_glance_ordering.py`, `test_longitudinal_scoring.py` |
| 15 | `IMPLEMENTED_WITH_LIMITS` | Clinic-scoped, bounded, auditable Shadow learning: `test_sl1_*`, `test_sl2_*`, `test_sl3_*`, `test_self_learning_importance.py` |
| 16 | `IMPLEMENTED_AND_VERIFIED` | Version/hash-bound exact provenance and fail-closed resolution: `test_highlight_provenance.py`, `test_provenance_resolution.py`, `test_archive_roundtrip.py` |

This matrix is a navigation index, not a substitute for the tests. The authoritative status, first break, and remaining production boundary for each scenario are recorded in `docs/real_clinic_readiness_status_2026-08-31.md`.

## Known limits

- Synthetic-data prototype only; no real PHI or production medical use.
- Local single-process/single-machine architecture, not distributed deployment.
- A current live DeepSeek mixed-language summary/provenance run passed, but a complete live Patient Check-in UI journey and multilingual clinical validity are not claimed.
- D3 frozen Provider layer is `NOT_RUN`; deterministic fallback results are separate.
- E4 is default-off per device; real local ASR evidence depends on the ignored model and synthetic audio being present on that reviewer device.
- Voice has no diarization and no physical-microphone evidence in the final run.
- Self-learning now includes deterministic SL1 ranking, two frozen-synthetic
  SL2 Shadow models, and an SL3 bridge that automatically compiles eligible
  explicit outcome labels into a content-free offline dataset. No real
  clinician labels are available; training is never automatic and formal
  Glance remains `base_only`.
- Data decay is a shadow payload policy, not demonstrated total storage reduction.
- Copilot confirmation tokens are short-lived but not persisted as one-time records; a multi-worker deployment needs a shared confirmation secret.
- No independent clinical usability study, production load test, public application hosting, penetration test, or regulatory assessment was performed.
- Repository-local verification and packaging are complete. Demo Video playback and email delivery are owner-controlled external evidence and are not stored or independently verified in this repository.

## Evidence and deliverables

- Candidate requirements: `2026 72 Hour Build_ Nightingale Candidate Brief 2.pdf`
- Attribution: `ATTRIBUTION.txt`
- Final evidence: `docs/final_submission_evidence_2026-08-28.md`
- Current real-clinic readiness ledger: `docs/real_clinic_readiness_status_2026-08-31.md`
- F1/A real-clinic hardening closeout: `docs/f1_a_closeout_2026-09-02.md`. A1–A5 are complete with documented limits; D safeguards survived final regression; the final reason-code matrix and 16-scenario ledger are recorded. Formal Glance remains base-only and live Provider evidence remains separate. Synthetic SL2 Shadow training is complete; the SL3 observed-feedback bridge exists, but real-feedback training and serving promotion remain blocked.
- F Final consult review evidence: `docs/final_feedback_consult_review_evidence_2026-09-03.md`.
- Self-Learning design and release boundary: `docs/self_learning_design_and_release_boundary_2026-09-03.md`.
- Self-Learning evidence: `docs/sl1_attention_ranking_evidence_2026-09-02.md`, `docs/sl2_shadow_pairwise_evidence_2026-09-03.md`, and `docs/sl3_observed_feedback_training_bridge_evidence_2026-09-03.md`.
- Frontend pre-visual repair evidence: `docs/frontend_previsual_repair_evidence_2026-08-28.md`
- Submission email draft: `docs/submission_email_draft_2026-08-28.md`
- Technical Brief: `output/pdf/Nightingale_Technical_Brief.pdf`

The final evidence manifest is authoritative for its dated command outcomes and capability boundaries. Current external delivery status is owner-controlled and may be newer than that dated manifest.
