# SL2 Shadow Pairwise Linear Ranking — Completion Evidence

Date: 2026-09-03

Policy: `sl2-pairwise-linear-v1`

Serving mode: `base_only`
Result: `IMPLEMENTED_WITH_LIMITS`

## Delivered mechanism

- Frozen 30-scenario synthetic dataset: 15 staff and 15 clinician groups,
  with 9 train / 3 validation / 3 test groups per role.
- Exactly 180 strict pairs and 30 evaluation-only TIE pairs.
- Exact 18-feature whitelist over workflow/state metadata; text, identities,
  serving outputs and feedback leakage fields are not model inputs.
- Two independent standard-library pairwise linear logistic rankers using the
  frozen optimizer and rounded 12-decimal weights.
- Canonical, byte-reproducible role artifacts with complete dataset, feature,
  label, optimizer and code-contract lineage.
- Shadow-only inference that preserves deterministic eligibility, priority
  bands and hard protection, and atomically falls back to base ordering on a
  controlled validation failure.
- Admin artifact/evaluation evidence, policy activation, replay, freeze/resume
  and rollback; Coverage Review labels learned ranks as simulation only.
- Formal Glance remains deterministic `base_only` and does not query or load
  SL2 training state.

## Frozen lineage

| Item | SHA-256 |
| --- | --- |
| Feature schema | `0560cea19b6cdac9f6005cc589b7f8392facd8195085cff19016753a649818bf` |
| Gold order | `9f93bf185d37f8491b03218e0f09339b29547f28c6dd701b5e2c1e2ac25fcedb` |
| Dataset manifest | `f07d31b585e0e55d2c9859ce3f8012bacfdefb3d9dfbe9bd0d61e592adb27177` |
| Staff artifact | `e918b179e94c499de03bc716686b2dc0c51611be2c3ae0b81f113d13bbb7f1fc` |
| Clinician artifact | `1baf5e17092ec2aff6a30b6209926dfd7f7d345c9eef7a512dd3f52ea40ffca1` |

## Frozen evaluation result

| Metric | Result | Gate |
| --- | ---: | ---: |
| Test strict-pair accuracy, overall | 1.000 | >= 0.85 |
| Test strict-pair accuracy, staff | 1.000 | >= 0.80 |
| Test strict-pair accuracy, clinician | 1.000 | >= 0.80 |
| Test TIE accuracy, overall | 1.000 | >= 0.70 |
| Test gold Top-5 recall, overall | 1.000 | >= 0.80 |
| Test strict-pair improvement over base | 0.222 | >= 0.10 |
| Absolute train-test gap, staff | 0.037 | <= 0.15 |
| Absolute train-test gap, clinician | 0.056 | <= 0.15 |
| Protection / eligibility / band / invalid-score violations | 0 | 0 |
| Deterministic replay/hash mismatch | 0 | 0 |

All frozen mechanism thresholds pass. This does not authorize serving
promotion.

## Review findings and limits

- Staff validation strict-pair accuracy is **0.333**, with an absolute
  train-validation gap of **0.630**. This is below the staff test result and is
  retained as a visible generalization warning. The frozen task card did not
  define a validation-accuracy gate, so the mechanism gate passes with this
  limitation rather than hiding or post-hoc tuning it.
- Every frozen scenario contains exactly five candidates, so gold Top-5 recall
  is structurally 1.0 and has no discriminating power in this dataset. Strict
  pair accuracy and ordered exact-match provide the useful ordering evidence.
- The frozen scenarios intentionally place all five items in the same workflow,
  producing a duplicate-workflow rate of 0.8. SL2 reports this concentration
  but does not diversify or suppress candidates.
- In the canonical Alice Tan browser journey, the eligible artifact-highlight
  candidates share the same learned score, so the complete base tie-break keeps
  their relative order. This is a truthful zero-shift live replay, not evidence
  of real clinical preference.
- Evidence is synthetic mechanism evidence only. No real clinician preference,
  clinical usefulness, safety certification or outcome benefit is claimed.

## Verification

- Failure-first baseline: all eight required SL2 modules initially failed at
  collection because no dataset/ranker implementation existed.
- Focused SL2 suite: 21 tests passed.
- Full backend suite: 692 tests collected; 690 passed and 2 environment-related
  tests skipped.
- Frontend production build: passed (`tsc -b` and Vite production build).
- Normal-session browser journeys:
  - Admin displayed hashes, frozen counts, PASS checks and the 0.333 staff
    validation limitation;
  - activation, offline replay, freeze/resume and rollback worked;
  - clinician and staff Coverage Review used their role-specific artifacts;
  - excluded and protected items displayed `base-preserved` and received no
    model score;
  - formal clinician Glance contained the same five items in the same order
    before and after SL2 activation;
  - browser console reported no warnings or errors.

## Final boundary

SL2 remains Shadow-only. It adds no database table, external ML dependency,
Provider call, record mutation, learned eligibility, learned safety override or
formal Glance serving path.
