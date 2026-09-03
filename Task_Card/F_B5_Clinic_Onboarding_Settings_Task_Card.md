# F_B5 Task Card — Clinic Onboarding, First Admin, Patient Import, and Settings Scope

> Official scenario: 5
> Priority: B
> Status: `IMPLEMENTED_WITH_LIMITS` — owner-approved v1 implemented and verified 2026-09-02. Evidence: `docs/fb5_clinic_onboarding_evidence_2026-09-02.md`.
> Difficulty: `5/5` — identity bootstrap, migration, import conflicts, and tenant settings cross several security boundaries

## Outcome

Allow a new clinic to start using Nightingale without editing the seed fixture or
database manually:

1. create a Clinic safely;
2. create its first administrator through a trusted bootstrap path;
3. reuse the existing invite/register/session flow for later users;
4. import patients idempotently with explicit row-level errors and conflicts;
5. configure that clinic without allowing its admin to configure another clinic.

## Previous verified baseline

- The schema supports multiple Clinics and clinic-scoped Users, Patients and
  patient-bound resources.
- Database User identity, HttpOnly Session and server-side authorization are the
  trusted access path.
- An authenticated clinic Admin can create clinic-scoped, one-time user invites.
- Clinic A/B application isolation and SQLite/SQLCipher ownership controls exist
  with documented limits.
- Clinics, initial administrators and Patients still originate from fixture/manual
  setup.
- AI/Voice settings are currently a single device-level row that a clinic Admin
  can operate; no clinic override exists.

## Owner-approved v1 decisions

### 1. First-admin trust root

The deployment owner issues a random, expiring, single-use
bootstrap link. Only its hash is stored. The clinic consumes it to create the
Clinic and first Admin atomically.

This avoids public self-sign-up, which would additionally require organization
verification, email/domain ownership, abuse prevention and recovery policy.

Public self-sign-up and a platform-admin role are not part of v1.

### 2. AI/Voice settings scope

Use **device defaults + clinic overrides**.

- Device scope: installed local Voice model, hardware/runtime capability, and
  deployment-owned defaults.
- Clinic scope: whether that clinic enables online AI or Voice.
- Effective value: clinic override first, otherwise device default.
- A clinic override can disable a capability but cannot enable something the
  device does not have or deployment policy forbids.
- Until a separate platform/device-admin role is approved, clinic Admins do not
  mutate deployment-wide defaults.

Provider credentials and Voice model preparation remain deployment-owned.

### 3. Patient import identity and conflict policy

Use the following minimum CSV policy:

- require `source_system + external_patient_id` as the stable clinic-local import
  identity;
- do not match or merge Patients by display name;
- exact replay becomes `unchanged/skipped`;
- differing data for an existing external identity becomes `needs_review`;
- preserve the existing record and incoming import evidence; never silently
  overwrite or decide which source is correct;
- valid rows may commit while invalid/conflicting rows remain in the batch report.

The only accepted columns are `external_patient_id,name`; valid rows commit while
invalid/conflicting rows remain in the report.

## Minimum implementation candidate

### Clinic and first Admin

- Add a hashed, expiring, single-use clinic bootstrap record.
- Generate bootstrap authority through a deployment-owned local setup path; no
  manual database editing.
- Consume the token with a conditional update so concurrent submissions produce
  one success and one deterministic conflict.
- Create Clinic, first Admin User, Argon2id Credential, initial Clinic settings and
  metadata-only Audit in one transaction.
- Return `login_required=true`; the new Admin signs in through the existing
  Login -> server Session path.

### Later users

- Reuse the current Invite -> Register -> Login -> Session flow.
- Never let the client supply or change the invite's authoritative clinic scope.
- Preserve patient-invite binding to an existing Patient record.

### Patient import

- Provide `preview` and `commit` stages with a size/row limit and strict columns.
- Persist an import batch identity, content hash and row outcomes.
- Use a clinic-scoped unique external identity for idempotency.
- Return exact counts and row-level `imported / unchanged / invalid / conflict`.
- Never put patient row content into operational logs or metadata-only AuditLog.

### Settings

- Keep deployment defaults separate from a new clinic-keyed settings record.
- Resolve effective settings using the authoritative clinic from Session/patient
  scope, never a caller-supplied clinic id.
- Keep the one device credential deployment-owned; clinic settings contain no
  Provider secret or secret reference.
- Apply optimistic concurrency, audit changes, uniform 404, and ownership
  constraints to clinic settings.
- Update every AI/Voice call site to resolve the effective configuration for the
  current clinic.

### Product UI

- Add a bootstrap-only setup journey for clinic name and first-admin account.
- Add an Admin patient-import preview with row errors/conflicts before commit.
- Reuse the existing Admin invite experience for subsequent users.
- Show whether each AI/Voice setting is inherited or overridden and why an
  unavailable device capability cannot be enabled.

## Failure-first evidence

- Start from an unseeded schema and prove there is currently no product path to
  create the first Clinic/Admin.
- Race two submissions using the same bootstrap token.
- Replay the same import, then submit a conflicting row for the same external id.
- Attempt Clinic A Admin reads/writes against Clinic B settings and import batches.
- Demonstrate the current shared device setting blast radius before introducing
  clinic overrides.
- Inject a transaction failure and prove no half-created Clinic/Admin/import batch
  survives.

## Exit gate

- A clean, unseeded installation can create one Clinic and first Admin without
  fixture or database editing.
- Bootstrap secrets are random, hashed, expiring, single-use and concurrency-safe.
- The first Admin can log in and invite subsequent same-clinic users through the
  existing trusted identity path.
- Patient import is idempotent, produces actionable row reports, and never silently
  overwrites conflicts.
- Clinic A cannot read or change Clinic B onboarding, import, settings or
  credential metadata; absent and cross-clinic resources remain indistinguishable.
- Effective AI/Voice behavior matches the owner-approved device/clinic inheritance
  rule across at least two Clinics.
- Existing clinic fixtures and D1/F_A3 security contracts remain green after
  migration.
- Targeted tests, full backend regression, frontend production build, clean-room
  setup, and real server-session Admin journeys pass.
- Documentation distinguishes prototype onboarding from public SaaS tenant
  verification and production multi-tenant certification.

## Non-goals

No public open sign-up unless separately approved; no organization/domain
verification, billing, subscription, production RLS certification, automatic
patient-record merge, real PHI import, external Email/SMS/WhatsApp delivery,
non-email patient identity, Provider spend, or platform-admin role added by
implication.

## Integration boundary

Freeze the current F1/A working-tree baseline before implementation because B5
will touch settings, schemas, authorization, migrations and Admin UI. Do not mix
unrelated cleanup, and do not commit, merge, push, upload, configure a third-party
service, or use a live Provider without separate authorization.

## Implementation evidence — 2026-09-02

- A 24-hour fragment-token setup flow creates Clinic, first Admin, Credential,
  inherited ClinicSettings and metadata-only audit atomically; concurrent token
  consumption produces one success and one conflict, and injected failure rolls
  the entire transaction back.
- Admin patient import accepts strict UTF-8 `external_patient_id,name` CSV up to
  1 MB / 1,000 rows, previews without Patient writes, commits valid rows,
  preserves conflicts, and is idempotent for repeated and concurrent commits.
- AI/Voice runtime resolution now uses the server-authoritative clinic id.
  Clinic Admins edit only `inherit/local/deepseek` and
  `inherit/enabled/disabled`; device keys/defaults/model preparation are local
  deployment operations.
- B5-specific tests: 23 passed. Full backend: 641 collected / 639 passed / 2
  existing local-ASR-input skips. Frontend production build: 64 modules.
- Scope static gate, secret scan, dependency checks and `git diff --check`
  passed.
- Clean local browser acceptance covered setup-link recognition, first Admin
  login, two-row CSV preview/commit, clinic AI/Voice overrides and a subsequent
  pending user invite with zero browser warning/error.

## Remaining limits

- Deployment-issued onboarding is not public organization verification or a
  hosted SaaS tenant-provisioning service.
- CSV and browser evidence use synthetic data only; real PHI import operations,
  retention policy and production recovery are not certified.
- Device Provider usage was not run. No per-clinic key, billing, PostgreSQL RLS,
  platform-admin role, external delivery or automatic patient merge was added.
