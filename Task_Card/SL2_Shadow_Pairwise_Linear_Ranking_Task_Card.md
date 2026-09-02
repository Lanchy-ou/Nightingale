# SL2 Task Card — Workflow-Aware Shadow Pairwise Linear Ranking

> Phase: Self-Learning Stage 2
> Status: COMPLETE — implemented and comprehensively reviewed 2026-09-03
> Hard dependency: SL1 Exit Gate must pass first
> Training data: frozen synthetic workflow scenarios only
> Model family: role-specific pairwise linear logistic ranker
> Policy version: `sl2-pairwise-linear-v1`
> Serving mode: permanently `base_only` in SL2

## 1. Outcome

Train and evaluate the smallest explainable ranking model that can learn
predeclared workflow-attention preferences from synthetic scenarios without
changing scope, eligibility, safety bands, clinical records or formal Glance.

The complete SL2 path is:

```text
SL1 attention-feature-v1 snapshots
        + frozen same-role/same-band synthetic order labels
        -> pairwise training examples
        -> staff linear ranker + clinician linear ranker
        -> immutable model artifacts
        -> Shadow-only within-band ranking
        -> deterministic base-vs-Shadow replay
```

SL2 proves that the controlled learning mechanism works. It does not prove
real clinician preference, medical validity or patient-outcome improvement.

## 2. Frozen decisions

No further product choice is open inside SL2:

- train two independent models: one for `staff` (Nurse) and one for
  `clinician`;
- train a pairwise linear logistic ranker, not absolute score regression;
- train only on frozen synthetic workflow labels;
- compare candidates only within the same ranking impression, role and priority
  band;
- apply the learned score only to eligible, non-hard-protected candidates;
- keep eligibility, role routing, active-frontier logic, priority bands,
  provenance and safety protection deterministic;
- keep formal Glance on the existing A2 `base_only` ordering;
- run learned ordering only through existing F_A1 Shadow replay;
- use no free text, embeddings, Provider output, click/dwell signal or
  individual-user personalization;
- add no new database table and no external ML dependency;
- do not add diversity suppression or set-level reranking in SL2.

## 3. Training objective

For two eligible AttentionItems `A` and `B` observed under the same:

```text
clinic
patient
workflow-state snapshot
viewer role
priority band
as_of
```

learn whether:

```text
A > B
B > A
A = B
```

The ranker learns a role-specific linear score:

```text
score_role(x) = w_role · x
```

For a strict pair, it learns:

```text
P(A > B) = sigmoid(w_role · (x_A - x_B))
```

The model objective is workflow attention ordering inside a fixed band. It is
not trained to decide:

- whether an item is visible to a role;
- whether an item is medically serious;
- whether an item is P0/critical;
- whether a Task should be created, assigned, verified or completed;
- whether one priority band may outrank another.

## 4. Synthetic label contract

### 4.1 Meaning of a label

A synthetic label is a predeclared expected ordering for a hand-written
workflow snapshot. It expresses a product/workflow hypothesis such as:

```text
an explicit downstream blocker should precede an otherwise comparable
non-blocking task
```

It never means:

```text
this disease is more dangerous
this is what a real clinician would choose
this ordering improves a clinical outcome
```

### 4.2 Gold ordering format

Every labelled item receives a manually frozen `gold_rank_group`:

```text
1 = should appear before group 2
2 = should appear before group 3
same group = TIE
```

The manifest stores:

```text
label_schema = sl2-gold-order-v1
scenario_group_id
snapshot_id
split = train | validation | test
viewer_role = staff | clinician
priority_band
candidate_independence_key
gold_rank_group
reason_code
feature_schema_hash
```

The compiler creates pair labels from the frozen gold groups; it never reads
base score, base rank, Shadow score or displayed position when producing gold
labels.

For Top-5 evaluation, the synthetic gold order keeps deterministic priority
bands unchanged, applies `gold_rank_group` only within each band, and resolves
gold TIE groups with the existing base tie-break. No TIE group may cross the
fifth-position boundary. The first five items in that frozen order are
`gold_top5`.

### 4.3 Allowed label reasons

Only these workflow reasons are allowed:

```text
explicit_downstream_blocker_first
closer_due_first_when_other_context_equal
longer_wait_first_when_no_due
explicit_decision_before_equivalent_execution
reported_done_verification_before_routine_open_task
updated_upstream_verification_before_unchanged_context
more_open_downstream_obligations_first
equivalent_workflow_state_tie
```

No medical condition, symptom name, inferred severity, clinician identity or
free-text rationale may become a label reason.

### 4.4 Pair eligibility

A training/evaluation pair is valid only when both items:

- are in the same frozen snapshot;
- have the same `viewer_role`;
- have the same deterministic `priority_band`;
- are eligible and on the active workflow frontier;
- are not hard-protected;
- have different `independence_key` values;
- have valid `attention-feature-v1` schema hashes;
- have no failed or mismatched source binding when exact provenance applies.

Pairs across roles, bands, clinics, patients or dataset splits fail closed.

## 5. Frozen synthetic dataset

### 5.1 Size and split

The dataset contains exactly 30 independent `scenario_group_id` values:

```text
15 staff-focused workflow scenarios
15 clinician-focused workflow scenarios
```

The split is fixed before training:

| Split | Staff groups | Clinician groups | Total groups |
| --- | ---: | ---: | ---: |
| train | 9 | 9 | 18 |
| validation | 3 | 3 | 6 |
| test | 3 | 3 | 6 |

Every scenario contributes exactly six strict pair labels and one TIE label:

```text
train:      108 strict + 18 TIE
validation:  36 strict +  6 TIE
test:        36 strict +  6 TIE
total:      180 strict + 30 TIE
```

All snapshots and transitions from the same workflow scenario stay in the same
split. No pair-level random split is allowed.

### 5.2 Scenario coverage

The 30 groups collectively cover:

- Nurse verification before and after `verified`, `corrected` and
  `unable_to_verify` outcomes;
- clinician priority review before and after Nurse verification context;
- explicit `requires_action`, `depends_on`, `follow_up_for` and
  `superseded_by` relationships;
- ordinary Tasks assigned to staff and clinician;
- patient-visible Task in `reported_done` awaiting formal verification;
- known and unknown due time;
- approaching due time and overdue duration inside their fixed bands;
- explicit workflow blocker versus non-blocker;
- different numbers of unresolved downstream obligations;
- equivalent workflow states producing TIE;
- unrelated workflow controls;
- clinic-B and patient-B isolation controls.

Medical wording is interchangeable decoration and must not affect labels or
features. The same structural scenario must preserve its label when symptom or
Task display text changes.

### 5.3 Counterfactual balance

Dataset construction must prevent shortcuts:

- preferred items appear on both lexical left and right sides after canonical
  pair orientation;
- candidate ids, workflow ids and creation order do not correlate with label;
- each learnable boolean appears in both positive and negative examples;
- due-time preference examples include controls where blocking/context, not
  deadline, determines the label;
- workflow-context examples include controls where all context is equivalent
  and the expected result is TIE;
- no test scenario is a renamed copy of a training scenario.

## 6. Learnable feature vector

SL2 consumes only the following normalized projection of
`attention-feature-v1`, in this exact order:

```text
due_known
due_proximity_7d
overdue_age_7d
waiting_age_7d
workflow_blocking_known
workflow_blocking_value
open_downstream_action_count_cap3
requires_action_from_viewer
requires_decision_from_viewer
upstream_verification_known
upstream_verified
upstream_corrected
upstream_unable_to_verify
patient_reported_done_pending_verification
attention_kind_care_task
attention_kind_patient_report_review
attention_kind_clinician_priority_review
attention_kind_artifact_highlight
```

Deterministic transforms:

```text
due_proximity_7d = clamp(1 - max(time_to_due_seconds, 0) / 604800, 0, 1)
overdue_age_7d   = clamp(max(-time_to_due_seconds, 0) / 604800, 0, 1)
waiting_age_7d   = clamp(age_seconds / 604800, 0, 1)
open_downstream_action_count_cap3 = min(count, 3) / 3
boolean true/false = 1/0
unknown value = 0 together with its explicit known-mask feature
```

`attention_kind_safety_context` is absent because protected/safety-context
items never enter model training or learned ranking.

### 6.1 Features forbidden from learning

The following remain gates, audit metadata, labels or leakage risks and are not
model inputs:

```text
clinic_id / patient_id / user_id / candidate_id / workflow_id / event_id
independence_key / workflow_group_key
raw or normalized text / Task title / diagnosis / symptom name
embedding / Provider output / source quote / note or comment content
source_authority / clinician identity / specialty
eligible / exclusion_reason / priority_band
hard_protected / explicit_risk / clinician_confirmed / needs_review
base_score / base_rank / Shadow score / displayed position
status feedback / current-item evaluation label / gold rank / future action
click / open / dwell time / evidence expansion
created_at or due_at as raw identifiers
```

Eligibility and priority bands are computed before the model. The model cannot
learn around a hard rule by receiving the hard-rule result as a feature.

## 7. Pairwise model contract

### 7.1 Model structure

Train two separate weight vectors:

```text
w_staff
w_clinician
```

Both use the same ordered feature schema. Labels are never pooled across roles.
No per-clinic or per-user model is trained.

### 7.2 Training algorithm

For every strict pair, orient left/right by lexical
`candidate_independence_key`, then set:

```text
z = x_left - x_right
y = 1 when left is preferred, otherwise 0
```

Minimize full-batch L2-regularized logistic loss independently for each role:

```text
loss = mean(binary_cross_entropy(sigmoid(w · z), y))
       + 0.01 * ||w||^2 / 2
```

Frozen optimizer:

```text
initial weights = all zero
learning rate = 0.05
iterations = 2000
gradient = full batch
randomness = none
exponent input clipped to [-30, 30]
intercept = none
early stopping = none
hyperparameter search = none
```

TIE rows are evaluation-only. A predicted TIE means:

```text
abs(score(A) - score(B)) <= 0.10
```

After iteration 2000, every weight is rounded to 12 decimal places before
canonical serialization and hashing. Shadow inference uses those stored rounded
weights, not the unrounded in-memory values.

The implementation uses Python standard-library arithmetic. SL2 adds neither
scikit-learn nor another ML framework.

### 7.3 Failure behavior

Training fails without emitting an artifact when:

- SL1 schema/version/hash is missing or mismatched;
- a label pair violates pair eligibility;
- a split leaks one `scenario_group_id` across partitions;
- a feature contains NaN/infinity or an unregistered field;
- either role lacks the frozen scenario/pair counts;
- loss becomes non-finite;
- the output cannot be reproduced byte-for-byte from the same inputs.

Failure never falls back to training on a different dataset or altered
hyperparameter.

## 8. Model artifact and lineage

Each role artifact is canonical JSON containing:

```text
policy_version
model_type = pairwise_linear_logistic
viewer_role
feature_schema_version
feature_schema_sha256
ordered_feature_names
transform_version = sl2-transform-v1
label_schema_version = sl2-gold-order-v1
dataset_manifest_sha256
train/validation/test scenario ids
hyperparameters
weights
training loss
validation metrics
test metrics
code_contract_version
artifact_sha256
```

Wall-clock timestamps are stored only in AuditLog/LearningEvaluation metadata,
not inside the canonical artifact hash. Identical code, manifest and data must
produce byte-identical model artifacts.

Version naming:

```text
sl2-pairwise-linear-v1-{role}-{dataset_hash_8}
```

The dataset manifest, label manifest, feature schema and model artifacts are
repository-local synthetic evidence. No external dataset is downloaded.

## 9. Shadow inference and ordering

### 9.1 Scope

The learned model runs only during offline/Admin Shadow replay. It is never
called by Glance GET and never changes stored serving
`adaptive_adjustment = 0`.

For every role-specific RankingRun:

1. retain the deterministic eligibility result;
2. retain the deterministic priority band;
3. retain base ordering for excluded or hard-protected candidates;
4. transform eligible non-protected candidates through the matching role
   artifact;
5. order within each unchanged band by learned score descending;
6. use the complete existing base sort key as deterministic fallback for equal
   learned scores;
7. store Shadow score/rank/inclusion without changing GlanceProjection or
   Highlight serving fields.

### 9.2 Fail-closed fallback

Any missing artifact, wrong role, schema mismatch, hash mismatch, unknown
feature, non-finite score or unsupported policy causes that replay to use base
ordering and record one controlled reason code:

```text
model_artifact_missing
model_role_mismatch
feature_schema_mismatch
artifact_hash_mismatch
unknown_feature
non_finite_score
unsupported_shadow_policy
```

No partial learned ordering is allowed inside one role-specific run.

### 9.3 Workflow concentration

`workflow_group_key` remains evaluation metadata. SL2 reports how many Top-5
positions come from the same workflow, but it does not suppress or diversify
items. Pairwise per-item scoring cannot safely decide whether two active steps
are redundant. Diversity-aware set selection requires a later separate design.

## 10. Evaluation contract

Evaluation is performed on the frozen validation and untouched test groups.
Metrics are reported overall and separately for `staff` and `clinician`.

Required metrics:

```text
strict_pair_accuracy
tie_accuracy
gold_top5_recall
ordered_top5_exact_match_rate
base_vs_shadow_top5_overlap
rank_shift_count
duplicate_workflow_rate
train_validation_accuracy_gap
train_test_accuracy_gap
protection_violation_count
eligibility_change_count
priority_band_change_count
invalid_or_nonfinite_score_count
```

The frozen mechanism thresholds are:

```text
test strict_pair_accuracy overall >= 0.85
test strict_pair_accuracy per role >= 0.80
test tie_accuracy overall >= 0.70
test gold_top5_recall overall >= 0.80
test gold_top5_recall per role >= 0.75
Shadow strict-pair improvement over base on test >= 0.10
absolute train-test strict-pair gap <= 0.15
protection violations = 0
eligibility changes = 0
priority-band changes = 0
invalid/non-finite scores = 0
deterministic replay/hash mismatch = 0
```

Failure of any threshold is a truthful negative result. The dataset, split,
labels, features, hyperparameters and thresholds must not be changed after test
results are observed. A new attempt requires a separately versioned SL2.x task
card and dataset.

Passing all thresholds still does not authorize serving promotion.

## 11. Admin and Coverage Review behavior

- Add `sl2-pairwise-linear-v1` as an approved Shadow policy only.
- Admin Shadow Learning displays role artifact versions, schema/dataset hashes,
  frozen split counts, latest evaluation and pass/fail reasons.
- Admin may select the SL2 policy for replay, freeze it, resume replay or roll
  back to existing `no-adjustment-v1` / `legacy-e2-v1` Shadow policies.
- No browser control trains or edits a model, label, feature or threshold.
- Coverage Review continues to display formal base Top 5, eligible unsurfaced
  and excluded candidates; optional Shadow rank is clearly labelled
  “simulation only.”
- Nurse and clinician cannot activate a policy or inspect another clinic's
  learning state.

## 12. Implementation surface

Expected minimal changes:

```text
backend/app/sl2_dataset.py
backend/app/pairwise_ranking.py
backend/scripts/train_sl2_pairwise.py
backend/evals/sl2/dataset_manifest_v1.json
backend/evals/sl2/gold_order_v1.json
backend/evals/sl2/feature_schema_v1.json
backend/training_artifacts/sl2/*.json
```

Update only:

- `backend/app/shadow_learning.py` for model-backed Shadow scoring and metrics;
- `backend/app/api/learning.py` and schemas for read/replay status;
- existing Admin/Coverage UI only where needed to show Shadow version and
  evaluation evidence;
- focused tests and documentation.

No database migration is required. Existing `LearningPolicyVersion`,
`LearningEvaluation`, `RankingRun`, `RankingDecision` and `LearningSignal`
remain authoritative.

## 13. Failure-first tests

Add:

```text
backend/tests/test_sl2_dataset_contract.py
backend/tests/test_sl2_feature_whitelist.py
backend/tests/test_sl2_pairwise_training.py
backend/tests/test_sl2_model_artifact.py
backend/tests/test_sl2_shadow_inference.py
backend/tests/test_sl2_workflow_generalization.py
backend/tests/test_sl2_privacy_and_scope.py
backend/tests/test_sl2_serving_isolation.py
```

Before implementation, demonstrate at least:

- current Shadow adjustments do not learn a feature weight vector;
- the repository has no frozen pairwise dataset/split/artifact contract;
- same-workflow transitions can leak across random pair-level splits;
- current replay cannot fail closed on model/schema/hash mismatch;
- current evaluation cannot compare a pairwise model with base ordering;
- no byte-reproducible role-specific artifact exists;
- formal Glance must remain unchanged throughout every failing and passing
  Shadow experiment.

Then implement only the minimum code required by this card.

## 14. Required verification

1. SL1 Exit Gate is recorded as passed before SL2 training begins;
2. focused SL2 tests pass;
3. existing SL1/F_A2/F_A1, workflow, Glance, Task, provenance, RBAC,
   clinic-isolation, privacy and data-decay tests remain green;
4. full backend suite passes with environment-related skips separate;
5. frontend production build passes;
6. training twice from clean inputs produces byte-identical role artifacts;
7. reversing ids, display text and pair orientation does not change gold truth
   or learned preference;
8. a renamed symptom/Task narrative produces the same feature vector and score;
9. workflow transitions stay in one dataset split and role labels never mix;
10. protected, cross-band, excluded and invalid-provenance pairs never train;
11. base-vs-Shadow replay meets or truthfully fails every frozen threshold;
12. normal Session browser journey shows formal Glance unchanged while Admin
    replay and Coverage Review show clearly labelled Shadow evidence;
13. freeze and rollback restore the prior Shadow policy without changing
    serving order;
14. learning data/artifacts/logs contain no patient text, quotes, Provider
    payloads, credentials or secrets.

## 15. Exit gate

SL2 is complete only when:

- the frozen 30-scenario dataset, manifests and hashes exist;
- staff and clinician models train independently and reproducibly;
- feature whitelist and forbidden-feature tests pass;
- model artifacts capture complete lineage;
- Shadow scoring changes only within deterministic bands;
- eligibility, protection, workflow state and formal Glance are unchanged;
- all frozen validation/test thresholds are reported without post-test tuning;
- failure paths fall back atomically to base ordering;
- Admin replay, freeze and rollback work through normal server sessions;
- all focused and regression verification passes;
- results are labelled synthetic mechanism evidence only.

## 16. Non-goals and prohibited claims

SL2 does not include:

- serving promotion or a learned `adaptive_adjustment` in formal Glance;
- absolute clinical-importance prediction;
- learned eligibility, routing, band assignment or safety override;
- medical severity labels, diagnosis, outcome prediction or treatment advice;
- real clinician/patient data, external/de-identified datasets or AI-generated
  ground truth;
- online learning, click/dwell optimization or random exploration;
- unified cross-role, per-clinic, per-specialty or per-user models;
- XGBoost, LightGBM, LambdaMART, neural networks, Bandits or RL;
- embeddings, free-text ranking or Provider calls;
- diversity-aware Top-5 suppression;
- Task/Event creation, workflow orchestration or clinical-record mutation;
- claims of clinician preference validity, clinical usefulness, safety
  certification or patient-outcome improvement;
- merge, rebase, push, external upload or submission work.

## 17. Post-SL2 decision boundary

After SL2, the owner may separately discuss one of three paths:

1. stop at synthetic Shadow evidence;
2. design a set-level diversity/redundancy reranker using workflow groups;
3. design a future real-feedback validation path if real authorized evidence
   ever becomes available.

None of these paths is authorized or required by this task card.

## 18. Completion record — 2026-09-03

SL2 completed with all frozen mechanism thresholds passing and formal Glance
remaining `base_only`. The complete implementation, lineage hashes, evaluation
metrics, limitations, full regression result and normal-session browser
evidence are recorded in:

`docs/sl2_shadow_pairwise_evidence_2026-09-03.md`

Result classification: `IMPLEMENTED_WITH_LIMITS`. In particular, staff
validation strict-pair accuracy is 0.333 and frozen Top-5 recall is
non-discriminating because every scenario contains exactly five candidates.
These limitations do not fail the card's frozen thresholds, but they prohibit
any clinical-validity or serving-promotion claim.
