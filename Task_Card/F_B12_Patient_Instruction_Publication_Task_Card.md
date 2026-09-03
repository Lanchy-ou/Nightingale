# F_B12 Task Card — Patient Instruction Publication, Correction, and Withdrawal

> Official scenario: 12, narrowed to the authenticated Patient portal
> Priority: B
> Status: `IMPLEMENTED_WITH_LIMITS` — authenticated Patient portal lifecycle implemented and verified 2026-09-02; evidence: `docs/fb12_patient_instruction_publication_evidence_2026-09-02.md`
> Difficulty: `3/5` — authority/version semantics are the primary risk

## Outcome

Give clinician-authored patient instructions an explicit publication lifecycle
so the system can answer which exact version is currently valid for the patient,
which earlier version was superseded or withdrawn, and what the patient actually
opened or acknowledged.

This is an in-product lifecycle. It does not send Email, SMS, WhatsApp or push
notifications and does not claim external delivery.

## Dependency and separation from B11

B12 defines whether an instruction version is patient-visible:

```text
draft -> published -> superseded | withdrawn
```

B11 separately records what the authenticated patient did with one published
version:

```text
available -> opened -> acknowledged
```

Implementation order is `B12 -> B11` for the combined product journey. Until
B12 exists, B11 may use the current clinician-authored Patient View allowlist as
the temporary definition of `available`, without inventing publication state.

Publication state and receipt state must never be collapsed. Acknowledgement
does not mean clinical agreement, consent, Task completion or that a withdrawn
version remains valid.

## Current verified baseline

- Clinician-authored `patient_instruction` Artifacts appear through the explicit
  Patient View allowlist.
- Copilot patient-instruction drafts require clinician editing and confirmation
  before Artifact creation.
- Artifact versions, historical snapshots, audit metadata and exact provenance
  already exist.
- A newer instruction may become the current Patient View summary, but the old
  instruction has no explicit `superseded` or `withdrawn` state.
- There is no external notification/delivery implementation.

## Discussion gates

1. Confirm whether v1 allows only clinicians to publish/correct/withdraw, with
   staff read-only.
2. Confirm that correction creates a new instruction Artifact/version target
   and never overwrites the patient-visible historical wording.
3. Confirm withdrawal reason codes and whether free-text rationale is stored in
   a clinician-authored note rather than lifecycle metadata.
4. Confirm that only one current published instruction is allowed per chosen
   scope (patient, Event, or instruction lineage). Recommended v1: explicit
   instruction lineage, not one global instruction per patient.
5. Confirm patient wording for superseded/withdrawn history. Recommended v1:
   active Patient View hides withdrawn content while retaining an audit/history
   surface for authorized clinical users.

## Owner-approved v1 decisions — 2026-09-02

- Clinicians publish, correct and withdraw; staff receive clinic-scoped read-only status.
- A correction creates a new immutable `patient_instruction` Artifact in the
  same lineage and immediately supersedes the prior published revision.
- Withdrawal metadata accepts only `entered_in_error`, `no_longer_applicable`
  or `replaced_elsewhere`; detailed rationale belongs in a clinician note.
- Current publication is enforced per explicit instruction lineage, not as one
  global instruction per Patient or Event.
- Draft, superseded and withdrawn wording is hidden from active Patient View;
  authorized clinical users retain Artifact, publication, receipt and audit history.

## Minimum candidate design

- Add an explicit instruction lineage/version identity and publication state.
- Draft content remains invisible to Patient View.
- Publishing binds actor, time, source Artifact/version and provenance.
- Correcting creates a new version target and atomically marks the previous
  published version `superseded`.
- Withdrawing removes the version from active Patient View without deleting the
  Artifact, receipt history, versions or audit evidence.
- Publishing a new version creates a new B11 receipt target beginning `Not viewed`.
- Withdrawing an acknowledged version preserves `opened_at`/`acknowledged_at`
  while making the publication state authoritative: withdrawn stays withdrawn.
- “Notify” means an in-product new/unread Patient portal indicator only.

## Failure-first evidence

- Prove a draft cannot appear in Patient View.
- Attempt publish/correct/withdraw as patient, staff, cross-clinic clinician and
  wrong-clinic Admin.
- Correct an acknowledged v1 and prove v2 starts unviewed while v1 history stays.
- Withdraw before and after acknowledgement and prove neither path deletes
  receipt/version/audit evidence.
- Replay publish/correct/withdraw requests and prove deterministic idempotency or
  version conflict behavior.

## Exit gate

- Draft/published/superseded/withdrawn states are explicit and server-enforced.
- Only the current published version appears in active Patient View.
- Correction and withdrawal never rewrite/delete historical content or receipts.
- B11 status is bound to the exact published version.
- Clinical and patient server-session journeys show publish -> open -> acknowledge
  -> correct -> new unviewed version -> withdraw.
- Targeted/full backend tests, frontend build, RBAC, version/provenance and audit
  regressions pass.
- Readiness documentation still reports external delivery as `NOT_IMPLEMENTED`.

## Non-goals

No Email/SMS/WhatsApp/push, public magic link, appointment system, electronic
signature, treatment consent, automatic clinical approval, Task completion,
external recall guarantee, real-time alerting or model training.

## Completion evidence — 2026-09-02

- Added exact Artifact-version publication records with independent
  `draft`, `published`, `superseded` and `withdrawn` states plus lineage revision.
- New patient instructions are drafts. Publishing is the only operation that
  creates a B11 `Not viewed` receipt and makes the exact version patient-visible.
- Correction uses a stable client operation id, preserves old content and B11
  acknowledgement, creates a new published Artifact/revision and a fresh receipt.
- Withdrawal hides active content while retaining the Artifact, versions,
  receipts and metadata-only audit history. Replays are idempotent; conflicting
  payload/reason replays fail with 409.
- Patient aggregates, direct patient Artifact lists and patient-visible counts
  filter on exact-version `published` state. Current-instruction decay protection
  also follows publication authority.
- Clinician UI provides publish/correct/withdraw controls and lineage history;
  staff is read-only. Copilot confirmation now creates a clinic draft rather
  than claiming immediate patient visibility.
- Failure-first and final tests cover RBAC, draft leakage, publish, correction,
  withdrawal before/after acknowledgement, audit privacy, migration and B11 linkage.
- Browser journey verified draft hidden -> publish -> patient acknowledge ->
  correction starts Not viewed -> withdrawal hides it while clinical history remains.
- External Email/SMS/WhatsApp/push delivery remains `NOT_IMPLEMENTED`.
