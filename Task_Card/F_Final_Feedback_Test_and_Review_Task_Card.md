# F Final Feedback Task Card — Consult Review Evidence and Learning Design

> Status: `IMPLEMENTED_WITH_LIMITS` — engineering controls verified; multilingual clinical validity and live Provider evidence remain NOT_RUN
> Timebox: 120 minutes maximum, leaving the remaining submission window for the
> Technical Brief, demo recording, final regression, and delivery.
> Scope: synthetic data only; current repository behavior is the baseline.

## Outcome

Turn the remaining official feedback into one small, honest, testable consult
review improvement and one current-state design document. Do not attempt a
streaming-audio, diarization, real-time co-editing, or model-serving rewrite.

The completed slice must demonstrate that a clinician reviews speaker labels,
mixed-language text, and medication/dosage mentions against the source before a
Doctor Consult transcript is confirmed for downstream processing. It must not
claim automatic speaker attribution, multilingual clinical understanding, or
medical-reference validation.

## Plain-language product contract

A Transcript is the structured written record of a consultation. Each segment
has a continuous index, an allowed speaker label, and the words attributed to
that speaker. It may come from manually pasted speaker-labelled text or from a
Voice capture that enters human review. The immutable Transcript is source
evidence; the AI Summary is a separate derived Artifact.

For this task:

1. AI/ASR may preserve text and propose processing output, but it must not be
   the authority that decides who spoke.
2. A mixed-language statement remains verbatim source text. Human review does
   not imply that every downstream extractor understands every language.
3. Medication/dosage review means "checked against the source transcript by a
   clinician". It does not mean checked against RxNorm, MIMS, BNF, or another
   medical reference.
4. Existing clinician-authored Artifacts, completed Tasks, publication state,
   receipts, and review decisions must remain outside AI ownership.

## Current verified baseline

- Manual Doctor Consult input already uses continuous `doctor|patient` segments.
- Local ASR deliberately emits unknown speakers and blocks confirmation until
  role-bounded human review resolves all blocking issues.
- Transcript, AI Summary, clinician note, patient instruction, Task, and Audit
  state are stored separately.
- Exact Artifact/Version/Span/quote-hash provenance, optimistic concurrency,
  deterministic fallback, and clinic-scoped Shadow Learning already exist.
- SL2 has frozen synthetic pairwise linear model artifacts; SL3 has an
  observed-feedback dataset bridge. Neither model controls formal Glance.

## Task 1 — Server-enforced Doctor Consult review attestation

Add the minimum typed confirmation contract for Doctor Consult confirmation:

- `speaker_labels_reviewed=true`
- `mixed_language_content_reviewed=true`
- `medication_dosage_mentions_reviewed=true`

All three statements mean the reviewer performed the check, including deciding
that no relevant mixed-language or medication/dosage mention exists. The server,
not only the frontend, must reject a missing or false attestation. Record only
the booleans, reviewer identity, role, and time as metadata; do not copy clinical
text into operational logs or Audit details.

Apply the gate only to clinician-owned Doctor Consult confirmation paths. Do not
force a patient to make a clinical medication/dosage attestation, and do not
change Nurse authority in this timebox.

Keep the Transcript immutable. The attestation must not edit source words,
invent a speaker, mark a medication medically valid, or publish a patient
instruction by itself.

### Required tests

1. Missing or false attestation is rejected before downstream AI processing.
2. A complete attestation allows the existing raw-first Doctor Consult flow.
3. Rejection persists no derived AI Summary and creates no duplicate Event or
   Transcript; retry with the same operation identity remains safe.
4. Audit metadata contains the reviewer and three booleans, but no Transcript
   text, patient name, IC/ID, phone number, medication, or dosage.
5. Patient and staff roles cannot submit the Doctor Consult attestation.

## Task 2 — Frozen mixed-language Transcript evaluation

Add one hand-written synthetic Doctor/Patient consultation containing a single
statement with Malay, English, and a Hokkien expression. Keep it consistent with
the canonical synthetic patient facts; do not import a public clinical dataset.

The evaluation proves only transport, review, and provenance behavior:

1. UTF-8 source text round-trips exactly without translation or normalization.
2. Segment indexes remain continuous and reviewed speaker labels remain intact.
3. An exact quote produced by Mock or deterministic processing must resolve to
   the original Artifact and Span; a changed/nonexistent quote is dropped.
4. Unknown speaker input remains blocked until human review.
5. Unsupported multilingual extraction fails closed or enters human review; it
   must not manufacture a medication, dosage, allergy, risk, or translation.
6. Provider, Mock, deterministic fallback, and `NOT_RUN` multilingual-clinical
   evidence remain separately labelled.

Suggested test location:

`backend/tests/test_feedback_consult_review.py`

Reuse existing transcript, Voice review, AI pipeline, and provenance helpers.
Do not create a second parser, Provider exit, or translation service.

## Task 3 — Self-Learning design and release-boundary note

Create:

`docs/self_learning_design_and_release_boundary_2026-09-03.md`

The note must explain the system that actually exists:

1. deterministic base ranking is the formal Glance authority;
2. SL1 records content-free surfaced, unsurfaced, and excluded decisions;
3. SL2 trains reproducible role-specific pairwise linear models from the frozen
   synthetic corpus and evaluates them in Shadow only;
4. SL3 compiles eligible explicit clinician outcomes into a clinic-scoped,
   content-free offline dataset;
5. caps, protected categories, provenance eligibility, freeze, replay, and
   rollback prevent automatic unsafe demotion;
6. no real-feedback model has been validated or promoted to serving;
7. exposure bias, alert fatigue, real label volume, calibration, and promotion
   gates remain unresolved.

This is documentation of an implemented architecture, not authorization to
train, promote, deploy, or claim a clinically trustworthy model.

## Task 4 — Focused regression and evidence update

Run the new tests plus the existing contracts most likely to regress:

- Doctor Consult ingestion and idempotency;
- Voice transcript review/confirmation;
- provenance resolution;
- RBAC clinic scope;
- patient instruction publication;
- concurrent edits;
- Shadow/SL2/SL3 isolation.

Then run the frontend production build. Update the current readiness ledger and
Technical Brief with observed results only. Do not convert a skipped ASR test,
Mock result, local hanging-server test, or design note into live clinical or
Provider evidence.

## Exit gate

- The Doctor Consult review attestation is enforced server-side and visible in
  the clinician confirmation UI.
- The synthetic mixed-language case passes exact round-trip and provenance tests.
- Unsupported language/speaker behavior fails closed without invented facts.
- Existing raw-first, clinic-scope, patient-view, concurrency, and publication
  contracts remain green.
- The Self-Learning note matches current code and explicitly says Shadow/base-only.
- Frontend production build passes.
- The readiness ledger states the remaining limits without overclaiming.

## Stop conditions

Stop new implementation and preserve the last passing state if this task has not
passed its focused tests within 90 minutes. Use the remaining submission window
for the Technical Brief, demo, final verification, and delivery.

## Non-goals

- streaming audio or incremental in-consult alerts;
- noisy-environment ASR accuracy work;
- automatic speaker attribution or diarization;
- translation or clinically validated multilingual extraction;
- external medical-reference or dosage validation;
- WebSocket presence, OT, CRDT, or Google Docs-style co-editing;
- an AI Summary regeneration workflow;
- real-feedback training, automatic retraining, model promotion, or serving;
- public deployment, external delivery, or real PHI.

## Completion record — 2026-09-03

- Both manual and Voice Doctor Consult confirmation paths enforce the three
  clinician review attestations server-side. Nurse and patient authority is
  unchanged.
- The hand-written Malay-English-Hokkien fixture passed exact transport,
  reviewed speaker, provenance and fail-closed unsupported-output tests.
- Audit details contain only the three booleans; reviewer, role and time use the
  existing metadata columns.
- The Self-Learning architecture/release boundary is documented with formal
  Glance remaining deterministic `base_only` and real-feedback serving blocked.
- Full backend: 712 collected, 710 passed, 2 explicit local-ASR-input skips.
  Frontend production build passed with 112 modules transformed.

Evidence: `docs/final_feedback_consult_review_evidence_2026-09-03.md` and
`docs/self_learning_design_and_release_boundary_2026-09-03.md`.
