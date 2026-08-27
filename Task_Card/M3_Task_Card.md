# M3 Task Card — Collaboration, Revision, RBAC, and Concurrency

> Status: COMPLETE

## Outcome

Add server-enforced role boundaries, comments, version history, revert, audit metadata, and deterministic conflict handling.

## Permanent contract

- Authorization is centralized in backend/app/authz.py.
- Cross-clinic and not-own-patient resources use a uniform 404.
- Editable notes use full version snapshots.
- Revert creates a new version; history is immutable.
- Different role-owned sections do not overwrite one another.
- Same-section stale writes return 409 through compare-and-swap.
- Comments remain collaboration, not clinical authority.
- Audit records metadata only.

## Exit evidence

RBAC, revision, concurrency, comment, audit, and provenance tests pass for patient, staff, clinician, and admin boundaries.
