# C1 Task Card — Encounter and Manual Doctor Consult Backend

> Status: COMPLETE

## Outcome

Create a clinician-only Doctor Consult endpoint that opens a new real-world Event, stores an immutable reviewed transcript first, then reuses the existing redaction/LLM/fallback/provenance pipeline.

## Permanent contract

- New Consult never writes into a seeded Event.
- Event.encounter_id is optional; date alone never groups Events.
- Manual transcript indexes are continuous and speakers are doctor or patient only.
- Unknown speakers, empty text, invented timestamps, and extra fields fail closed.
- Transcript is system-authored immutable raw source.
- AI Doctor Summary is separate from clinician assessment/plan.
- Replay uses stable consult identity and conflicting payloads return 409.

## Exit evidence

Creation, raw-first failure retention, idempotency, RBAC, encounter grouping, exact provenance, fallback, and regression tests pass.
