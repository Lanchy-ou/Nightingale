# D4 Task Card — Evidence-Bound Clinician Copilot

> Status: COMPLETE AND RE-VERIFIED

## Outcome

Provide a clinician-only assistant that retrieves exact record evidence and prepares editable drafts without direct clinical authoring authority.

## Permanent contract

- Query is clinician-only and clinic-scoped.
- The server selects patient, Event, evidence cards, draft type, visibility, and write path.
- Every supported fact resolves to Event → raw Artifact → exact Span.
- AI Summary self-citation is rejected.
- Comparison is explicitly labelled inference.
- Unknown remains unknown.
- Provider output cannot select an endpoint, author, Task status, or permission.
- Draft confirmation requires a short-lived HMAC token binding actor/scope/Event/type/evidence/template.
- The clinician must edit and confirm; Copilot never writes directly.

## Frozen evidence

Four frozen questions cover change, current priorities, historical evidence, and a draft. Mock Provider evaluation passes; live Provider is not implied.

## Exit evidence

RBAC, evidence resolution, injection resistance, forged/expired token rejection, state isolation, frontend Context tools, and full regressions pass.
