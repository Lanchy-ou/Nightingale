# Self-Learning Design and Release Boundary — 2026-09-03

Status: `IMPLEMENTED_WITH_LIMITS`
Formal serving mode: `base_only`
Evidence: synthetic mechanism tests only; real-clinician validation `NOT_RUN`

## 1. What controls Glance today

The formal Glance order is deterministic. `attention-v1` first applies
role-specific eligibility and fixed priority bands; `importance-v1` then uses
stored, explainable factors such as recency, explicit risk, unresolved work,
clinician confirmation, symptom change and repeated mentions. Stable due-time,
creation-time and identifier tie-breaks make the result reproducible. The warm
read path uses materialized `GlanceProjection` rows and does not train or call a
Provider.

No SL2 or SL3 model is loaded by the formal Glance GET path. The serving
adaptive adjustment is forced to zero. Activating, freezing, replaying or
rolling back a Shadow policy changes Shadow evidence only; it cannot change an
Artifact, Task, Highlight, workflow, priority band, eligibility result or the
formal Top 5.

## 2. Implemented learning stages

| Stage | Implemented behavior | Boundary |
| --- | --- | --- |
| SL1 | Builds content-free role-specific `AttentionItem` snapshots and immutable `RankingRun` / `RankingDecision` records for every surfaced, eligible-unsurfaced and excluded candidate. Each decision records base rank, Shadow fields, eligibility/exclusion, priority band, workflow identity and source-binding status. | No model is trained. Clinical text and Provider payloads are not ranking features. Formal Glance remains deterministic. |
| SL2 | Trains separate reproducible staff and clinician pairwise linear logistic rankers from a frozen 30-scenario synthetic corpus. The exact 18-feature whitelist, split, optimizer, hashes and role artifacts are fixed. Inference is offline/Admin Shadow replay only and can reorder only eligible, non-protected candidates within an unchanged priority band. | Synthetic mechanism evidence is not clinician preference or clinical-validity evidence. The staff validation accuracy warning and non-discriminating five-item Top-5 metric remain visible. |
| SL3 | Compiles the latest eligible explicit `outcome_label` records into a clinic-scoped, role-scoped, content-free offline pairwise dataset. Pair groups require the same reviewer, run, role and priority band; exports replace source identities with hashes and fixed feature vectors. Training is an explicit local operator command with a required evidence classification. | The seeded database has zero eligible observed pairs, so training correctly stops without an artifact. No real-feedback model has been validated, promoted or served. |

SL1 records exposure instead of learning only from the displayed five. Coverage
Review separates `formal_top`, `eligible_unsurfaced` and `excluded`, so later
evaluation can see which candidates the deterministic policy hid and why.
This reduces blind spots in the evidence record; it does not by itself remove
exposure bias because explicit labels still depend on what reviewers inspect.

## 3. Feedback and dataset contract

Status changes and ranking labels are distinct:

- ordinary accept/reject/pin status controls do not train SL1/SL2/SL3;
- explicit demotion and quality signals are stored as bounded Shadow evidence;
- only an explicit `outcome_label` with `attention_label_v1` and grade `0..3`
  can enter the SL3 compiler;
- clicks, opens, dwell time, missing feedback, AI output and unreviewed items are
  never inferred as labels;
- only the latest label for the same controlled identity is used, while
  supersession remains auditable;
- staff and clinician data are never pooled into one model.

SL3 accepts a pair only when both decisions are eligible, non-protected, from
the same clinic/reviewer/run/role/priority band, have distinct independence
keys, have a valid frozen feature vector, and have source binding `current` or
`not_applicable`. A complete reviewer/run/band group stays in one deterministic
train, validation or test split. Raw text, quotes, names and direct clinic,
patient, actor, decision, Highlight and workflow identifiers are absent from
the exported pair rows.

The initial SL3 mechanism minimum is 12 strict pairs, six complete pair groups,
two reviewers, and at least one strict pair in each split. This is only an
engineering/data-integrity threshold. It is not a clinical calibration or
promotion threshold.

## 4. Safeguards against unsafe automatic demotion

The system uses several independent gates:

1. **Base-only serving.** Learned scores cannot reach formal Glance in the
   current release.
2. **Eligibility before learning.** Terminal, rejected, inactive, incomplete,
   wrong-role and other excluded records cannot be made eligible by a model.
3. **Priority bands stay fixed.** Shadow ranking is limited to within-band
   comparisons; it cannot move an ordinary item above a protected or
   role-priority band.
4. **Protected categories keep base treatment.** Allergies, explicit risks,
   unresolved tasks, clinician-confirmed items, pinned items, conflicts,
   `needs_review` items and priority-review Tasks are protected from negative
   generalization. Fixed Safety Context remains outside the dynamic five.
5. **Bounded legacy adjustments.** Stored Shadow adjustment evidence is capped
   to `[-2, +3]`; negative decay/adjustment is blocked for protected items.
   The formal serving adjustment is nevertheless zero.
6. **Provenance eligibility.** Artifact-derived feedback requires an
   independent system AI Summary plus a current exact raw-source span and quote
   hash. SL3 also rejects stale/mismatched source bindings; Task/Event candidates
   without an Artifact span are explicitly `not_applicable`, never assigned a
   fabricated span.
7. **Atomic fail-closed replay.** A missing artifact, role/scope mismatch,
   feature/schema/hash mismatch, unsupported policy or non-finite score causes
   the entire role replay to use base ordering. Partial learned order is not
   retained.
8. **Freeze, replay and rollback.** Freeze records a signal cutoff; replay is
   deterministic and produces evaluation evidence; rollback selects a prior
   Shadow policy. None of these operations mutates formal serving order.

These controls prevent the current mechanism from silently suppressing a
protected clinical item. They do not prove that the deterministic base policy
or a future learned policy is clinically optimal.

## 5. Release boundary and unresolved work

No real-feedback model has been trained or validated. `authorized_real_feedback`
is only an operator-supplied provenance classification; it is not proof of
consent, representativeness, label quality or sufficient sample size. The
current application exposes no browser action, scheduler or page-load side
effect that trains, promotes or serves a model.

Before any future serving proposal, a separately approved release gate must at
least define and then test:

- representative real label volume per role, clinic type and workflow;
- reviewer agreement, label definitions and adjudication;
- exposure-bias measurement for items rarely opened or labelled;
- alert-fatigue and duplicate-workflow metrics, including harmful suppression;
- score/rank calibration against an owner-approved operational outcome;
- protected-category recall and explicit must-surface cases;
- prospective Shadow comparison, rollback triggers and monitoring ownership;
- privacy, retention, consent and access rules for real feedback;
- an independent clinical-safety review and a staged promotion decision.

SL2's frozen results, including the staff validation warning, cannot be reused
as this gate. SL3's current zero-pair result is an honest stop condition, not a
reason to lower thresholds or manufacture labels.

## 6. Explicit non-authorization

This note documents the implemented architecture. It does not authorize real
feedback collection, model training, automatic retraining, serving promotion,
deployment, clinical-trust claims, or changes to deterministic Glance. Those
actions require a new owner-approved task card and observed evidence against
predeclared promotion and rollback criteria.

Implementation evidence: `docs/sl1_attention_ranking_evidence_2026-09-02.md`,
`docs/sl2_shadow_pairwise_evidence_2026-09-03.md`, and
`docs/sl3_observed_feedback_training_bridge_evidence_2026-09-03.md`.
