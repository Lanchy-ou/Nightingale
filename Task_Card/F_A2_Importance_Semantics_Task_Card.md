# F_A2 Task Card — Importance Semantics and Failure Handling

> Official scenario: 14
> Priority: A — core ranking contract and prerequisite for F_A1
> Status: IMPLEMENTED_AND_VERIFIED_WITH_LIMITS — deterministic scope and review-closure hardening completed 2026-09-02

## Outcome

Make every Highlight's retrieval priority reproducible and explainable, and define what the system does when a clinician judges the ranking wrong, without presenting the score as clinical risk probability or guessed medical truth.

## Current verified baseline

- Base importance is a deterministic weighted sum of stored feature flags.
- Highlight stores base, adaptive, decay, and final score fields.
- Glance reads precomputed scores and remains Provider-free.
- Every role projection stores eligibility, exclusion reason, priority band, factor arithmetic and rule version, including candidates excluded from the top five.
- The UI explains learned adjustment when non-zero and exposes the persisted deterministic band/factor explanation on demand.

## Approved v1 product contract

Glance is a patient-level attention surface with two projections:

- `safety_context`: fixed, clinician-confirmed allergy context; it does not consume the dynamic top five;
- `needs_attention`: role-specific, unresolved work requiring review, decision or action.

The server role `staff` is the Nurse role. v1 does not add a separate Nurse RBAC role and does not learn individual clinician/staff habits.

Every submitted Patient Check-in creates one internal `patient_report_review` Task assigned to `staff`. AI extracts exact-source patient-reported candidates and may recommend a clearly unverified priority-review route. The recommendation is never clinical confirmation.

Approved priority-review reason codes:

```text
patient_explicit_worsening
patient_explicit_severe_intensity
patient_requests_urgent_contact
patient_reports_medication_or_allergy_concern
```

Only exact-source, schema-valid provider results may use these codes. Provider fallback, invalid output, unknown codes and failed provenance enter routine Nurse review. Current deterministic `safety_escalated` behavior remains separate and does not become a real-time clinic alert.

Routine Nurse review is due and escalates after 12 elapsed hours. The environment-owned default is `NANTINGALE_PATIENT_REVIEW_WINDOW_MINUTES=720`; development/test may use 5 minutes. Automated tests inject time and never sleep.

Clinician review records two independent labels:

```text
review_outcome = no_action | monitor_or_record | action_required
time_sensitivity = routine | time_sensitive
```

`no_action + time_sensitive` is invalid. `attention-label-v1` derives grades 0/1/2/3 without treating unreviewed items as negative labels.

Actual medical thresholds and clinical validity remain `NEEDS_CLINICAL_INPUT`. v1 reports rule/workflow conformance only.

### Approved action ownership and label semantics

- `patient_report_review` and `clinician_priority_review` are review work. They determine whether a patient report was verified and whether follow-up action is needed; they are not the follow-up action itself.
- A clinician may not close a review as `action_required` without linking one unresolved `care_action` Task in the same patient record. The follow-up Task may be assigned either to the completing clinician (`assigned_role=clinician`, `assigned_user_id=current clinician`) or to the Nurse queue (`assigned_role=staff`, no individual user required). A time-sensitive result also requires an explicit due time.
- A Nurse-created ordinary Task assigned to a clinician is valid clinician work and appears in the clinician projection. It does not itself create an `attention-label-v1` grade. The label is derived only from the clinician's explicit two-axis completion of the review Task.
- A patient report matching an approved priority-review reason code creates the clinician review Task immediately as `Patient-reported · Unverified`, alongside the Nurse verification Task. Nurse verification updates the clinician card but is not the only route by which the clinician becomes aware of the report.

### Information classification direction (FHIR-aligned, not FHIR-conformance claimed)

The canonical clinical record remains `Event -> Artifact -> Span`; FHIR concepts are used as a design vocabulary so the distinctions are not forgotten:

- patient submission / conversation delivery resembles HL7 FHIR `Communication`;
- a patient- or Nurse-reported measurement or assertion may later be represented as `Observation`, with subject, status, effective time and performer kept explicit;
- actionable work maps to `Task`, including requester, owner, status, timing and focus;
- clinician-confirmed persistent safety context resembles `Flag`;
- unresolved conflict or potential issue resembles `DetectedIssue`;
- authorship, derivation, version and source lineage map to `Provenance`.

F_A2 does not replace these source records with one universal fact table. A future `AttentionItem` is a derived, rebuildable projection over Task, Highlight, Artifact and conflict/safety records. Its first complete classification should keep separate axes for: content kind, workflow state, requested action, responsible role/user, source authority, time semantics, provenance, eligibility, priority band and factor explanation. It must not become a second source of clinical truth or weaken exact-span provenance.

Reference vocabulary (official HL7 FHIR R5 pages): [Communication](https://hl7.org/fhir/R5/communication.html), [Observation](https://hl7.org/fhir/R5/observation.html), [Task](https://hl7.org/fhir/R5/task.html), [Flag](https://hl7.org/fhir/R5/flag.html), [DetectedIssue](https://hl7.org/fhir/R5/detectedissue.html), and [Provenance](https://hl7.org/fhir/R5/provenance.html). These are conceptual mapping references only; F_A2 does not claim FHIR serialization, profile conformance or interoperability certification.

## Deterministic implementation contract

- Extend Task with workflow kind/id, attention class, creation method, verification outcome, escalation timestamps, clinician outcome labels, routing metadata and immutable source binding.
- Create idempotent staff/clinician review Tasks with stable workflow identities. A retry repairs missing derived workflow rows without duplicating Event, Artifact, Highlight or Task.
- Precompute role-specific Glance projections for both eligible and excluded candidates. Projection metadata contains no raw clinical text.
- Exclude terminal Tasks from dynamic Glance while preserving Timeline/Audit history.
- Add role-scoped Nurse verification and clinician completion endpoints. Corrections remain Staff Note/Comment content, never Task metadata.
- Persist one review decision per extracted patient-report candidate. A `corrected` candidate must link to an authored Staff Note in the same Event; session-level completion is blocked while any candidate remains pending.
- Require a linked, unresolved downstream `care_action` before accepting `action_required`; keep its assignee and due time explicit instead of hiding the action in review metadata.
- Add an explicit ranking rule version and server-authoritative factor explanation. Existing deterministic score remains a retrieval heuristic inside approved priority bands, not a clinical-risk probability.
- Keep Glance reads Provider-free and limit dynamic items to five.

### Approved deterministic priority bands

1. pinned / `needs_review` / hard-protected;
2. current-role priority review;
3. overdue verification or escalation;
4. other overdue Care Task;
5. current-role unresolved Task;
6. routine new patient review;
7. other unresolved content.

Within a band, sort by stored score, due time, record time and stable id.

## Failure-first evidence

Before implementation, demonstrate at least:

- a submitted Check-in has no Nurse review Task;
- terminal Task Highlights remain in Glance;
- Nurse and clinician receive the same unfiltered work queue;
- a current score cannot identify its rule version/factors;
- an AI priority suggestion without exact provenance reaches the clinician queue;
- a review Task passes its deadline without one idempotent internal escalation;
- a clinician outcome path can complete without the approved two-axis label.

## Exit gate

- Every score identifies its approved rule version and exact factor arithmetic.
- Server and UI explanations agree with the persisted score.
- The approved synthetic suite exercises surfaced and unsurfaced candidates, stable ties, hard protections, resolution, rejection, and decay.
- A clinician can identify and correct a ranking decision without changing the underlying clinical record.
- Glance remains precomputed, deterministic, Provider-free, and within its existing read-path performance contract.
- Results are reported as mechanism/rule conformance, not clinical calibration or medical validation.
- Production uses 720 minutes; time-injected tests exercise a 5-minute policy at `T+4:59` and `T+5:00` without waiting.
- Nurse UI supports candidate-by-candidate verified/corrected/unable-to-verify decisions with exact source access; corrected decisions have a linked Staff Note.
- `action_required` cannot close without an executable follow-up Task assigned to the clinician or Nurse queue; time-sensitive follow-up has a due time.
- Glance UI exposes the server-persisted priority band, rule version and factor arithmetic in human-readable form.

## Final reason-code stability gate — completed 2026-09-02

Execute this only after the full F task set is complete, so it evaluates the final extraction and routing pipeline rather than an intermediate implementation. Build an independent matrix for each approved reason code covering: clear positive, negation, historical-only statement, resolved condition, ambiguous wording, patient correction, multiple people/pronouns, and source/span mismatch. Report `mock`, deterministic `fallback`, and live Provider separately; never merge them into one pass rate. The live run remains `NOT_RUN` until an explicitly authorized Provider/key is available. This gate evaluates extraction/routing stability, not medical validity; clinical thresholds remain `NEEDS_CLINICAL_INPUT`.

Final result: mock plus the Provider-independent server validator passed all
`32/32` expected outcomes; deterministic fallback carried no priority reason
code in `28/28` language cases; exact source mismatch dropped `4/4`; live
Provider is `NOT_RUN`. The first run exposed 19 false-positive mock routes in
negative/ambiguous cases. `app/priority_routing.py` now fails those codes closed
to routine Nurse review without deleting the patient report. Evidence:
`tests/test_f1_reason_code_stability.py` and
`docs/f1_a_closeout_2026-09-02.md`.

## Current evidence (2026-09-02)

- One submitted Check-in creates one stable Nurse review workflow; exact-source approved priority signals create the parallel clinician review Task.
- Role-specific, PHI-free Glance projections include excluded candidates and deterministic factor/rule metadata; terminal Tasks leave the dynamic top five.
- Nurse verification and clinician outcome/time-sensitivity completion pass RBAC, idempotency, provenance and five-minute injected-time tests.
- One `PatientReviewItem` is persisted per extracted candidate. Session completion is blocked while an item remains pending; `corrected` is rejected unless it links the deciding Nurse's non-empty Staff Note in the same Event.
- `action_required` is rejected without an active downstream `care_action`; the action may be owned by the current clinician or Nurse queue, and a time-sensitive result requires a due time.
- Real product Session journey passed with the local deterministic Provider: patient priority submission -> Nurse exact-span review -> Staff Note correction -> clinician `Corrected by Nurse` state -> Nurse-owned follow-up Task -> clinician review removed from dynamic Glance. The routine follow-up reached the Nurse Task queue but correctly remained outside Top 5 behind higher-band overdue work.
- Browser acceptance also verified the persisted `attention-v1` band, `importance-v1` factor arithmetic and rule versions in the Glance explanation UI. A workbench-remount continuity defect found during this journey was repaired and rechecked.
- Backend: 544 collected, 542 passed, 2 pre-existing local-ASR-input tests skipped. Frontend production build passed (60 modules).
- Clinical validity, real-clinician evaluation, real-time alerting, external delivery and F_A1 model training remain not established/not implemented.

## Non-goals

No medical weight guessing, clinical-risk probability, diagnosis, outcome prediction, real-time consult alerting, external notification/delivery, scheduling/shift system, model training, post-hoc feature selection, or unapproved change to the current scoring constants.
