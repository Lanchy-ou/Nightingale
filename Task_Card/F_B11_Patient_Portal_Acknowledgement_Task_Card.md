# F_B11 Task Card — Patient Portal Visibility and Acknowledgement

> Official scenario: 11, narrowed to the in-product patient portal
> Priority: B
> Status: `IMPLEMENTED_WITH_LIMITS` — in-product receipt journey complete; external delivery remains out of scope
> Difficulty: `2/5` — small vertical feature, but RBAC and state semantics remain hard gates

## Outcome

Let a clinician know whether a patient-facing instruction has been available in
the Patient portal, opened by the authenticated patient, and explicitly
acknowledged by that patient.

The clinician should be able to distinguish:

- `Not viewed` — the instruction is visible in the portal but has not been opened;
- `Viewed · awaiting acknowledgement` — the patient opened it but did not confirm receipt;
- `Acknowledged` — the patient explicitly confirmed that they received/read it.

This is an in-product receipt workflow. It is not proof that an external message
was sent or delivered.

## Owner-approved scope decision

- Do not build Email, SMS, WhatsApp, provider webhooks, background send workers,
  bounce handling, or external retries in this card.
- Do not create a generic external `Delivery` abstraction merely for future use.
- Patient login and the existing Patient View remain the trusted identity boundary.
- External delivery remains `NOT_IMPLEMENTED`, not a hidden mock and not fake success.
- The first implementation target is `patient_instruction`. Existing Care Task
  lifecycle already records patient action separately and must not be duplicated.

## Current verified baseline

- Clinician-authored `patient_instruction` Artifacts already appear through the
  explicit Patient View allowlist.
- Patient View is available only to the patient-role user bound to that Patient.
- Care Tasks already distinguish patient `reported_done` from clinic-confirmed
  `completed`.
- There is no persisted per-instruction viewed/acknowledged state.
- Loading an aggregate API response is not currently evidence that the patient
  actually opened a specific instruction.

## Minimum design

Add one instruction-specific receipt record bound to:

```text
clinic_id + patient_id + instruction_artifact_id + artifact_version
```

Minimum state:

```text
available -> opened -> acknowledged
```

Required metadata:

- `opened_at`;
- `acknowledged_at`;
- the authenticated patient user responsible for each action;
- metadata-only audit actions, never copied instruction text.

Rules:

- A normal GET/prefetch must not silently mark an instruction as opened.
- Opening is recorded only after that exact instruction is rendered for the
  authenticated patient through an explicit idempotent mutation.
- Acknowledgement is an explicit patient action and is also idempotent.
- Acknowledgement means “I received/read this information”; it is not clinical
  agreement, consent, treatment completion, or Task completion.
- A new instruction version is a new receipt target and starts unviewed. The old
  version's receipt history remains retrievable.
- Clinic-facing status is read-only and clinic-scoped. Cross-clinic and
  not-own-patient requests retain uniform 404 behavior.

## Product changes

### Patient View

- Show a clear new/unread state for the current instruction.
- Record `opened` when the patient deliberately opens that instruction.
- Provide one clear `Acknowledge` action.
- After acknowledgement, show when it was acknowledged.

### Clinical workspace

- Show `Not viewed`, `Viewed · awaiting acknowledgement`, or `Acknowledged`
  beside the relevant patient instruction.
- Link the state to the exact instruction/version rather than to the Patient as
  a whole.

## Failure-first evidence

- Prove that the current system cannot persist whether a patient opened or
  acknowledged an instruction.
- Attempt to open/acknowledge another patient's or another clinic's instruction.
- Load/prefetch Patient View without opening the instruction and prove it remains
  unviewed.
- Edit an instruction and prove the old receipt cannot make the new version look
  acknowledged.

## Exit gate

- The three user-visible states are persisted and resolve to the exact
  instruction version.
- Only the bound patient can record open/acknowledge actions.
- Repeated open/acknowledge requests are idempotent and do not duplicate audit
  history incorrectly.
- Clinician/staff visibility is clinic-scoped and read-only.
- Patient and clinician server-session browser journeys demonstrate the complete
  transition from unviewed to acknowledged.
- Targeted tests, full backend regression, frontend production build, and
  relevant RBAC/state-isolation regressions pass.
- Readiness documentation still reports Email/SMS/WhatsApp delivery as
  `NOT_IMPLEMENTED`.

## Non-goals

No Email, SMS, WhatsApp, push notification, tracking pixel, public magic link,
appointment system, new Care Task lifecycle, clinician publish/withdraw/correct
workflow, external-delivery claim, or patient clinical-consent claim.

The separate scenario 12 publication/correction/withdrawal lifecycle is not
absorbed into this card.

## Completion evidence — 2026-09-02

- Added an exact-version `patient_instruction_receipts` record with persisted
  `available -> opened -> acknowledged` state and patient actor/timestamps.
- Patient View GET/prefetch remains read-only. Explicit open and acknowledge
  mutations are idempotent and write metadata-only audit actions.
- Only the bound patient can mutate a receipt. Clinician/staff receive a
  clinic-scoped read-only history; Admin and out-of-scope identities fail closed.
- Patient UI hides instruction wording until deliberate open, shows all three
  states, and states that acknowledgement is not consent or Task completion.
- Clinical Event Detail shows the receipt beside the exact Artifact version.
- Failure-first and final targeted tests cover prefetch, RBAC, idempotency,
  audit content, migration, and v1 acknowledged -> v2 unviewed history.
- Browser journey verified patient `Not viewed -> Viewed -> Acknowledged`, then
  clinician `Version 1: Acknowledged` on the same synthetic instruction.
- External Email/SMS/WhatsApp delivery, retry, bounce and escalation remain
  `NOT_IMPLEMENTED`; B12 publication/correction/withdrawal remains separate.
- B12 now supplies the publication authority: only an exact `published`
  instruction version can create or mutate a B11 receipt.
