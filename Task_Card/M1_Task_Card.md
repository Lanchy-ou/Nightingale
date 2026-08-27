# M1 Task Card — Skeleton and Canonical Data Model

> Status: COMPLETE

## Outcome

Create the FastAPI/SQLAlchemy/React skeleton and the canonical synthetic longitudinal fixture.

## Permanent contract

- One connected patient record; no role-specific data silos.
- Event is the Timeline unit.
- Artifacts are parallel representations and never overwrite one another.
- Span is an exact JSON source pointer.
- Canonical model: Patient → Event → Artifact → Span.
- AI artifacts use author_role system and remain distinct from human notes.
- Synthetic fixture is the single source of truth.

## Exit evidence

The schema supports multiple dated Events and Artifacts for one patient, source links resolve, the seed is repeatable, and the initial read API/tests pass.
