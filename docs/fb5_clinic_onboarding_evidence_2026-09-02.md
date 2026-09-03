# F_B5 Clinic Onboarding and Settings Evidence

> Date: 2026-09-02
> Result: `IMPLEMENTED_WITH_LIMITS`
> Boundary: local synthetic-data prototype; no live Provider, external delivery,
> public organization verification or production multi-tenant certification.

## Delivered journey

1. A deployment owner generates a 24-hour, single-use `/setup#token=...` link.
2. The clinic creates its Clinic and first Admin atomically, then signs in through
   the existing server-session Login path.
3. The Admin previews and commits a strict `external_patient_id,name` CSV.
4. Valid patients are created once; invalid, duplicate and conflicting rows stay
   visible in a downloadable report and never overwrite an existing Patient.
5. The Admin invites subsequent users through the existing clinic-bound Invite
   flow.
6. AI/Voice settings inherit device defaults or use this Clinic's override;
   Clinic A cannot read or mutate Clinic B settings/import batches.

## Safety and data contracts

- Onboarding tokens are 256-bit random values; only SHA-256 hashes persist. Raw
  tokens remain in the URL fragment and are never copied into AuditLog.
- Token consumption uses a conditional update. Clinic, first Admin, Argon2id
  credential, ClinicSettings and audit commit in one transaction.
- Patient import identity is `(clinic_id, source_system, external_patient_id)`.
  Names are not auto-merged. Exact replay is unchanged; differing source data is
  a conflict requiring corrected re-import.
- Import Preview writes only the batch/report. Commit claims the batch before
  creating Patients, so repeated and concurrent commits remain idempotent.
- SystemSettings and its Provider credential remain device-owned. ClinicSettings
  contains only nullable AI/Voice overrides and optimistic-concurrency metadata.
- Consult, Check-in, Copilot and Voice configuration resolution receives clinic
  identity from the authenticated server-side resource/session path.

## Verification

- Failure-first B5 suite: **23 passed** across onboarding, patient import,
  clinic settings, migration, frontend contracts and a full Cookie Session
  integration journey.
- Full backend: **641 collected / 639 passed / 2 skipped**. The two skips are the
  existing real-local-ASR input-dependent tests and are not counted as passes.
- Frontend TypeScript/Vite production build: **passed, 64 modules transformed**.
- `A3_SCOPE_BYPASS_PASS`, `SECRET_SCAN_PASS`, `pip check`, `npm ls --depth=0`
  and `git diff --check`: passed.
- Clean/unseeded migration test creates the schema and onboarding token without
  fixture insertion; migration runs twice without duplicating ClinicSettings.
- Local browser acceptance used an isolated unseeded database and real Cookie
  Session: setup page valid, first Admin login successful, CSV showed two ready
  rows then two imported rows, clinic-local AI/Voice overrides persisted, and a
  subsequent clinician invite appeared pending. Browser warning/error log: empty.

## Honest limits

- This is deployment-issued onboarding, not public self-registration, domain
  verification, billing or a platform-admin control plane.
- Only synthetic CSV data was exercised. Real PHI governance, backup/restore and
  production operations remain outside this evidence.
- No live Provider call, Provider spend, per-clinic API key, Email/SMS/WhatsApp
  delivery, patient merge, PostgreSQL RLS, penetration test or production load
  test was performed.
- Repository changes remain local and uncommitted/unpushed.
