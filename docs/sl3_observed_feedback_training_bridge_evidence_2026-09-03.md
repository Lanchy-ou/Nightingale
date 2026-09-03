# SL3 Observed Feedback Training Bridge — Evidence

Date: 2026-09-03

Status: `IMPLEMENTED_WITH_LIMITS`

Serving: permanently `base_only` in SL3

Real clinician evidence: `NOT_RUN` / unavailable

## Delivered path

```text
RankingRun + RankingDecision + explicit outcome_label
  -> automatic content-free feature extraction
  -> same reviewer/run/role/band pair compiler
  -> deterministic grouped train/validation/test split
  -> explicit offline training command
  -> immutable Shadow artifact + held-out mechanism report
```

The compiler never treats clicks, dwell time, missing feedback, AI output or an
unreviewed item as a ranking label. Exported rows contain hashes and the frozen
18-feature vectors, not clinical text or raw clinic, patient, actor, decision,
Highlight or workflow identifiers.

## Safety and scope

- Only latest explicit `outcome_label` values `0..3` with reason
  `attention_label_v1` are considered.
- Both decisions must be eligible, non-protected, source-current or
  source-not-applicable, and in the same reviewer/run/role/priority band.
- Complete pair groups stay in one deterministic split.
- Training requires explicit `synthetic_mechanism` or
  `authorized_real_feedback` classification. The latter additionally requires
  an operator confirmation flag and is not claimed in this evidence.
- Artifacts are bound to role, feature schema, dataset hash and scope hash.
- Any artifact, role, schema, hash, scope or score failure falls back to base
  ordering for Shadow replay.
- No API or browser control trains, schedules, approves or serves a model.

## Current-data result

The isolated seeded application database produced:

- strict observed pairs: `0`;
- train/validation/test strict pairs: `0 / 0 / 0`;
- mechanism readiness: `false`;
- output: content-free dataset only;
- model artifact: **not emitted**;
- result: `training_blocked` with explicit insufficient-data reasons.

This is the expected result because no real clinician feedback is available.

## Synthetic mechanism validation

The existing frozen clinician scenarios were routed through the new bridge only
as synthetic mechanism input:

- byte-reproducible artifact hash:
  `5ce62a5fbb0140aab0f4ce8908af3f938367452b4bda4718313c2399cf3c9106`;
- train strict accuracy: `0.944`;
- validation strict accuracy: `1.000`;
- test strict accuracy: `1.000`;
- test TIE accuracy: `1.000`;
- protection, eligibility and priority-band changes: `0`.

These results prove interface mechanics only and add no new clinical-validity
evidence beyond SL2.

## Verification

- Failure-first collection failed because `app.observed_feedback` did not exist.
- Focused SL3 tests cover deterministic compilation, privacy, clinic/role/band
  boundaries, protected and invalid-source exclusion, evidence classification,
  reproducible training, scope-bound artifacts, atomic fallback and Admin RBAC.
- Existing SL2 artifact validation and Shadow tests remain green after sharing
  the frozen optimizer.
- The local CLI was run against an isolated seeded database and refused to emit
  a model because readiness was not met.
- Focused SL2/SL3 regression: `30 passed`.
- Full backend regression: `702 collected`, `700 passed`, `2 skipped`; both
  skips require ignored real-local-ASR model/audio inputs and are not reported
  as passes.
- Frontend TypeScript/Vite production build: passed, `65 modules transformed`.
- Normal server-session Admin browser journey: passed. The page showed
  automatic extraction, manual-only training, `NOT_RUN` real-clinician
  validation, zero eligible staff/clinician pairs, explicit blocking, and
  `Serving: base-only`; no browser warning/error was recorded.
- `git diff --check` and Python compilation: passed.

## Non-claims

No real clinician recruitment, consent, clinical calibration, real-feedback
accuracy, automatic retraining, model serving, production scheduler or patient
outcome benefit is claimed.
