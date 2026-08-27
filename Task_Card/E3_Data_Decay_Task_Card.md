# E3 Task Card — Protection-First Data Decay

> Status: IMPLEMENTED_AND_VERIFIED

## Outcome

Add a deterministic maintenance-only storage policy and verified compressed shadow payload without deleting authoritative clinical content.

## Permanent contract

- Policy version is decay-v1.
- Hot/warm/cold is derived from transparent protection and age rules.
- Authoritative Artifact.content is never removed or overwritten.
- Cold storage uses a zlib-json-v1 shadow payload with source SHA-256 and round-trip verification.
- Clinician-confirmed, risk, unresolved Task, needs-review, recent, and protected artifact types cannot decay unsafely.
- Highlight final score remains base + adaptive + decay.
- Restored content must preserve exact provenance.
- Voice recording BLOBs stay outside E3 compression.
- Apply is idempotent and maintenance-only; read paths do not compute policy.

## Non-claims

The evidence is local synthetic maintenance timing and one shadow compression result. It is not total database savings, production retention, clinical forgetting, or a deletion policy.

## Exit evidence

Policy, idempotency, archive round-trip, provenance, Voice integration, SQLCipher backup/restore, performance, and full regressions pass.
