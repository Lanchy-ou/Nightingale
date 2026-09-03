# F_B12 Patient Instruction Publication Evidence — 2026-09-02

## Verified outcome

The authenticated Patient portal now has two separate, version-bound state
machines:

```text
clinical authority: draft -> published -> superseded | withdrawn
patient receipt:    available -> opened -> acknowledged
```

Only clinicians can publish, correct or withdraw. Staff can read clinic-scoped
publication and receipt status. Patient View and direct patient Artifact reads
include only exact versions whose publication state is `published`.

## Preserved boundaries

- Correction creates a new immutable Artifact in the same lineage; it does not
  rewrite historical patient wording or its receipt.
- Withdrawal removes active Patient View visibility without deleting Artifact,
  ArtifactVersion, receipt or audit evidence.
- Acknowledgement means only portal receipt/read. It is not consent, clinical
  agreement or Care Task completion.
- Email, SMS, WhatsApp, push, external delivery, external recall and escalation
  remain `NOT_IMPLEMENTED`.

## Automated evidence

- Failure-first B12 tests initially failed because publication endpoints and
  persisted authority state did not exist.
- Final B12 tests cover draft leakage, all role/scope boundaries, ownership
  mismatch, idempotent publish/correct/withdraw, conflicting replays, withdrawal
  before and after acknowledgement, audit privacy and legacy migration.
- B11, Patient View, RBAC, session routing, Copilot draft authority and data
  retention regressions pass with the B12 authority gate.
- Complete backend collection: 653 tests; 651 passed and 2 existing local-ASR
  input tests skipped.
- Frontend production build: 65 modules transformed successfully.
- `git diff --check`: passed.

## Browser evidence

A normal server-session clinician/patient journey using synthetic Alice Tan data
verified:

1. clinician-created instruction remained a clinic draft and was absent from Patient View;
2. publish created a `Not viewed` portal instruction;
3. the patient deliberately opened and acknowledged that exact version;
4. clinician correction preserved the acknowledged old revision and created a
   new `Not viewed` revision;
5. withdrawal hid the correction from active Patient View;
6. clinical Event Detail retained the withdrawn revision, fixed reason code,
   audit activity and two-revision lineage history.

## Limits

- Synthetic data and local browser only; no real patient, clinician validation,
  external delivery channel or production multi-worker certification.
- The demonstration does not prove that previously viewed content can be
  recalled from screenshots, exports or any external channel.
- No commit, push, deployment or external message was performed.
