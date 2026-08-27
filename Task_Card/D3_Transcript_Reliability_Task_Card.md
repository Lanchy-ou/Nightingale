# D3 Task Card — Transcript Reliability

> Status: COMPLETE AND FROZEN

## Outcome

Normalize untrusted manual transcript text into a reviewed canonical doctor/patient transcript without LLM use or persistence at preview time.

## Permanent contract

- Normalize is deterministic and non-persistent.
- Outcomes are ACCEPT, NEEDS_REVIEW, or REJECT.
- Unknown, third-party, ambiguous, unlabeled, empty, or over-limit input fails closed.
- Speaker is never silently invented.
- Character ranges are exact and non-BMP safe.
- Only user-reviewed continuous doctor/patient segments may be confirmed.
- Confirmation stores immutable raw Transcript first, then uses the existing AI pipeline.

## Frozen evaluation

- 40 synthetic cases: 26 development and 14 frozen holdout.
- 40/40 manifest hashes and the frozen holdout digest are verified.
- Silent speaker invention, silent truncation, redaction miss, and unanchored fallback candidate hard gates are zero.
- The frozen runner makes no network call; live Provider layer is NOT_RUN.
- Deterministic fallback metrics are reported separately.

## Exit evidence

Corpus validation, runtime evaluator, normalization/limits/range tests, confirm-flow integration, frontend review flow, and full regression pass.
