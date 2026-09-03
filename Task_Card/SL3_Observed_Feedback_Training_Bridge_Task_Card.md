# SL3 Task Card — Observed Feedback Training Bridge

> Phase: Self-Learning Stage 3
> Status: IMPLEMENTED_WITH_LIMITS — bridge complete; real clinician evidence unavailable
> Owner authorization: 2026-09-03 in current thread
> Serving mode: permanently `base_only` in this card
> Real clinician evidence: `NOT_RUN` / unavailable

## 1. Outcome

Connect already-persisted, controlled workflow feedback to a content-free,
versioned pairwise dataset and offline Shadow-training interface without
claiming real-clinician validation or promoting a model into formal Glance.

```text
RankingRun + RankingDecision + explicit outcome labels
  -> automatic feature extraction
  -> same-run / same-role / same-band pair compiler
  -> versioned content-free dataset manifest
  -> explicit offline training command
  -> held-out Shadow mechanism report
```

## 2. Frozen safety decisions

- Use only explicit `outcome_label` signals. Never infer preference from clicks,
  dwell time, absence of feedback, AI output, or an unreviewed candidate.
- Pair labels only when two eligible, non-protected decisions belong to the
  same run, viewer role, priority band and reviewer.
- Accept only current or not-applicable source bindings and the frozen
  `attention-feature-v1` / 18-feature projection.
- Keep raw patient text, Highlight text, actor ids, clinic ids, patient ids,
  decision ids and workflow ids out of exported training rows.
- Split by complete reviewer/run/band group; never split pairs from one group
  across train, validation and test.
- Dataset extraction is automatic and read-only. Training is an explicit local
  operator action, never a page-load side effect or online update.
- Training requires an explicit evidence classification:
  `synthetic_mechanism` or `authorized_real_feedback`. Unverified application
  data fails closed.
- `authorized_real_feedback` is a provenance declaration, not proof of consent,
  clinical validity or sufficient sample size.
- No model from this card can modify eligibility, priority bands, hard
  protection, provenance, `GlanceProjection`, `adaptive_adjustment`, or formal
  Glance ordering.

## 3. Readiness reporting

For each role report:

- labelled decisions;
- independent reviewers;
- eligible pair groups;
- strict and tie pairs by split;
- excluded label counts and reason codes;
- whether the offline mechanism minimum is met.

The initial engineering minimum is 12 strict pairs, 6 complete pair groups,
2 reviewers and at least one strict pair in train, validation and test. This is
only a mechanism/data-integrity gate and is not a clinical validation threshold.

## 4. Interface

- `app/observed_feedback.py`: compiler, manifest, validation, offline training
  artifact and held-out Shadow report.
- Admin learning status: read-only observed-feedback readiness for staff and
  clinician scopes.
- `scripts/train_observed_feedback.py`: explicit local command requiring clinic,
  role, evidence classification and output directory.
- No browser control trains, approves or serves a model.

## 5. Exit gate

- Failure-first tests demonstrate the bridge is absent before implementation.
- Feature extraction and group splitting are deterministic and content-free.
- Cross-clinic, cross-role, cross-band, protected, excluded and invalid-source
  records never enter a pair.
- Re-running compilation and training yields byte-identical artifacts.
- Unverified data and insufficient samples fail without emitting a model.
- Synthetic tests exercise the complete compile/train/evaluate mechanism.
- Admin status truthfully reports that real clinician validation is `NOT_RUN`.
- Existing SL1/SL2, Glance, RBAC and full regression suites remain green.
- Formal Glance remains byte/order equivalent before and after any Shadow work.

## 6. Explicit non-goals

No real clinician recruitment, consent workflow, automatic retraining,
production scheduler, online learning, click optimization, model serving,
clinical calibration, deployment, external Provider/Voice validation, external
notification, PostgreSQL work, penetration test, or production-readiness claim.

## 7. Completion record — 2026-09-03

- Application `RankingRun` / `RankingDecision` / explicit `outcome_label`
  records now compile automatically into a deterministic, content-free
  pairwise dataset.
- The compiler enforces same clinic, run, reviewer, role and priority band;
  excluded, protected, invalid-source and invalid-feature rows fail closed.
- The explicit local training command requires an evidence classification and
  emits no model when the dataset is insufficient.
- Synthetic mechanism tests exercise deterministic compile, training,
  artifact hashing, held-out evaluation, scope binding and Shadow replay.
- The current seeded database truthfully produces zero eligible observed pairs
  and `training_blocked`; no model is fabricated.
- Admin status reports automatic extraction, manual-only training,
  `real_clinician_validation=NOT_RUN` and per-role readiness.
- Formal Glance remains `base_only`; no serving approval or promotion exists.

Detailed evidence: `docs/sl3_observed_feedback_training_bridge_evidence_2026-09-03.md`.
