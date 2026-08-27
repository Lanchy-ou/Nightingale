# D2 Task Card — Care Tasks and Patient Experience

> Status: COMPLETE AND RE-VERIFIED

## Outcome

Add first-class care Tasks and an action-first Patient Experience while preserving clinician authority.

## Permanent contract

- Task states: open, in_progress, reported_done, completed, cancelled.
- Patients may Start or Report done only on their own visible assigned Tasks.
- reported_done always waits for clinic confirmation.
- Staff/clinicians verify completion or cancel within clinic scope.
- Every Task has an origin Event and may carry an explicitly selected exact Artifact/Span source.
- Task-to-Highlight mapping is explicit, FK/unique constrained, and concurrency-safe.
- Rejected Highlights cannot be adopted.
- Patient APIs expose an exact safe field allowlist.

## Exit evidence

Lifecycle, provenance, RBAC, Glance mapping, concurrent adoption, patient projection, frontend journeys, and full regressions pass.
