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
- DeepSeek: a current synthetic Check-in turn completed live, but the strict final Summary failed validation and fell back; therefore a complete live Check-in journey is not claimed;
- D3 frozen Provider layer: `NOT_RUN` by design.

## Provenance and authority

Every suggested Highlight stores its Event, AI Summary Artifact, raw source Artifact, and exact source Span. A failed quote restore or span resolution drops the candidate. Fuzzy matching is prohibited.

For Patient Check-in, candidate facts must name one patient `message_id` and copy a verbatim quote from that message. AI questions and acknowledgements can never become patient facts, Highlights, or Copilot evidence. AI summaries are system-authored and clearly separated from clinician/staff-authored material.

If patient/AI-derived content conflicts with a clinician-authored record, the clinician artifact remains authoritative or the candidate is marked for review. AI never overwrites a clinician note, staff note, patient instruction, or raw source.

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

The current final regression environment does not contain the ignored local model/audio inputs, so two real-local-ASR tests are explicitly skipped. Historical dated evidence records one observed synthetic local slice; current E4 status is therefore implemented with limits, not a fresh end-to-end ASR rerun.

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
Task_Card/          frozen vertical scope and Exit Gates
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
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In another terminal:

```powershell
Set-Location frontend
npm install
$env:VITE_DEMO_AUTH='true'
npm run dev
```

Demo mode exposes a role selector and legacy identity headers. Do not use it as deployment evidence.

### Product identity mode

Leave `VITE_DEMO_AUTH` and `NANTINGALE_DEMO_AUTH` unset/false. Open the frontend, log in with a seeded synthetic account, and let the server-side session cookie determine the role and patient binding. The canonical seeded password is documented in `backend/seed/fixture.py` for local synthetic demonstration only.

### Existing schema migration

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\migrate_phase_e_schema.py
.venv\Scripts\python.exe scripts\migrate_patient_checkin_schema.py
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

Voice is not required for Patient Multi-turn Check-in and remains default-off. The preferred Windows review flow is Admin → AI & Voice settings → Download local model → enable Voice. The command below remains available for technical/offline preparation.

```powershell
Set-Location backend
.venv\Scripts\python.exe scripts\prepare_local_asr.py --output <private-model-directory>
$env:NANTINGALE_VOICE_ENABLED='true'
$env:NANTINGALE_ASR_PROVIDER='faster_whisper'
$env:NANTINGALE_ASR_MODEL_PATH='<private-model-directory>'
```

Clinical and patient pages poll capability metadata every ten seconds. When Voice is disabled or the model is unavailable, the capture entry remains visible with the exact reason and any active microphone stream is released.

## Verification commands

```powershell
Set-Location backend
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

## Known limits

- Synthetic-data prototype only; no real PHI or production medical use.
- Local single-process/single-machine architecture, not distributed deployment.
- DeepSeek full Patient Check-in journey is not currently verified because the strict live Summary failed and fell back.
- D3 frozen Provider layer is `NOT_RUN`; deterministic fallback results are separate.
- E4 is default-off per device; real local ASR evidence depends on the ignored model and synthetic audio being present on that reviewer device.
- Voice has no diarization and no physical-microphone evidence in the final run.
- Self-learning is bounded interaction weighting, not clinical learning.
- Data decay is a shadow payload policy, not demonstrated total storage reduction.
- Copilot confirmation tokens are short-lived but not persisted as one-time records; a multi-worker deployment needs a shared confirmation secret.
- No independent clinical usability study, production load test, public hosting, penetration test, or regulatory assessment was performed.
- E5 cannot be called Submission Ready until a real 6–9 minute Demo Video is recorded and played end-to-end, the submitter name is supplied, and final attachment/link access is verified.

## Evidence and deliverables

- Candidate requirements: `2026 72 Hour Build_ Nightingale Candidate Brief 2.pdf`
- Attribution: `ATTRIBUTION.txt`
- Final evidence: `docs/final_submission_evidence_2026-08-28.md`
- Demo runbook: `docs/demo_video_runbook_2026-08-28.md`
- Submission email draft: `docs/submission_email_draft_2026-08-28.md`
- Technical Brief: `output/pdf/Nightingale_Technical_Brief.pdf`

The final evidence manifest is authoritative for commit hashes, exact command outcomes, Provider/ASR status, missing owner inputs, and Submission Ready status.
