# E2 Task Card — Bounded Self-Learning Importance

> Status: IMPLEMENTED_AND_VERIFIED

## Outcome

Adapt future Highlight ranking from controlled clinician/staff interactions without learning clinical truth or using PHI/raw text as a feature.

## Permanent contract

- Learning key is same-clinic controlled entity_type; other is metadata-only.
- Clinician signals: accepted +1, pinned +2, rejected -1.
- Staff signals are bounded and never set clinician confirmation.
- Only the latest actor/highlight signal contributes.
- Adaptive adjustment is capped to [-2, +3].
- Only a successful status CAS on an eligible exact-provenance AI Highlight records feedback.
- Risk, unresolved Task, clinician-confirmed, pinned, and needs-review protections block negative learning.
- Glance reads precomputed scores and never reads feedback history or calls a Provider.

## Non-claims

This is deterministic interaction weighting, not clinical learning, model training, preference generalization, or real-clinician validation.

## Exit evidence

The 18-case synthetic evaluation, strict provenance/eligibility tests, clinic isolation, caps/protections, migration, performance, security, and full regressions pass.
