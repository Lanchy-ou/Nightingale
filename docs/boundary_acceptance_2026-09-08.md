# Boundary repair acceptance — 2026-09-08

## Scope and state

Implemented R1 → R2A → R3 → R4 → R5 → R2B → R6 on local branch
`codex/boundary-repairs-20260908`. Working/demo databases were not migrated or
backfilled. Tests, performance data and browser changes used isolated synthetic
databases. No push, deployment or external submission was performed.

The [operating guide](boundary_repairs.md) covers migration, separate API/worker
startup, preview/apply, verified backup and guarded restore. Task cards are in
[boundary_tasks](boundary_tasks/R1.md). Apply is an offline operator action;
shipping the repair tool does not mean existing data has already been repaired.

## Automated verification

Final complete backend suite: **800 passed, 2 skipped; 267.33 seconds**.
Raw JUnit evidence: [full suite](boundary_tests_2026-09-08.xml).
The two skips are existing opt-in real local ASR tests requiring explicit model
and synthetic audio paths. Mock voice lifecycle/security tests run normally.
SQLCipher backup/restore, migration, RBAC, revision history, concurrency, source
binding, patient-view isolation and provider timeout/cancellation gates are
included in the complete suite.

```powershell
# From backend; choose a fresh basetemp directory on Windows:
.venv/Scripts/python.exe -m pytest -p no:cacheprovider --basetemp=../tmp/boundary-verification --junitxml=../docs/boundary_tests_2026-09-08.xml
# From frontend:
npm run build
```

Frontend production build passed: TypeScript + Vite, 119 transformed modules.
Browser used that production bundle. `git diff --check` passed.

Separate reconstructed task snapshots were also checked from the original Git
baseline in a temporary directory before creating review commits:

| Task | Focused tests passed |
| --- | ---: |
| R1 | 6 |
| R2A | 20 |
| R3 | 13 |
| R4 | 12 |
| R5 | 7 |
| R2B | 19 |
| R6 | 46 |

[Per-snapshot results](boundary_commit_checks_2026-09-08.json) document those
checks. The final suite supersedes snapshot counts and includes subsequent
regressions for unsupported historical risk and guarded derived transactions.
Additional focused evidence: [repair](boundary_repair_tests_2026-09-08.xml),
[transactions](boundary_transaction_tests_2026-09-08.xml),
[maintenance/admin/egress/notifications](boundary_tail_tests_2026-09-08.xml).

Reproduced failures before correction included cross-patient repeated flags,
Unicode empty-key collisions, negated/family fallback risk, GET invoking due
maintenance, and authentication heartbeat invoking the global notification
outbox. The final tests cover these counterexamples, same-Event representations,
untrusted recomputation IDs, concurrent ingestion, lease expiry, dual workers,
fifth-failure handling, metadata-only admin exits, four egress schema guards,
and failure injection at summary/Highlight/projection/audit persistence.

## Browser verification

Local API on `127.0.0.1:8018`, isolated seeded database, mock provider,
notifications disabled. Browser checks used the compiled frontend and existing
synthetic demo identities:

- Clinician created a new Doctor Consult from three speaker-labelled transcript
  segments, reviewed all confirmation checks and saved successfully.
- Raw transcript and AI summary remained separate; the mock response produced
  zero candidate highlights, a supported result rather than fabricated evidence.
- Added an independent clinician assessment/plan, then an Event comment; both
  persisted and appeared in the Event lifecycle.
- Returned to Glance and opened an existing headache highlight's exact original
  patient-message span. The source panel showed the complete source message and
  Event → Artifact → Span navigation.
- Switched to Ben: Alice's source/context panel cleared and Ben showed his own
  empty Glance, without the prior comment/source state.
- Patient login rendered Today/Care Plan/Check-in/Visit Summaries, with care
  actions and patient instructions rather than the clinical workspace.
- Staff login rendered the nurse workspace and authorized patient Glance.
- Admin login rendered account management; Invitations → Patient loaded only
  patient name/ID choices through the new administrative endpoint.
- Browser console warning/error collection was empty.

No real email, provider or notification delivery was exercised. Existing local
notification doubles cover delivery/retry behavior automatically.

## 10,000 overdue-task Glance measurement

Reproduce from `backend`:

```powershell
.venv/Scripts/python.exe -m scripts.measure_boundary_glance --output ../docs/boundary_performance_2026-09-08.json
```

The script always builds a fresh temporary database. Fixed synthetic time:
2026-09-08 12:00. Backlog: 10,000 valid due patient-review tasks with associated
Events, artifacts, sessions and workflows, spread across 100 additional patients
and two clinics. Requests read the canonical patient's Glance. A separate worker
thread continuously sweeps during the running case to exercise write contention;
production uses the documented 60-second polling interval.

Environment: Windows 11 build 22000, Python 3.13.5, SQLite 3.50.2,
SQLAlchemy 2.0.52; FastAPI TestClient with a real file database. This measures
application/SQLite behavior, not HTTP/TLS network latency or deployment capacity.

| Worker | Warmups | Measured requests | P95 | Errors |
| --- | ---: | ---: | ---: | ---: |
| Stopped | 10 | 100 | 5.305 ms | 0 / 100 |
| Running | 10 | 100 | 12.297 ms | 0 / 100 |

P95 is the 95th ordered observation. Both satisfy the ≤300 ms target. SQL hooks
recorded **zero request-thread INSERT/UPDATE/DELETE statements**. The worker
completed 50 jobs during the run, with zero failed/retrying jobs; the measurement
is not a claim that all 10,000 tasks drained in that interval. Header-based demo
auth was used for timing; a separate cookie-session regression forces last_seen
refresh with notifications enabled and proves it does not invoke business work.
[Raw performance JSON](boundary_performance_2026-09-08.json).

## Compatibility and remaining operational limits

- Nullable semantics allow old rows to be read after additive migration. Source
  mismatches are skipped, never repaired through fuzzy matching or another model.
- Limited lexicon and pattern detection intentionally leave unsupported meaning
  unknown. This is a synthetic-data prototype, not a general clinical NLP or
  real-PHI de-identification guarantee.
- Maintenance state is durable, but a supervisor must keep the separate process
  running. Discovery scans still grow with stored data; they no longer burden GET.
- Guarded repair snapshots prevent overwriting later manual/projection changes.
  Historical evaluation evidence is retained but conservatively excluded before
  affected patient/rule repair cutoffs; serving remains `base_only`.
- Existing database backup/restore must be verified before actual backfill. No
  automatic changes to the working database are included in this delivery.
