# E3 Hybrid Storage / Data Decay — implementation brief and evidence

Date: 2026-08-28

Policy: `decay-v1`

Frozen fixture time: `2026-08-26T23:59:59`

## Scope and authority boundary

E3 is a deterministic maintenance policy over the existing longitudinal
record. It does not add a second clinical record, delete history, summarize raw
content, call an LLM, or move data to object storage.

```text
authoritative Event + Artifact.content
  -> server-side protection and exact-provenance checks
  -> Hot / Warm / Cold decision at injected as_of
  -> stored Highlight decay adjustment (0 / -1 / -2)
  -> optional verified Cold shadow payload

Glance GET -> stored final score only
Timeline / provenance -> authoritative Artifact.content only
Patient View -> existing explicit patient-safe projection only
```

The score contract remains:

```text
base_importance_score + adaptive_adjustment + decay_adjustment
  = importance_score
```

The age windows are Hot 0–30 days, Warm >30–365 days, and Cold >365
days. A future Event time fails safe to Hot. Protection is evaluated first and
cannot be overridden by age.

## Protection facts

An Artifact remains Hot with decay 0 when any related server-side fact is:

- `explicit_risk=true`;
- a real Task row in `open`, `in_progress`, or `reported_done` state;
- `clinician_confirmed=true`;
- Highlight status `pinned`;
- Highlight review status `needs_review`;
- the latest valid clinician-authored patient instruction used by the same
  patient-facing projection contract;
- exact provenance cannot be verified;
- canonicalization or an existing shadow archive integrity check fails.

The Task check reads Task rows and their statuses. It does not infer a pending
task from prose or trust an isolated client/legacy flag.

## Shadow archive schema and recovery

`artifact_storage_state` is a one-to-one metadata/shadow table keyed by
`artifact_id`. It records tier, controlled reason codes, policy version,
evaluation timestamps, canonical SHA-256, codec, compressed BLOB, byte counts,
and round-trip verification time.

Canonical serialization is UTF-8 JSON with sorted keys, compact separators,
Unicode preserved, and non-standard numeric values rejected. Cold candidates
use `zlib-json-v1`. A payload is persisted only after decompressing back to the
same canonical bytes. Recovery rechecks the codec, zlib stream, SHA-256, JSON
parse, and canonical byte equality. Exact spans are resolved again on the
restored object in automated tests.

`Artifact.content` is never removed or replaced. Artifact versions, comments,
audit logs, tasks, highlights, Events, and source spans remain unchanged. This
is a migration-readiness proof, not a hot-copy deletion design.

## Migration and runner

`app.db.migrate_e3_schema()` is an explicit, idempotent migration for both
plain SQLite and SQLCipher. It first preserves the E2 schema contract, then
creates the new table and tier index. Fresh seed and encrypted-demo creation
receive the full schema through SQLAlchemy metadata.

The runner accepts an explicit date and exactly one mode:

```text
python scripts/apply_storage_policy.py --as-of 2026-08-26 --dry-run
python scripts/apply_storage_policy.py --as-of 2026-08-26 --apply
```

Dry-run performs no schema, state, or score write. Apply runs migration, then
writes state and Highlight final scores atomically. Repeating the same policy
against unchanged authoritative data produces zero state/score updates even
when the runner clock is later. Output is metadata-only: artifact ids, tiers,
controlled reasons, counts, byte metrics, verification status, policy/as-of,
and timing; it contains no raw content, quote, patient name, or PHI.

## Observed synthetic evidence

The canonical 14-Artifact fixture produced:

| Metric | Observed |
|---|---:|
| Hot / Warm / Cold | 12 / 1 / 1 |
| Protected Artifacts | 7 |
| Cold archive candidates | 1 |
| Cold canonical bytes | 235 |
| Cold compressed bytes | 180 |
| Compressed/original ratio | 0.766 |
| Verified round trips | 1 |
| First apply state writes | 14 |
| First apply Highlight score writes | 3 |
| Identical second apply writes | 0 state / 0 Highlight |
| Dry-run elapsed | 8.4890 ms |
| First apply elapsed | 8.3320 ms |
| Identical second apply elapsed | 3.5574 ms |
| Archive build + restore P50 / P95 (1,000 samples) | 0.0220 / 0.0235 ms |

These timings are one run of
`python scripts/measure_storage_policy.py --roundtrip-samples 1000` on local
Windows 11, Python 3.13.5 and SQLite 3.50.2. Policy/apply/round-trip time is
reported separately from request latency and is not a production benchmark.

The 2025-04-15 low-value historical note becomes Cold / -2. The 2026-02-06
context note becomes Warm / -1. August 2026 data remains Hot. The nurse risk,
open blood-test Task context, and current patient instruction remain Hot.

## Read, privacy, and encrypted-storage gates

- Glance GET does not import E3 maintenance code and does not query
  `artifact_storage_state`, Artifact, Event, feedback, or audit history.
- Patient View retains its strict response schema and sentinel anti-leak tests;
  storage tier, hash, codec, payload, reason codes, and byte counts are absent.
- Cross-clinic authorization remains the existing uniform 404 behavior.
- SQLCipher migration is tested explicitly. Encrypted backup and restore retain
  the new table and a shadow-state row; a plain SQLite reader remains blocked.

The final 100-sample read baseline (10 warm-ups discarded) remained well below
the 300 ms prototype gate:

| Endpoint | Layer A P50 / P95 | Layer B P50 / P95 |
|---|---:|---:|
| Glance | 3.814 / 4.429 ms | 3.872 / 4.447 ms |
| Events | 6.374 / 7.096 ms | 6.335 / 7.025 ms |
| Patient View | 5.284 / 6.078 ms | 5.394 / 6.094 ms |

Layer A is in-process application + SQLite time; Layer B adds local Uvicorn and
loopback HTTP. These are single-user synthetic local measurements, not
distributed or production capacity evidence.

## Limits

The authoritative hot copy and compressed shadow copy coexist, so E3 cannot
claim total database storage savings. It does not implement production object
storage, hot-copy deletion, legal retention automation, cross-region archive,
or validation on real longitudinal patient data. If a future design externalizes
the payload, at-rest encryption and restore/provenance gates must be repeated
for that storage system before any authoritative-copy deletion is considered.
