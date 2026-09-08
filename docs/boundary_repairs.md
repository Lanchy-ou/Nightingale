# Boundary repairs — architecture and operating guide

## Preserved contracts

Event → Artifact → exact Span remains canonical. Raw input, AI summaries and
human notes are separate. Human decisions, note versions, task identities and
provenance bindings are retained. Serving stays `base_only`.

## Repetition and semantics

`repeated_mentions.py` groups distinct Events inside a verified patient/clinic
scope. A second artifact or replay in the same Event does not add evidence.
Persistence flushes before reading the group so SQLite writers serialize, then
updates flags, explanations, scores and Glance projections in the same derived
transaction. IDs supplied in old `recompute_existing` output cannot authorize
updates. Seed uses the same grouping function without runtime depending on seed.

Display text and existing entity IDs remain compatible. New nullable
`semantic_context` carries concept_key, assertion, subject, temporality,
recognition_status and rule_version. The server interprets the exact anchored
source clause; provider semantic suggestions are not authority. Unicode text is
preserved, empty/generic display labels are not identity evidence. The bounded
lexicon lives in `backend/app/semantic_rules.py`; supported aliases include
headache/head pain/头痛. Only recognized, affirmative, patient, Event-current
statements count. Past Events can still contain then-current evidence. Unknown
time is not inferred from creation time. Uncertainty is separate from clinical
conflict `needs_review`; no new clinician authority is implied.

Fallback risk candidates preserve exact quotes. Clause checks suppress obvious
negation, family, past and hypothetical risk evidence. Unsupported meanings stay
uncertain; this is not general medical NLP. Patient emergency routing is a
separate existing rule path and is unchanged.

## Background maintenance

Glance and task GETs no longer invoke escalation or commit maintenance work.
`maintenance_jobs` is separate from notification tables and records kind,
target/patient/clinic IDs, state, attempts, due time, lease and reason code.
Deterministic job IDs and conditional lease claims prevent duplicate processing.
Each job rechecks scope/current task state and commits its escalation, original
marker, projection and system audit atomically. The original report source is
retained. Failure rolls back only that job. An expired lease can be reclaimed.

Defaults: 50 jobs/pass, 60-second interval, 120-second lease. Retry waits are 1,
5, 15 and 60 minutes; the fifth failure becomes `failed`. Discovery reads metadata;
its scan cost is outside GET, but still grows with data volume. The existing
notification sweep runs from this same independent process and retains its
configuration and delivery logic. It is not a new distributed queue platform.

Run from `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.run_maintenance --once
.venv/Scripts/python.exe -m scripts.run_maintenance --status
.venv/Scripts/python.exe -m scripts.run_maintenance --retry JOB_ID
.venv/Scripts/python.exe -m scripts.run_maintenance
```

Supervise the worker independently of API replicas and use identical database
and encryption environment. Monitor pending/failed status; errors are reason
codes without raw task text. Authentication session bookkeeping remains an
independent concern from clinical GET writes.

## Permissions and indirect exits

| Role | Clinical access | Administration |
| --- | --- | --- |
| admin | No default Event/Artifact/Glance/source/comment/version/clinical audit/check-in/task read | Accounts, invitations, sessions, imports, system/clinic settings and metadata statistics |
| clinician | Existing clinic-scoped clinical workflow, owns clinician notes | Existing permissions unchanged |
| staff | Existing clinic-scoped support workflow, owns staff notes | Existing permissions unchanged |
| patient | Own patient-facing projection and check-in workflow | No clinical workspace |

Admin invitations use a dedicated ID/name-only patient projection. Clinical API
requests still check scope: absent/cross-scope targets are 404; same-scope denied
permissions are 403. Hidden unconfirmed check-ins keep their existing 404
visibility behavior. Administrative audit exposes access/security metadata,
not clinical audit bodies. Notifications keep management metadata separate from
clinical inbox reads. No admin account receives clinician rights automatically.

## Model egress

`egress.py` defines exact root/collection field allowlists for summarize,
copilot, checkin_turn and checkin_summary. Extra identity/audit/internal metadata
is removed. Source/message/task IDs use request-local references restored locally
in structured responses. Collection values must be scalar and type-valid.
Redaction precedes provider calls; the final gate also rejects unrecognized
placeholders or still-visible supported sensitive patterns. DeepSeek adapters
are guarded even if a caller bypasses orchestration. Rejection invokes existing
local fallback/unavailable behavior and emits only `egress_rejected`.

Known-name/ID/phone rules now also handle email, common explicit address forms
and explicit name introductions, including bounded Chinese forms. Unknown family
names, unusual addresses, obfuscated text and arbitrary PHI are not comprehensively
recognized. Checks passing do not authorize real-record egress. Provider selection,
keys, timeout/cancellation and feature switches remain unchanged.

## Transaction ownership and migration

`ingestion_service.py` owns source/consult/confirmed-voice ingestion transactions.
Stage 1 commits Event + immutable source + audit. The provider runs between write
transactions. Stage 2 commits summary + Highlights + scoring/projections + audit.
Low-level `persist_derived` flushes but does not commit or roll back. The check-in
business service keeps its existing overall submission transaction and calls
low-level persistence within it. Stable IDs preserve retries and patient-safe
responses. A failed derived stage leaves the raw stage available for retry.

Migration implementations moved to `schema_migrations.py`; `db.py` retains engine,
session setup and lazy compatible migration imports. No migration framework or
new dependency was introduced. The boundary migration adds a nullable Highlight
column and the maintenance/repair tables; it is safe to rerun:

```powershell
.venv/Scripts/python.exe -m scripts.migrate_boundary_schema
```

## Existing data: preview, apply and recovery

Do not run `seed` on an existing database. Stop ingestion and the maintenance
process before backup/migration/backfill. For encrypted databases use the existing
backup/restore commands with keys supplied by the existing environment (never put
keys in commands or evidence). Restore to a **new** file and verify it before
modifying the original:

```powershell
.venv/Scripts/python.exe -m scripts.backup_encrypted_db --output E:/backups/nightingale-before-boundary.db
.venv/Scripts/python.exe -m scripts.restore_encrypted_backup --input E:/backups/nightingale-before-boundary.db --output E:/backups/nightingale-restore-check.db
```

For local plaintext SQLite, use SQLite's backup API with a new output file and
verify `PRAGMA integrity_check` and row counts after opening the backup; do not
copy a live WAL database file alone. Existing encryption mode stays unchanged.
Once the restore has been verified, migrate and preview both passes:

```powershell
.venv/Scripts/python.exe -m scripts.repair_boundaries --mode repetition --clinic-id clinic_001 --patient-id pat_001
.venv/Scripts/python.exe -m scripts.repair_boundaries --mode repetition --clinic-id clinic_001 --patient-id pat_001 --apply
.venv/Scripts/python.exe -m scripts.repair_boundaries --mode semantics --clinic-id clinic_001 --patient-id pat_001
.venv/Scripts/python.exe -m scripts.repair_boundaries --mode semantics --clinic-id clinic_001 --patient-id pat_001 --apply
```

Replace IDs with verified database IDs; omit patient scope to process the clinic,
or omit both to process all patients. Commands commit one patient at a time and
can resume after interruption. Preview reports current repeated-flag differences, semantic updates and
unsupported risk-flag removals separately; it does not claim an exact future score.
The first pass repairs scope using compatible entity keys; the second reinterprets
exact bound source quotes without calling a model. Mismatched source versions or
hashes are skipped, not guessed. Unrecognized valid quotes become unknown. For source-verified non-task candidates,
unsupported old automatic risk flags are also removed; task escalation risk is
not altered by semantic backfill.

Apply emits a repair ID only when business changes exist. Repair audit contains
IDs, rule version and counts. Internal repair snapshots retain only derived state
and source hashes needed for recovery, not source text. Old Highlights/versions,
human statuses, summaries and audit history are never deleted or rewritten.
Historical ranking/Shadow runs remain stored; repair records associate affected
patient/rule/cutoff and downstream observed-feedback/evaluation excludes earlier
runs conservatively. This can exclude valid older evidence as well as polluted
ones, intentionally favoring isolation over training volume.

To restore one derived batch (latest first if there are multiple passes):

```powershell
.venv/Scripts/python.exe -m scripts.repair_boundaries --restore REPAIR_ID --apply
```

Restore compares the complete saved after-state fingerprint (including human
state, projections and source hashes). Any later change refuses automatic restore;
review manually instead of overwriting new work. Whole-database restoration is a
separate offline recovery procedure and must not overwrite subsequent work.
Restart API and worker after validating results. No working/demo database
backfill, deployment, external delivery or push was performed by this change.
