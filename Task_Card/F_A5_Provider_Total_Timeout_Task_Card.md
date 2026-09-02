# F_A5 Task Card — Explicit Provider Total Timeout

> Official scenario: 8
> Priority: A
> Status: DESIGN_GATE — implementation is not authorized until owner approval

## Outcome

Bound the complete time a clinician or patient waits for a Provider that never returns, while preserving the already-committed raw source and entering the correct clearly labelled fallback/unavailable behavior.

## Current verified baseline

- Raw consult and Check-in sources are persisted before derived Provider work.
- Returning Provider errors, invalid output, and ordinary exceptions enter existing fallback/unavailable paths.
- DeepSeek adapter does not configure an explicit application-owned total deadline.
- A hung request can leave the UI in processing even though the raw source is safe.

## Discussion gates

1. Approve total wait expectations for Consult, Check-in, Copilot, and key verification separately or as one shared policy.
2. Decide connect/read/write/pool timeouts, retry count, and total deadline so retries cannot silently exceed the user-facing bound.
3. Approve timeout-specific behavior and copy for each product flow.
4. Decide whether timeout configuration is fixed, device-level, or environment-owned; do not add unnecessary configurability.

No timeout number is approved by this card.

## Minimum candidate design to challenge

- Build Provider clients through one shared factory with explicit bounded network timeouts and retries.
- Introduce a distinct timeout classification such as `provider_timeout`, not a generic provider error.
- Consult/Check-in derived work may use the existing deterministic fallback; Copilot must remain unavailable rather than inventing an uncited answer; key verification must fail without saving an unverified key.
- UI must state that the raw source was saved and whether deterministic fallback was used.
- Retry must reuse the existing idempotency identity and never create a second Event/source.

Do not use a frontend timer or a cancellation wrapper that leaves a synchronous Provider call running as the only timeout control.

## Failure-first evidence

- A fake Provider accepts the request and never returns or blocks beyond the approved deadline.
- The current endpoint exceeds the intended bound before implementation.
- The raw Event/source remains committed during the failure.

## Exit gate

- Every Provider entry is covered by the approved total-wait policy.
- A never-returning Provider produces a response within the approved deadline plus test tolerance.
- Raw source persists exactly once; retry produces no duplicate Event/Artifact.
- Timeout has a distinct metadata reason and leaks no clinical content to logs.
- Consult/Check-in fallback and Copilot/key-verification unavailable behavior match their approved contracts.
- Frontend production flow clearly separates saved raw source, timeout, and fallback/unavailable result.

## Non-goals

No Provider SLA claim, background-job architecture rewrite, unlimited retries, fake success, or proof based only on an immediate 503/error response.
