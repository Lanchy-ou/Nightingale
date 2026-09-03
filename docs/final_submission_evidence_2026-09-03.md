# Final Repository Evidence — 2026-09-03

> Repository status: **READY WITH EXTERNAL DELIVERY LIMITS**. The code, automated tests, README, Attribution, and three-page Technical Brief are repository-complete. Demo Video playback, final email delivery, and recipient-context access remain submitter-controlled evidence outside the repository.

## 1. Scope and baseline

- Repository: `https://github.com/Lanchy-ou/Nightingale`
- Validated code/document baseline before this evidence-only closeout: `4075b9c476bc4901d025eaf15a4ba3aea93cab52`
- Data boundary: synthetic data only.
- Product boundary: prototype, not production medical software, clinical validation, regulatory evidence, or a public-host security certification.
- The supplied clinic feedback contains numbered scenarios 1–16 and a concluding cross-cutting capability checklist. The three-page Technical Brief presents that checklist as synthesis item 17 without claiming that the source contained a separately numbered scenario 17.

## 2. Repository deliverables

| Deliverable | Status | Repository evidence |
|---|---|---|
| Working application | `VERIFIED_WITH_LIMITS` | FastAPI backend, React/TypeScript frontend, canonical synthetic longitudinal fixture, role-specific workflows, exact provenance, and documented deployment boundary. |
| Automated scenario tests | `PASS` | 714 backend tests collected: 712 passed and 2 explicit local-ASR-input skips. The skipped tests passed separately when ignored synthetic model/audio inputs were supplied, as recorded in the F Final evidence. |
| Clear Git history | `PASS` | Feature, repair, and documentation work is separated into descriptive `feat`, `fix`, `docs`, and merge commits. |
| README setup/run/test instructions | `PASS` | `README.md` covers development/demo mode, product identity mode, onboarding, migrations, SQLCipher/Caddy, optional Voice, verification commands, scenario 1–16 test mapping, limits, and deliverable locations. |
| Technical Brief | `PASS` | `output/pdf/Nightingale_Technical_Brief.pdf` is exactly three rendered pages. It covers scenarios 1–16 plus synthesis item 17, current-build integration, first failures, blocked/unsuccessful attempts, assumption changes, verification, and release boundaries. |
| Attribution | `PASS` | `ATTRIBUTION.txt` lists runtime libraries, tools, Provider/model use, document-generation libraries, licenses, and non-bundled assets. |
| Continuous integration | `ADDED` | `.github/workflows/ci.yml` runs the full backend suite, dependency and secret checks, frontend contract checks/build, and a Technical Brief regeneration smoke check on pushes and pull requests. |

## 3. Observed final verification

### Backend

Command:

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest
```

Observed result:

```text
714 collected
712 passed
2 skipped
```

The two default skips require ignored local-ASR model/audio inputs and are intentional. They are not counted as live microphone, noisy-clinic, diarization, or multilingual clinical-validity evidence.

Additional observed checks:

```text
python -m pip check                 PASS — no broken requirements
python scripts/check_no_secrets.py PASS — SECRET_SCAN_PASS
```

### Frontend

Observed results:

```text
transcriptRange.test.mjs PASS
voiceCapture.test.mjs    PASS
patientCheckIn.test.mjs  PASS
TypeScript no-emit       PASS
Vite production build   PASS — 112 modules transformed
npm ls --depth=0         PASS
```

The current sandbox intercepted the canonical local `npm run build` when TypeScript attempted to rewrite the existing ignored `tsconfig.tsbuildinfo`. The same source then passed `tsc --noEmit` and a Vite production build with output redirected to a writable temporary directory. This was an environment filesystem permission boundary, not a compiler or bundle failure. CI runs the canonical command in a clean checkout.

### Repository and deliverables

```text
git diff --check                  PASS
git fsck --full                   PASS (reachable repository intact)
Technical Brief PDF page count   PASS — 3
Technical Brief rendered review  PASS — no clipping or overflow observed
```

Normal unreachable/dangling Git objects may remain from local development and do not indicate reachable-history corruption.

## 4. Scenario result summary

The authoritative detailed ledger remains `docs/real_clinic_readiness_status_2026-08-31.md`, with later implementation evidence in the F1/A, F Final, and SL1–SL3 documents.

For numbered scenarios 1–16, the current honest classification is:

```text
5 SURVIVE / 9 PARTIAL / 2 DO NOT SURVIVE
```

The cross-cutting synthesis item 17 is `PARTIAL`. The two explicit non-survivors are phone/WhatsApp-only patient access and in-consult streaming alerting. Important partial limits include host/third-party retention, database RLS, multilingual/noisy ASR validity, external delivery, medication-reference validation, ranking calibration, exposure/fatigue evaluation, and production learned serving.

## 5. External delivery boundary

The repository does not prove or store:

- final Demo Video playback, duration, audio quality, or recipient access;
- final email delivery or attachment/link access in the recipient's context;
- real patient/PHI use;
- live clinical validation, production capacity, penetration testing, or regulatory compliance.

The owner previously reported recording the Demo Video and sending a corrected follow-up email. Those statements remain owner-reported and were not independently verified by the repository checks. The two local `Nightingale_72_Hour_Build_Feedback_Completed` DOCX/PDF files are intentionally not tracked or uploaded.

## 6. Final classification

**Repository:** READY WITH DOCUMENTED LIMITS.

**External submission package:** REQUIRES SUBMITTER CONFIRMATION of Demo Video playback/access and final email/attachment delivery.

**Production/clinical readiness:** NOT CLAIMED.
