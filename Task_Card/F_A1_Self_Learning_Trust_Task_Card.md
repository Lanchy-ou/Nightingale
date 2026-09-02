# F_A1 Task Card — Self-Learning Trust and Blind-Spot Control

> Official scenario: 15
> Priority: A — highest optimization focus
> Status: IMPLEMENTED_AND_VERIFIED_WITH_LIMITS — auditable Shadow foundation completed 2026-09-02; no model training authorized

## Outcome

Make every role-specific ranking decision auditable, including candidates outside Top 5, while preventing Hide, rapid review actions or unvalidated learning from changing formal Glance ordering.

F_A1 is a trust and evaluation layer, not a trained ranking model. A2 remains the serving authority.

## Approved serving and feedback semantics

- Formal Glance is permanently `base_only` in this phase. `adaptive_adjustment=0` on serving writes; A2 priority bands, deterministic factors, decay and stable tie-breaks remain authoritative.
- Existing `importance_feedback` is preserved as immutable legacy evidence but status endpoints no longer append to it.
- Hide removes only the current Highlight. Confirm/Acknowledge/Pin affect only the current item and do not teach future ranking.
- A2 clinician outcome/time-sensitivity labels are stored as evaluation labels, not ranking preferences.
- Only clinician may submit `explicit_demotion`; Nurse and clinician may submit `quality_issue`. All signals are Shadow-only.
- Demotion reasons are controlled: `duplicate_or_redundant`, `already_resolved_or_stale`, `not_actionable_for_viewer_role`, `lower_than_other_active_work`.
- Quality reasons are controlled: `extraction_incorrect`, `source_mismatch`, `wrong_role_route`; these always have zero ranking value.
- Negative generalization is blocked for allergy, explicit risk, unresolved Task, clinician-confirmed, pinned, `needs_review`, unresolved conflict and priority patient-review work.
- Teaching is itemized and explicitly confirmed; no bulk endpoint exists. Latest signal per actor and independence key is effective during replay.

## Implemented data and workflow contract

- `RankingRun` captures one immutable clinic/patient/role/rule/policy ranking state and deduplicates identical states by SHA-256 fingerprint.
- `RankingDecision` records every projected candidate: eligibility, exclusion, band, content-free factor snapshot, base/shadow ranks and Top 5 inclusion. It stores no patient text, quote or Provider payload.
- `LearningSignal` separates `outcome_label`, `explicit_demotion` and `quality_issue`, including eligibility/ineligibility reason and supersession lineage.
- `LearningPolicyVersion` keeps serving fixed to `base_only` and supports `legacy-e2-v1` versus `no-adjustment-v1` Shadow policies, freeze cutoff and rollback.
- `LearningEvaluation` persists reproducible base-vs-Shadow metrics. No `enabled` serving policy can be activated; attempts fail 422.
- Projection rebuilds write immutable ranking snapshots. Glance GET remains Provider-free and does not query RankingRun, RankingDecision, LearningSignal, policy, evaluation or legacy feedback tables.

## Coverage Review and Admin controls

- `Coverage Review` is a separate patient workspace tab; it never inserts random candidates into Glance.
- Nurse and clinician inspect their own role projection in three groups: formal Top 5, eligible but not shown, and excluded with reason.
- Exact-span candidates retain source navigation. Event/Task-level candidates are labelled instead of pretending to have an exact span.
- Nurse can report only quality/routing problems. Clinician can additionally submit controlled Shadow demotion.
- Admin Shadow Learning shows serving mode, active Shadow policy, freeze state and latest replay; it can replay, freeze/resume, and switch between approved Shadow policies.

## Evaluation contract

Replay reports content-free counts and comparison metrics, including candidate/eligible/surfaced/unsurfaced/excluded totals, grade 2–3 and time-sensitive Top 5 coverage when labels exist, base/Shadow overlap, rank shifts, NDCG@5 when labels exist, protection violations, invalid surfaced items, actionable-role coverage, duplicate workflow rate, independent workflow count, clinician count and label-missing rate.

`None`/“Not enough labels” is the required result when labels are absent; it must never be converted to zero or a success claim.

## Current evidence (2026-09-02)

- Failure-first tests reproduced the old Hide-to-`-1` coupling and missing Rank 6+ decision history before implementation.
- Backend full collection: 556 tests; 554 passed and 2 pre-existing real-local-ASR input tests skipped.
- Frontend production build passed: 62 modules.
- Normal Session browser journey passed:
  - Nurse Coverage displayed seven eligible unsurfaced candidates and no demotion control; quality feedback persisted as non-ranking evidence.
  - Clinician explicit demotion produced an eligible Shadow signal; formal Coverage Top 5 exactly matched live Glance.
  - Hide removed one current item while legacy feedback count remained unchanged and serving adaptive stayed zero.
  - Admin replay evaluated 16 stored runs / 168 decisions; protection and invalid-surfaced violations were zero. Missing A2 labels were truthfully reported as unavailable.
  - Freeze/resume and `legacy-e2-v1` ↔ `no-adjustment-v1` Shadow rollback succeeded while serving remained base-only.
- Local SQLite received the additive, idempotent F_A1 migration; existing data and legacy feedback were not deleted or reseeded.

## Remaining gates before any model training or serving promotion

- Define numeric evidence-volume, coverage and inter-rater thresholds from real-clinic evidence.
- Complete the deferred F-task reason-code stability matrix with mock, fallback and live Provider reported separately.
- Obtain external clinical review of medical trigger definitions and protected categories.
- Approve a separate model-training card, frozen dataset, evaluation protocol, rollback trigger and promotion decision.

## Non-goals and non-claims

No LambdaMART, Bayesian model, neural model or Bandit is trained. No online/random exploration, individual clinician learning, free-text feedback, clinical-risk probability, medical-validity claim, real-clinician validation claim or clinical-outcome improvement claim is added.
