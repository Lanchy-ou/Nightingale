# F_A3 Task Card — Clinic-Isolation Defense in Depth

> Official scenario: 2
> Priority: A
> Status: IMPLEMENTED_WITH_LIMITS — owner-approved A3-v1 implemented 2026-09-02

## Outcome

Ensure that one defect or omitted call in the central scope check does not expose another clinic's patient data, while keeping one authoritative role-permission model and uniform non-existence behavior.

## Current verified baseline

- Product identity is an HttpOnly session resolved to the database User on every request.
- `authorize_scope` enforces clinic and patient ownership; `authorize` adds role/action permission.
- Patient-directory queries independently filter `Patient.clinic_id`.
- Cross-clinic and absent resources use a uniform 404.
- No database Row-Level Security or complete second resource-loading boundary exists.

## Discussion gates

1. Choose the second boundary: scoped query/load helpers, ORM criteria, database constraints/triggers, PostgreSQL RLS, or a bounded combination.
2. Keep object scope and role/action permission separate; do not create two conflicting permission matrices.
3. Decide how to enforce Patient/Event/Artifact/Highlight/Task clinic consistency for legacy and newly written rows.
4. Define the acceptable migration/deployment impact for the 48-hour prototype.

The default candidate for discussion is scoped resource loaders plus cross-entity consistency checks. A PostgreSQL/RLS migration is not assumed.

## Required route inventory

Inventory every list and direct-object path for patients, events, artifacts, highlights/provenance, comments, versions/audit, Tasks, consults, Check-ins, Voice, Admin, invites, and settings. Record where identity, SQL scope, role permission, and uniform 404 are enforced.

## Failure-first evidence

- Disable or monkeypatch `authorize_scope` and prove the current direct-object blast radius.
- Attempt Clinic B reads/writes against Clinic A patient, Event, Artifact, Highlight, Task, comment, revision, and audit resources.
- Insert or attempt inconsistent cross-clinic relationships and show which layer rejects them.
- Keep the current fixture count explicit rather than generalizing it to production.

## Exit gate

- Every patient-bound direct-object load has an approved query-level scope boundary in addition to role authorization.
- A fault-injected no-op `authorize_scope` still cannot expose cross-clinic patient resources through the tested routes.
- Cross-entity clinic/patient consistency is enforced or rejected deterministically.
- Cross-clinic and absent resources remain indistinguishable.
- Product-session Clinic A/B browser journeys and full RBAC regressions pass.
- Documentation states the remaining SQLite/no-RLS boundary honestly.

## Non-goals

No production multi-tenant certification, broad database migration, duplicate authorization authority, frontend-only guard, or cross-clinic data-sharing feature.

## Approved A3-v1 design

- Patient-bound direct-object routes use explicit one-query scoped loaders. Scope ownership is filtered in SQL; `authz.PERMISSIONS` remains the only role/action matrix.
- SQLite/SQLCipher connections enable foreign keys. Ownership-only triggers validate Patient/Event/Artifact/Highlight/Task/Glance/Ranking/Learning/Check-in/Voice relationships without reading clinical content or computing ranking.
- Existing-database migration runs a metadata-only ownership preflight and fails closed on inconsistent rows. It never repairs or merges clinical records automatically.
- A static AST gate rejects patient-bound route parameters passed to global `db.get` calls.
- Cross-clinic background authority is limited to the named patient-review sweep, migration/install functions, and synthetic seed/highlight generation.
- Formal Glance remains A2 `base_only`; A1 records RankingRun/Decision batches in the caller's single transaction and remains Shadow-only.

## Implementation evidence (2026-09-02)

- Failure-first baseline: 10 cross-clinic read paths returned 200 when `authorize_scope` was fault-injected to a no-op; inconsistent Event/Task/RankingRun rows were accepted.
- After implementation: `backend/tests/test_fa3_clinic_isolation.py` covers fault-injected reads/writes, Check-in/Voice direct ids, uniform 404, no-mutation writes, cross-entity rejection, migration preflight, single-query loaders, active FK/indexes, the privileged allowlist, A1 transaction ownership, and two DB-backed Cookie Sessions.
- Static gate: `backend/scripts/check_clinic_scope_bypass.py` reports `A3_SCOPE_BYPASS_PASS`.
- Full backend regression: 579 collected; 577 passed; 2 existing local-ASR-input skips.
- Frontend production build: passed; 62 modules transformed.
- Real uvicorn dual-Session HTTP acceptance: Clinic A and Clinic B each read their own Patient (200); both cross-clinic Patient reads matched the absent-resource 404 body exactly.
- Browser UI acceptance: `NOT_RUN` because the in-app browser runtime failed during local initialization. HTTP Session evidence is not relabelled as visual browser evidence.
- Performance, 100 samples after 10 warm-ups, local TestClient Layer A: Glance P95 5.742 ms before → 6.403 ms after; Events 7.714 → 6.439; Patient View 5.639 → 5.320. This is local synthetic evidence, not production capacity.

## Remaining limits

- This is application query isolation plus SQLite/SQLCipher ownership enforcement, not PostgreSQL Row-Level Security and not production multi-tenant certification.
- The static gate covers externally supplied route path ids; service-owned ids and explicitly validated body references remain governed by ownership triggers and application validators.
- Visual browser Session acceptance remains to be rerun when the browser runtime is available.
