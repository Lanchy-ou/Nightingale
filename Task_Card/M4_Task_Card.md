# M4 Task Card — AI Pipeline, Redaction, and Deterministic Prioritization

> Status: COMPLETE

## Outcome

Create one redacted Provider pipeline for consult/session summaries and exact candidate Highlights.

## Permanent contract

- LLMClient is the only Provider exit.
- Supported Providers are mock and DeepSeek; failures use deterministic_fallback.
- Redaction for names, IDs, and phones runs before egress.
- Provider quotes are restored locally and exact-matched against raw source.
- Invalid schema, altered placeholders, or poor anchoring fails closed.
- AI summaries are system-authored and never overwrite clinician/staff artifacts.
- Conflict checks compare bounded entities against clinician notes.
- Ranking remains deterministic; Provider output is not authority.

## Exit evidence

Raw-first ingestion, redaction, Provider/fallback, exact anchoring, conflict, and no-LLM read-path tests pass.
