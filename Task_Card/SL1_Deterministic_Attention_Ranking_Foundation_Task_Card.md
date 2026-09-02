# SL1 Task Card — Deterministic Workflow-Aware Attention Ranking Foundation

> Phase: Self-Learning Stage 1
> Status: IMPLEMENTED_WITH_LIMITS — deterministic foundation verified; no model trained
> Design source: `docs/top5_attention_ranking_conceptual_design_reference.md`
> Serving mode: `base_only`
> Feature schema version: `attention-feature-v1`
> Workflow schema version: `care-workflow-v1`
> Ranking rule versions: existing `attention-v1` + `importance-v1`

## 1. Outcome

Build the stable representation and deterministic ranking baseline that a later
Self-Learning stage can learn from safely.

Stage 1 must produce a complete, reproducible chain:

```text
Event / Artifact / Task / Highlight
        -> CareWorkflow + typed WorkflowLink
        -> current workflow state + active frontier
        -> role-specific AttentionItem snapshot
        -> eligibility filter
        -> deterministic priority band
        -> fixed within-band score
        -> deterministic Top 5
        -> immutable impression / decision snapshot
```

Stage 1 does not train a model. Its output is the versioned feature contract,
the fixed baseline and the synthetic evidence needed to discuss Stage 2.

## 2. Concrete product example

A patient submits an exact-source report that their headache is much worse.
One source Event opens one explicit workflow; it does not create duplicate
medical Events for Nurse and clinician:

```text
Event E1: patient report
    |
    +--triggered_review--> Task T1: Nurse verification
    |
    +--triggered_review--> Task T2: clinician priority review
                                |
                                +--requires_action--> Task T3: care action
```

- Initially, the Nurse Glance projects T1 as “verify this patient report.”
- T2 may already appear for the clinician as “patient-reported · unverified”
  when the existing exact-source deterministic route created it.
- Completing T1 does not create a second patient fact. Its verified/corrected/
  unable-to-verify result changes the workflow context projected onto T2.
- If the clinician records `action_required`, T2 cannot close until it links to
  one unresolved T3 assigned to clinician or Nurse. T3 may be patient-visible.
- When a patient reports a patient-visible T3 as done, the Task remains
  non-terminal (`reported_done`) until staff/clinician formally verifies and
  completes it.
- Each transition closes, updates or activates role-specific AttentionItems;
  ranking never creates T1, T2 or T3.

The simpler case remains mandatory: a clinician-created ordinary Task assigned
to the Nurse queue is eligible for `staff` and excluded for `clinician` until
an explicit clinician-owned review/escalation Task exists.

## 3. Relationship to the existing product

Stage 1 extends and consolidates the implemented F_A2/F_A1 foundation; it does
not replace it.

- `Patient -> Event -> Artifact -> Span` remains the canonical clinical record.
- `Task`, `Highlight`, `PatientReviewItem`, conflict and safety state remain the
  authoritative domain records.
- `CareWorkflow` stores the operational identity and lifecycle of one handling
  process rooted in an Event. It is not a Care Episode and does not summarize
  or replace clinical content.
- `WorkflowLink` stores explicit, typed relationships between the root Event
  and Task steps. It contains identifiers and relationship metadata only.
- `AttentionItem` is a derived, rebuildable projection. It is not a clinical
  fact table and cannot be edited as clinical truth.
- Existing `GlanceProjection` remains the materialized serving projection.
- Existing `RankingRun` and `RankingDecision` remain the immutable impression
  and decision history.
- Existing F_A2 priority bands and `importance-v1` weights remain the serving
  baseline.
- Existing F_A1 Shadow policy, freeze, replay and rollback infrastructure is
  reused, but no learned policy is enabled in Stage 1.
- No `AttentionItem` database table is added in Stage 1. A typed internal
  projection is materialized into the existing projection/decision records.
- `encounter_id` continues to group Events from the same clinic visit;
  `workflow_id` groups an actionable process across roles and time. Date or
  encounter equality never implies a workflow relationship.

## 4. Frozen terminology

### Event

A real-world occurrence on the longitudinal Timeline. It answers “what
happened” and is not itself the ranking unit.

### Current state

Deterministic state derived from the latest authoritative records at an
injected `as_of` time: open/terminal, assigned role, due/overdue, review state,
conflict state, provenance state, upstream state and downstream obligations.

### CareWorkflow

One clinic- and patient-scoped operational process rooted in exactly one Event,
for example handling one patient submission. One Event may activate multiple
role-specific Task steps inside the same workflow. One Care Episode may contain
many workflows, but Care Episode remains outside Stage 1.

### Workflow node and link

Events and Tasks are workflow nodes; they remain authoritative in their own
tables. `WorkflowLink` is a directed, typed edge explaining why one Task exists,
which earlier step updates it, and which downstream action it requires.

### Active frontier

The set of non-terminal, non-superseded workflow steps whose explicit
prerequisites are satisfied at `as_of`. These are the workflow steps eligible
to generate current role-specific AttentionItems. A non-blocking upstream
verification may change a step's context without preventing it from appearing.

### AttentionItem

One role-specific snapshot of an existing object that may require attention,
decision or action now. The same Task may yield an eligible Nurse projection
and an excluded clinician projection without duplicating the Task.

### Candidate set

All AttentionItem snapshots evaluated for one clinic, patient, viewer role and
`as_of`, including eligible, unsurfaced and excluded items.

### Impression

One immutable `RankingRun` plus all associated `RankingDecision` rows. It must
record the complete candidate set, not only the displayed five.

## 5. Stage 1 candidate sources

Only existing, explicit records and active workflow steps may generate
candidates:

1. a Task-owned Highlight representing an unresolved Care Task or review Task;
2. a non-Task Highlight derived from an Artifact with valid provenance;
3. an unresolved conflict or `needs_review` Highlight;
4. a pinned Highlight;
5. clinician-confirmed allergy context, projected separately as
   `safety_context` and not counted inside the dynamic five.

Rules:

- Every dynamic Task candidate must retain the explicit `Task <-> Highlight`
  link. Never infer Task ownership from same-day or same-Event proximity.
- Workflow-generated Task candidates must retain their `workflow_id`, root
  Event and typed inbound/outbound links. Missing links fail closed to
  `workflow_link_incomplete`; ranking must not invent a chain.
- Terminal Tasks, rejected Highlights and patient-session summary context that
  already has an explicit review workflow are recorded as excluded, not
  silently discarded from impression history.
- Stage 1 adds relational workflow/link tables, not a graph database. It does
  not create a Care Episode table, new Event extractor or parallel patient
  record.
- Task creation is authorized workflow behavior. An importance score, learned
  score or Top-5 position can never create, assign, close or verify a Task.
- Stage 1 supports `staff` and `clinician` ranking projections only. Patient
  ranking and Admin ranking are out of scope.

## 6. `attention-feature-v1` contract

The typed internal snapshot must contain the following feature groups. Stored
`RankingDecision.factor_snapshot` remains metadata-only: no patient text,
quotes, note bodies, comments or Provider payloads.

### 6.1 Identity and lineage — never scored

```text
schema_version = attention-feature-v1
candidate_id
source_kind = task | highlight
source_id
clinic_id
patient_id
event_id
workflow_id | null
workflow_root_event_id | null
workflow_group_key | null
independence_key
workflow_node_type = event | task | null
workflow_node_id | null
viewer_role = staff | clinician
attention_kind
```

`attention_kind` is server-derived from existing structured fields:

```text
care_task
patient_report_review
clinician_priority_review
conflict_review
artifact_highlight
safety_context
```

Unknown or unsupported types use `artifact_highlight`; they are never guessed
from free text during ranking.

### 6.2 Workflow-state features

```text
status
terminal
unresolved
rejected
pinned
needs_review
conflict_unresolved
attention_class
task_kind | null
review_outcome | null
time_sensitivity | null
workflow_status = active | completed | cancelled | not_applicable
active_frontier
superseded
patient_reported_done_pending_verification
```

### 6.3 Role and requested-action features

```text
responsible_role_known
responsible_role | null
assigned_to_viewer_role
requires_action_from_viewer
requires_decision_from_viewer
waiting_for_other_role
role_route_known
```

The role source is explicit Task/review-workflow metadata. `created_by` and
`author_role` never imply current responsibility.

For a non-Task Highlight without explicit responsibility metadata:

```text
responsible_role_known = false
role_route_known = false
```

It remains eligible for both clinical roles under the existing generic
Highlight behavior, and must be visibly auditable as an unknown route. Stage 1
must not fabricate an owner.

### 6.4 Time features

All time-derived values use an injected `as_of`; tests never sleep.

```text
due_known
due_at | null
overdue
escalated
age_seconds
time_to_due_seconds | null
```

No due date means `due_known = false`; it must not be encoded as “not urgent.”

### 6.5 Explicit context/dependency features

```text
workflow_link_known
inbound_relation_types[]
outbound_relation_types[]
blocking_predecessor_count
open_downstream_action_count
workflow_blocking_known
workflow_blocking | null
parent_context_known
upstream_verification_known
upstream_verification_outcome | null
```

Stage 1 uses only explicit `CareWorkflow`, `WorkflowLink`, `workflow_id`,
follow-up links and stored workflow metadata. It does not infer causal or
clinical relationships from dates or free text. A downstream clinician card
reads Nurse verification context through an explicit `verification_updates`
link; it does not copy the Nurse result into a new patient fact. When no
explicit blocking relation exists:

```text
workflow_blocking_known = false
workflow_blocking = null
```

### 6.6 Authority, provenance and safety features

```text
source_binding_status
exact_span_available
source_authority
hard_protected
protection_reasons[]
```

`source_authority` is structural (`patient`, `staff`, `clinician`, `system`),
not a probability. Exact-span claims retain Artifact version + span + quote
hash validation. Event/Task-level candidates use `not_applicable` rather than
pretending to have an exact span.

### 6.7 Existing fixed score features

Stage 1 preserves `importance-v1` exactly:

```text
recency             +2
explicit_risk       +3
unresolved_task     +2
clinician_confirmed +2
symptom_change      +3
repeated_mentions   +1
decay_adjustment    existing deterministic E3 value
adaptive_adjustment 0 in serving
```

These constants are an existing retrieval heuristic, not clinical-risk
weights. Stage 1 does not tune, add or remove scoring weights.

### 6.8 Missingness rule

Unknown is never converted to `false` or zero. Any feature that can be absent
must use either a `*_known` companion flag or an explicit `null` value. Missing
features are preserved for Stage 2 evaluation and cannot create a negative
training label.

## 7. Workflow representation and transition contract

### 7.1 `CareWorkflow` — one operational process

Stage 1 adds one relational `CareWorkflow` model:

```text
workflow_id
clinic_id
patient_id
workflow_kind = patient_report_response | care_action_chain
root_event_id
status = active | completed | cancelled
created_by_role = system | staff | clinician
created_by_user_id | null
created_at
updated_at
completed_at | null
```

Rules:

- the root Event, workflow, every linked Task and every linked Highlight must
  belong to the same clinic and patient;
- one workflow has exactly one root Event, but the Event may trigger multiple
  role-specific Task branches;
- one Task belongs to at most one workflow, and every dynamic Task candidate
  must belong to exactly one workflow after the SL1 migration;
- `patient_report_response` is used for Check-in/report verification chains;
- `care_action_chain` is used for a human-created Task and its explicit
  follow-up actions;
- workflow status is operational metadata, not clinical outcome or resolution
  of the underlying health issue;
- completing a workflow never deletes its Event, Artifacts, Tasks or AuditLog.

### 7.2 `WorkflowLink` — explicit typed edges

Stage 1 adds one relational `WorkflowLink` model:

```text
link_id
workflow_id
clinic_id
patient_id
from_type = event | task
from_id
relation_type
to_type = task
to_id
created_by_role = system | staff | clinician
created_by_user_id | null
created_at
```

Allowed relationship types and their frozen meaning:

```text
triggered_review      root Event activated a review Task
triggered_action      root Event activated an ordinary Care Task
verification_updates  source Nurse review supplies context to target clinician review
depends_on            target stays inactive until source Task is terminal
requires_action       source review decision requires the explicit target care Task
follow_up_for          target Task is a later action for the source Task
superseded_by          target replaces source; source cannot generate a current item
```

Validation rules:

- `triggered_review` and `triggered_action` are the only Event-to-Task
  relationships; all other types are Task-to-Task;
- every endpoint must exist before the link is committed;
- endpoints must match the link's workflow, clinic and patient;
- self-links, cross-patient links, cross-clinic links and directed cycles are
  rejected;
- the tuple `(workflow_id, from_type, from_id, relation_type, to_type, to_id)`
  is unique, making retries idempotent;
- links contain no patient text, clinical summary or copied Task description;
- date, `encounter_id`, title similarity and shared Event membership never
  create an implicit link.

### 7.3 Current workflow state and active frontier

At injected `as_of`, a Task is on the active frontier only when:

1. its Task status is non-terminal;
2. it is not the source of `superseded_by`;
3. every inbound `depends_on` source Task is terminal.

The active frontier is workflow state, not a role decision. Role ownership and
hard protection are applied afterward by the role-specific eligibility rules.

Relationship behavior:

- `triggered_review` activates the created review Task immediately;
- `verification_updates` never blocks clinician visibility. Before Nurse
  completion it projects `upstream_verification_known = false`; after
  completion it projects the authoritative stored verification outcome;
- `requires_action` points to the real downstream Task required by the existing
  F_A2 `action_required` closure rule;
- a patient-visible Task in `reported_done` remains non-terminal and active for
  its responsible clinical role until formal completion;
- terminal or superseded steps remain in Timeline/Task/Audit history but do not
  generate dynamic AttentionItems;
- a workflow becomes `completed` only when all non-superseded Tasks are
  terminal and no `requires_action` obligation is missing or unresolved.

### 7.4 Orchestration authority

- Existing deterministic Check-in and review services may create workflow Tasks
  and links in the same transaction as their authoritative domain changes.
- Human-created Care Tasks use the authenticated actor and an explicit
  assignee; a ranking process cannot create or assign them.
- State transitions are idempotent and write metadata-only AuditLog entries.
- Projection rebuilds read workflow state; they never mutate Workflow, Task,
  Event, Artifact or review decisions.
- No status update becomes a new medical Event merely because it occurred at a
  later time. A genuinely new consult or patient report remains a new Event.

## 8. Feature responsibilities

Features must be classified before use; one flat vector must not control every
decision.

| Feature class | Purpose | Examples |
| --- | --- | --- |
| Scope/security | authorize data access before ranking | clinic, patient, role |
| Eligibility gate | enter or exclude a role candidate | terminal, rejected, assigned role |
| Priority band | determine workflow tier | protected, priority review, overdue |
| Within-band score | deterministic baseline | existing six `importance-v1` flags |
| Tie-break | guarantee stable order | due time, record time, stable id |
| Explanation/audit | explain and replay | rule version, reasons, known masks |
| Stage 2 label only | evaluate future learning; never a Stage 1 feature | outcome label, explicit feedback |

Feedback, displayed rank, clicks and later outcomes must not enter the same
impression's feature vector. This prevents target leakage.

## 9. Role-specific eligibility contract

Scope checks happen before ranking. Cross-clinic and unauthorized records never
enter the projection builder.

For each authorized role projection, apply these rules in order:

1. rejected Highlight -> excluded: `rejected`;
2. completed/cancelled Task -> excluded: `terminal_task`;
3. Task expected to belong to a workflow but missing its workflow/root/link ->
   excluded: `workflow_link_incomplete`;
4. non-terminal Task outside the active frontier -> excluded:
   `inactive_workflow_step`;
5. clinician-confirmed allergy -> excluded from dynamic list:
   `fixed_safety_context` and shown only in `safety_context`;
6. patient-session summary with an explicit patient-review workflow -> excluded:
   `patient_candidate_review_context`;
7. pinned, `needs_review`, explicit-risk or unresolved-conflict Highlight ->
   eligible for both authorized clinical roles and marked `hard_protected`;
8. `patient_report_review` Task -> eligible only for `staff`;
9. `clinician_priority_review` Task -> eligible only for `clinician`;
10. any other Task -> eligible only when `assigned_role == viewer_role`;
11. non-Task Highlight with unknown role route -> eligible for both clinical
   roles, with `role_route_known = false`;
12. unsupported role -> fail closed; no projection is produced.

For Stage 1, `assigned_user_id` is displayed/audited but does not personalize
ranking inside one role. Individual-user ranking is a later, separately
approved capability.

## 10. Deterministic ranking contract

### 10.1 Priority bands — unchanged from F_A2

1. pinned / `needs_review` / hard-protected;
2. current-role priority review;
3. overdue verification or escalation;
4. other overdue Care Task;
5. current-role unresolved Task;
6. routine new patient review;
7. other unresolved content.

### 10.2 Exact within-band order

The serving sort key is frozen as:

```text
priority_band ascending
pinned first
needs_review first
final_score descending
known due time before unknown due time
due_at ascending
Highlight.created_at ascending
Highlight.highlight_id ascending
```

`final_score = base_importance_score + decay_adjustment` in Stage 1 because
serving `adaptive_adjustment` is always zero.

### 10.3 Duplicate-workflow handling

Stage 1 records, but does not suppress, multiple active items from the same
workflow in formal Glance. Two separate identities are required:

```text
workflow_group_key = workflow:{workflow_id}

independence_key = workflow:{workflow_id}:task:{task_id}
                or workflow:{workflow_id}:event:{event_id}:entity:{entity_key}
                or task:{task_id}                         legacy fallback
                or event:{event_id}:entity:{entity_key}  non-workflow Highlight
                or highlight:{highlight_id}              final fallback
```

`workflow_group_key` measures workflow concentration/redundancy.
`independence_key` prevents feedback on a Nurse verification step from
superseding feedback on a separate clinician decision or patient-facing action
inside the same workflow. Coverage Review and replay must report
`duplicate_workflow_rate`. Changing the formal Top 5 to diversity-aware
selection is reserved for Stage 2 discussion, because silent suppression could
hide a distinct action inside one workflow.

### 10.4 Top-5 boundary

- Dynamic `needs_attention` remains limited to five.
- Fixed clinician-confirmed allergy `safety_context` remains outside that five.
- Stage 1 does not introduce a new “critical” classifier or unlimited critical
  overflow. Medical trigger definitions require external clinical authority
  and are outside this synthetic mechanism phase.
- Any hard-protected candidate outside five is retained in Coverage Review and
  counted as a protection-coverage failure; it is never silently treated as a
  successful result.

## 11. Impression and feedback capture

Every projection rebuild must create or deduplicate one immutable `RankingRun`
per clinic/patient/viewer-role/state/policy fingerprint and one
`RankingDecision` per evaluated candidate.

Each decision records:

```text
eligible / exclusion reason
priority band / band reasons
content-free attention-feature-v1 snapshot
base score / shadow score
base rank / shadow rank
surfaced base / surfaced shadow
source binding status
workflow group, node, relationship and independence identity
```

Stage 1 feedback behavior is frozen:

- Hide/Confirm/Acknowledge/Pin change only the current Highlight state; they do
  not train future ranking.
- `quality_issue` is audit/evidence only and has zero ranking value.
- clinician `explicit_demotion` is stored as a Shadow-only label.
- outcome/time-sensitivity labels remain evaluation labels.
- clicks, opens, dwell time and evidence expansion are not learning labels in
  Stage 1 and are not added merely to create more data.
- feedback never changes Event, Artifact, Task, provenance or clinician notes.

## 12. Synthetic evidence set

No real clinician or real patient data is expected. Stage 1 uses a frozen,
hand-written synthetic replay set. It proves mechanism behavior only.

The fixture must include, at minimum:

1. one patient-report Event opening a `patient_report_response` workflow;
2. parallel Nurse verification and clinician priority-review Tasks linked to
   that single root Event;
3. Nurse `pending -> verified` and `pending -> corrected` variants changing the
   clinician AttentionItem context without creating a duplicate Event;
4. clinician `action_required` blocked until an explicit linked Care Task
   exists;
5. a patient-visible Care Task moving to `reported_done`, remaining active for
   formal staff/clinician completion;
6. open Nurse Task created by a clinician and open clinician Task created by a
   Nurse;
7. Nurse Task waiting normally versus the explicit clinician escalation path;
8. one blocking `depends_on` chain, one non-blocking `verification_updates`
   link and one `superseded_by` replacement;
9. overdue verification Task plus completed and cancelled Tasks;
10. pinned, `needs_review` and unresolved-conflict candidates;
11. clinician-confirmed allergy safety context;
12. exact-source Artifact Highlight and Event/Task-level no-span candidate;
13. missing due time, missing workflow link and unknown role-route cases;
14. two active candidates sharing one workflow group but having different
    independence keys;
15. exact ties requiring the stable-id tie-break;
16. cycle, cross-clinic and cross-patient link attempts that fail closed;
17. clinic-B and patient-B isolation controls;
18. more than five eligible candidates so surfaced and unsurfaced decisions are
    both exercised;
19. one clinician Shadow demotion, one quality issue and one unrelated control.

All timestamps use a frozen `as_of`. All expected role eligibility, bands,
scores and final ordering are declared before the replay is run.

## 13. Implementation surface

Expected minimal changes:

- add `CareWorkflow` and `WorkflowLink` to `backend/app/models.py` with the
  frozen enums, uniqueness and scope fields;
- add an additive, idempotent SL1 migration that preserves existing rows and
  applies these fixed backfill rules:
  - Tasks sharing a non-empty legacy `workflow_id` and containing
    `patient_report_review` or `clinician_priority_review` become one
    `patient_report_response` workflow rooted at their existing patient-report
    Event;
  - that root receives one `triggered_review` link to each review Task, and a
    present Nurse-review/clinician-review pair receives one
    `verification_updates` link;
  - other Tasks sharing a non-empty legacy `workflow_id` become one
    `care_action_chain` rooted at their existing Event;
  - a Task with no `workflow_id` receives a stable workflow id derived from its
    Task id, one `care_action_chain`, and one root `triggered_action` link;
  - an existing `follow_up_task_id` creates the corresponding
    `requires_action` link;
  - a legacy group spanning clinics, patients or incompatible root Events fails
    closed and is reported; it is never split or guessed silently;
- add `backend/app/workflow_state.py` for link validation, cycle detection,
  workflow status and active-frontier derivation;
- add `backend/app/attention_items.py` as a pure, typed projection builder;
- update `backend/app/glance_projection.py` to consume the projection builder;
- update `backend/app/shadow_learning.py` to persist the versioned feature
  snapshot, workflow group key, node identity and exact independence key;
- update only the existing patient-report/review and Task creation/completion
  services that must create links or advance workflow state; do not introduce a
  second orchestration path;
- reuse existing JSON fields in `GlanceProjection` and `RankingDecision` for
  feature snapshots; the only schema additions are the two workflow tables;
- add focused tests without modifying unrelated patient, voice, Copilot,
  onboarding or instruction-publication behavior;
- reuse existing Coverage Review and Admin Shadow UI; no new Stage 1 page.

## 14. Failure-first tests

Add these focused test modules:

```text
backend/tests/test_sl1_attention_features.py
backend/tests/test_sl1_workflow_chain.py
backend/tests/test_sl1_role_candidates.py
backend/tests/test_sl1_deterministic_ranking.py
backend/tests/test_sl1_impression_snapshot.py
backend/tests/test_sl1_synthetic_replay.py
```

They must first demonstrate the current gaps, especially:

- an ordinary Task assigned to the other role can remain eligible as generic
  unresolved content;
- `workflow_id` alone cannot prove trigger, dependency, branch or follow-up
  direction;
- `follow_up_task_id` alone cannot represent one Event triggering parallel
  Nurse and clinician review branches;
- a ranking projection cannot distinguish an active step, a blocked step and a
  superseded step from one explicit workflow contract;
- no single versioned feature contract expresses known versus unknown values;
- current decision snapshots do not expose the complete frozen feature groups;
- the clinician-created/Nurse-assigned example cannot be asserted end to end
  from one projection contract.

Then implement the minimum changes that make them pass.

## 15. Required verification

1. focused SL1 tests pass;
2. all existing F_A2/F_A1, Task, Glance, provenance, RBAC, clinic-isolation,
   privacy and data-decay tests remain green;
3. full backend suite passes with existing environment-related skips reported
   separately;
4. frontend production build passes;
5. normal server-session browser journey verifies the mandatory product example
   for Nurse, clinician and Coverage Review;
6. Glance GET remains precomputed, Provider-free and independent of learning
   tables;
7. replaying the frozen snapshot twice yields the same fingerprint, candidates,
   exclusions, scores and order;
8. link creation rejects cycles, missing endpoints and cross-scope ownership;
9. retries create no duplicate Workflow, WorkflowLink, Task, Highlight or
   RankingDecision rows;
10. one root patient Event drives the Nurse -> clinician -> care-action state
    journey without duplicate patient facts or Timeline Events;
11. ranking/learning/workflow metadata contains no patient text, source quote, comment,
   note body, Provider payload, credential or secret;
12. serving remains `base_only`, `adaptive_adjustment = 0`, and no Stage 1
   feedback changes a later formal ranking.

## 16. Exit gate

Stage 1 is complete only when all of the following are true:

- every candidate is represented by `attention-feature-v1` with an explicit
  feature class and known/unknown semantics;
- every workflow has one root Event, validated typed links and a deterministic
  active frontier;
- Nurse verification changes clinician projection context through an explicit
  link without copying or replacing the patient source;
- `action_required` has a linked actionable Task, and patient `reported_done`
  remains pending formal clinical-role completion;
- the clinician-created/Nurse-assigned Task is eligible for Nurse and excluded
  for clinician until an explicit clinician-owned action exists;
- every eligible, unsurfaced and excluded candidate is captured in an immutable
  impression;
- every ordering decision identifies eligibility, band, fixed score arithmetic,
  due-time handling, rule versions and final stable tie-break;
- the frozen synthetic replay is deterministic and clinic/patient isolated;
- safety/provenance protections and Coverage Review remain intact;
- formal Glance remains A2 deterministic `base_only`;
- evidence is described as workflow/ranking mechanism conformance, not clinical
  validity, clinician preference learning or outcome improvement.

## 17. Non-goals

Stage 1 does not include:

- learned weights, Logistic Regression, pairwise ranking, LambdaMART, XGBoost,
  neural ranking, Bandit or reinforcement learning;
- online parameter updates, random exploration or serving promotion;
- real clinician recruitment, real patient data or de-identified clinical
  datasets;
- guessed medical severity weights, diagnosis, risk probability or clinical
  validation;
- embeddings or whole-record black-box ranking;
- patient-facing ranking, individual clinician personalization or specialty
  models;
- a new Event store, Care Episode scope, graph database, generic workflow
  engine, FHIR serialization or interoperability claim;
- changes to raw records, clinical notes, Task authority or exact provenance;
- merge, rebase, push, external upload or submission work.

## 18. Stage 2 handoff package

Stage 1 hands the Stage 2 discussion exactly these frozen artifacts:

1. `attention-feature-v1` schema and feature-class registry;
2. `care-workflow-v1` schema, typed-link semantics and active-frontier rules;
3. role-specific candidate and exclusion contract;
4. deterministic `attention-v1` / `importance-v1` baseline;
5. immutable impression snapshots containing displayed and undisplayed items;
6. frozen synthetic workflow scenarios and expected labels;
7. protection, provenance, privacy and isolation constraints;
8. deterministic replay report and baseline metrics;
9. an explicit list of features that are eligible or forbidden for learning.

Stage 2 is defined separately in
`Task_Card/SL2_Shadow_Pairwise_Linear_Ranking_Task_Card.md`. It trains only a
role-specific Shadow pairwise linear ranker and cannot change serving under the
SL1 or SL2 contracts.

## 19. Implementation evidence — 2026-09-02

- Added metadata-only `CareWorkflow` and `WorkflowLink` tables, validated typed
  edges, cycle/scope rejection, deterministic active-frontier derivation and an
  additive idempotent legacy Task backfill.
- Added the pure `attention-feature-v1` role projection and connected it to the
  existing `GlanceProjection`, `RankingRun` and `RankingDecision` paths. No
  `AttentionItem` table or second clinical authority was added.
- Formal Glance remains `attention-v1` / `importance-v1`, `base_only`, with
  serving `adaptive_adjustment = 0`. No learned model or learned serving policy
  was introduced.
- Patient Check-in review orchestration now records one root Event workflow,
  parallel Nurse/clinician review links, non-blocking verification context and
  explicit downstream `requires_action` links. `reported_done` remains active
  until formal clinical-role completion.
- Six focused SL1 modules cover feature completeness/missingness, link
  validation, role routing, deterministic ties, complete immutable impressions
  and frozen synthetic replay. Final backend regression: **669 passed, 2
  existing local-ASR-input skips**. Frontend production build: **65 modules**.
- Normal Cookie Session browser evidence on a temporary synthetic database
  covered patient submit -> Nurse review projection + clinician priority
  projection -> Coverage Review, including eligible/unsurfaced/excluded rows,
  `NOT_APPLICABLE` Event/Task sources, `base_only` copy and zero browser
  warning/error. The linked `action_required` closure path is covered by the
  backend Session/API regression rather than a browser mutation journey.
- Evidence is mechanism conformance only. Clinical validity, clinician
  preference learning, outcome improvement, real-world workflow suitability,
  patient/Admin ranking and learned serving remain **NOT ESTABLISHED / out of
  scope**.
