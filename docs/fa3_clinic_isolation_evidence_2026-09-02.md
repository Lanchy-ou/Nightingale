# F_A3 Clinic-Isolation Evidence — 2026-09-02

Status: `IMPLEMENTED_WITH_LIMITS`

## Boundary

A3 protects patient-bound application interfaces if one endpoint omits or faults the central `authorize_scope` call. It does not claim database Row-Level Security, production multi-tenant certification, or cross-clinic sharing.

DB User resolved from the HttpOnly Session remains authoritative for user id, role, clinic id and patient id. Query-level ownership and role/action permission remain separate:

1. `app/clinic_scope.py` performs one SQL query that includes Clinic/Patient ancestry and returns no cross-scope row.
2. `app/authz.py` applies the existing `PERMISSIONS` role/action matrix.
3. `resource_not_found()` preserves the same 404 body for absent and out-of-scope objects.

## Interface inventory

Static inventory: 74 router handlers plus `/api/me`.

| Group | Representative routes | Ownership root |
|---|---|---|
| Patient | `/patients/{id}`, Events, Patient View, Glance, Tasks, Copilot, Consults | Patient → Clinic |
| Event/Artifact | Event artifacts/sources/notes, Artifact edit/revert/versions/diff | Event → Patient → Clinic |
| Collaboration | Comments and Event Audit | Comment/Version/Audit → Artifact/Event |
| Attention | Highlight provenance/status, Task transition/review/provenance | Highlight/Task → Event/Patient/Clinic |
| Patient Check-in | Patient list/start and direct Session lifecycle | CheckInSession → Patient/Event/raw Artifact/User |
| Voice | Capture/audio/transcribe/review/confirm | VoiceCapture → Patient/User and optional Event/Transcript |
| Shadow Learning | Coverage, Decision signal, admin replay/freeze/rollback | RankingRun → Patient/Clinic; Decision → Highlight; Signal → actor/run clinic |
| Identity/Admin | invites, users, sessions, access audit | User/Invite → Clinic; patient invite → Patient |
| Device-only | AI/Voice settings, transcript normalizers, capabilities | Not patient-bound; unchanged by A3 |

## Database ownership enforcement

- `PRAGMA foreign_keys=ON` on SQLite/SQLCipher connections.
- Deferrable schema FKs for legal parent/child staging in one transaction; production workflows also flush ownership parents before children.
- Metadata-only migration preflight refuses mismatched legacy relationships.
- Ownership triggers cover Event, User/Patient binding, Artifact author scope, Highlight references, Task references, RankingRun, RankingDecision, LearningSignal, GlanceProjection, Check-in and Voice.
- Conflict Artifacts may belong to a different Event only when both Events belong to the same Patient and Clinic. Both sources remain preserved.
- Trigger predicates use identifiers and ownership keys only. They do not read note/transcript bodies, interpret clinical facts, or calculate Importance/Shadow ranking.

Validated indexes:

- `ix_events_scope_timeline`
- `ix_highlights_patient_event`
- `ix_tasks_scope_list`
- `ix_glance_scope_read`
- `ix_ranking_runs_scope_latest`
- `ix_learning_signals_scope_decision`
- `ix_checkins_scope_direct`
- `ix_voice_scope_direct`

`EXPLAIN QUERY PLAN` verified the Glance scope read uses `ix_glance_scope_read`.

## Fault-injection and consistency evidence

Before implementation, a no-op `authorize_scope` allowed Clinic B clinician reads of Clinic A Patient and Highlight provenance. Ten representative patient-bound reads returned 200 rather than the missing-resource 404.

After implementation:

- the same ten reads match absent-resource 404 status and body;
- cross-clinic Highlight, Task, Artifact and LearningSignal writes return 404 and cause no status/signal mutation;
- Check-in and Voice direct ids remain hidden;
- mismatched Event/Task/RankingRun/Highlight/RankingDecision/LearningSignal relationships raise `IntegrityError`;
- migration preflight refuses a legacy Event whose Patient and Clinic disagree;
- each scoped Patient/Event/Artifact/Highlight/Task/RankingDecision loader issued exactly one SQL statement;
- the static bypass check passes;
- A1 projection/ranking capture does not commit inside the batch service.

## Regression and Session evidence

- A3 targeted: 23 passed.
- Full backend: 579 collected; 577 passed; 2 existing local-ASR-input skips.
- Frontend: TypeScript/Vite production build passed; 62 modules transformed.
- Real uvicorn with two independent in-memory Cookie Sessions:
  - `usr_clinician_01`, `clinic_001`: own Patient 200; Clinic B Patient 404.
  - `usr_clinician_02`, `clinic_002`: own Patient 200; Clinic A Patient 404.
  - each cross-clinic response body exactly matched its absent-Patient response.
- In-app browser initialization failed before a tab could be controlled, so visual browser evidence is `NOT_RUN`; it is not inferred from HTTP results.

The temporary acceptance database was synthetic, used only for this run, and removed afterward.

The existing gitignored synthetic Demo database passed the metadata-only preflight and was migrated in place. A read-back observed `foreign_keys=1`, 22 installed `a3_*` ownership triggers and seven `ix_*scope*` indexes (the additional Highlight patient/Event index uses a non-`scope` name).

## Performance comparison

Local synthetic TestClient Layer A, 100 samples per endpoint after 10 warm-ups:

| Endpoint | Before P95 ms | After P95 ms | Difference |
|---|---:|---:|---:|
| Glance | 5.742 | 6.403 | +0.661 |
| Events | 7.714 | 6.439 | -1.275 |
| Patient View | 5.639 | 5.320 | -0.319 |

All remain far below the local 300 ms Glance gate. These measurements show no material prototype regression; they do not establish production capacity.
