# F_A4 Task Card — Log and Operational Privacy Boundary

> Official scenario: 3
> Priority: A
> Status: `IMPLEMENTED_WITH_LIMITS` — owner-approved v1 (2026-09-02), hardened through review rev 3. Evidence: `docs/fa4_log_privacy_evidence_2026-09-02.md` and `docs/fa4_log_privacy_boundary_design_gate_2026-09-02.md`.

## Outcome

Prove what sensitive data can and cannot leave through application, edge, exception, audit, crash/monitoring, and Provider-side paths, and define retention/deletion boundaries without treating empty test logs as production evidence.

## Current verified baseline

- Generic validation/500 responses avoid rejected bodies and exception text.
- Application-owned exception logs use error type/path metadata rather than raw exception messages.
- Audit rows are designed as metadata-only.
- The documented secure-demo topology disables Uvicorn and Caddy access logs.
- Synthetic tests cover application error sanitization and an offline Caddy-upstream failure.
- No production log corpus, retention/deletion implementation, third-party crash dashboard, or Provider-retention audit is established.

## Discussion gates

1. Inventory every owned and third-party sink, including storage location and operator access.
2. Approve an allowlisted operational-log schema and identify fields that remain sensitive even without note text.
3. Separate operational-log retention from encrypted clinical AuditLog retention.
4. Decide whether access logging remains disabled or uses an approved minimal format.
5. Decide the product stance for crash monitoring and external Provider retention; absence and external policy are not code-verified controls.
6. Approve retention/deletion periods rather than inventing durations.

## Minimum candidate design to challenge

- Use structured allowlist logging; never log request/response bodies, transcript/messages, Provider payloads, credentials/tokens, or exception text.
- Prefer route templates/request IDs/error codes/latency over raw paths and identifiers.
- Keep a final synthetic scrubber as defense in depth, not the primary permission to log unsafe values.
- Run synthetic sentinel journeys through real application and edge error paths, then scan every actual generated sink.
- Record third-party/Provider evidence separately as verified configuration, external policy, or `NOT_ESTABLISHED`.

## Failure-first evidence

Exercise synthetic name, IC/ID, phone, token, patient message, and Provider-payload sentinels through validation errors, 404, unhandled 500, Provider failure/invalid output, ASR failure, and Caddy upstream failure. Demonstrate the current gaps in real generated logs and retention evidence.

## Exit gate

- A complete sink/data/retention/access inventory exists.
- Approved application-owned sinks remain sentinel-free after real synthetic error journeys.
- Access-log behavior and exception sanitization are executable, not documentation-only.
- AuditLog and operational logs have distinct content and retention contracts.
- Retention/deletion behavior is implemented or explicitly marked not implemented.
- Third-party crash/Provider retention remains separately classified and is never inferred from local tests.

## Non-goals

No claim of regulatory compliance, production monitoring certification, Provider-side deletion guarantee, or successful audit based only on empty local logs.
