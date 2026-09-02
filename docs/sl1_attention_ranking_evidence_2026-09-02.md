# SL1 Deterministic Attention Ranking Evidence — 2026-09-02

## Result

`IMPLEMENTED_WITH_LIMITS`

SL1 now provides a deterministic, role-aware workflow/ranking representation
that later learning work can replay safely. It does not train a model and does
not claim clinical validity.

## Product behavior verified

- One submitted synthetic patient Check-in remains one patient Event.
- The Event owns one `patient_report_response` workflow with explicit Nurse and
  clinician review branches.
- Nurse verification updates clinician context through
  `verification_updates`; it does not copy or replace the patient statement.
- A clinician `action_required` outcome must link a real unresolved Care Task.
- Patient `reported_done` remains non-terminal until staff/clinician completion.
- Ordinary Tasks route only to their explicit responsible role. Other-role,
  terminal, superseded, incomplete-link and patient-review-context candidates
  remain in the immutable impression with an exclusion reason.
- Artifact claims preserve exact version/span/hash provenance. Event/Task-level
  candidates without an exact span are explicitly `not_applicable`, not
  `binding_missing` and never given a fabricated span.
- Formal Top 5 remains fixed `attention-v1` / `importance-v1`, with Safety
  Context outside the dynamic five and learned adjustment disabled in serving.

## Implementation surfaces

- `backend/app/models.py`: `CareWorkflow`, `WorkflowLink`.
- `backend/app/workflow_state.py`: workflow creation/backfill, link validation,
  cycle/scope rejection, active frontier and lifecycle status.
- `backend/app/attention_items.py`: content-free `attention-feature-v1`
  snapshots, role eligibility, priority bands and stable ordering.
- `backend/app/glance_projection.py`: materializes AttentionItems into the
  existing role projection.
- `backend/app/shadow_learning.py`: immutable full-candidate snapshots,
  workflow/independence identity and replay metrics.
- Existing Task and patient-review services create/advance links; ranking code
  cannot create, assign, close or verify Tasks.
- `backend/app/db.py`: additive/idempotent migration plus ownership preflight,
  indexes and SQLite/SQLCipher scope triggers.

## Verification

- Focused SL1 plus F_A2/F_A1 regression: passed.
- Full backend: `669 passed, 2 skipped` in 199.52 seconds. The two skips are the
  existing local-ASR-input integration skips; no SL1 test was skipped.
- Frontend: standard `npm run build` passed, 65 modules transformed.
- `git diff --check`: passed.
- Browser: normal server Cookie Sessions on a temporary synthetic database:
  patient submit, Nurse Glance/Coverage, clinician Glance/Coverage, parallel
  role routing, eligible/unsurfaced/excluded decisions, `NOT_APPLICABLE`
  Task-level source display, `base_only`/Shadow-only copy, and zero console
  warning/error.
- Full Nurse verification -> clinician outcome -> linked care-action state
  mutation is covered by backend Session/API tests; it was not repeated as a
  browser mutation journey.

## Limits

- Synthetic mechanism evidence only; no real patient or clinician data.
- No clinical severity model, threshold, must-surface definition or clinical
  safety certification was introduced.
- No learned weights, online updates, random exploration or serving promotion.
- No individual clinician, patient-facing or Admin ranking.
- Diversity-aware Top 5 suppression remains reserved for Stage 2 discussion.
