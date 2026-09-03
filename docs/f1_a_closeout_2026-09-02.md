# F1 / A-Stage Closeout — 2026-09-02

Status: `F1_A_COMPLETE_WITH_LIMITS`

This closes the owner-approved A1–A5 implementation and acceptance scope. It
does not start B/C work, authorize model training, claim medical validity, use a
live Provider, commit/push the working tree, or perform external delivery.

## Exit-gate result

- F_A1–F_A5 each have an owner-approved design and a recorded implementation.
- Final D-safeguard regression review passed after all A changes.
- A/D targeted regression: `124 passed`.
- Full backend: `611 collected`; `609 passed`, `2 skipped` existing local-ASR-input tests.
- Frontend production build: passed; `62 modules transformed`.
- `git diff --check`: passed. Secret scan: `SECRET_SCAN_PASS`.
- Real server-session browser acceptance passed for Patient, Nurse, Clinician
  and Admin workspaces with zero browser warning/error.
- Live DeepSeek and a real external Provider timeout remain `NOT_RUN`; mock,
  deterministic fallback, local hanging-network and live evidence are never merged.

## Final reason-code stability matrix

Approved codes:

1. `patient_explicit_worsening`
2. `patient_explicit_severe_intensity`
3. `patient_requests_urgent_contact`
4. `patient_reports_medication_or_allergy_concern`

Each code is tested against clear positive, negation, historical-only,
resolved, ambiguous, patient correction, multiple people/pronouns and exact
source/span mismatch.

| Evidence layer | Result | Meaning |
|---|---:|---|
| Mock + server validator | `32/32` expected outcomes | Explicit current self-report routes; ambiguous/non-current/mismatched wording fails closed to routine Nurse review |
| Deterministic fallback | `28/28` language cases carried no priority code | Fallback never creates clinician-priority routing |
| Exact source/span mismatch | `4/4` dropped | No code survives a quote that is absent from the patient source |
| Live Provider | `NOT_RUN` | No authorized live key/spend; no live pass rate is claimed |

The first independent run exposed 19 false-positive mock routes across the 28
negative language cases. `backend/app/priority_routing.py` now performs a
Provider-independent, exact-source, fail-closed validation before review Task
routing. Rejected codes do not delete or hide the patient report; the submission
still creates routine Nurse review. Direct patient medication/dose help requests
remain eligible for priority review while the Check-in response continues to use
the deterministic medical-advice refusal.

This matrix evaluates rule/workflow conformance only. Clinical thresholds and
medical validity remain `NEEDS_CLINICAL_INPUT`.

## Final 16-scenario ledger

| # | Status | First visible break / remaining limit | Improvement retained |
|---:|---|---|---|
| 1 | `NOT_IMPLEMENTED` | Patient access still requires email/password | Product identity is server-session and patient-bound; no fake phone/WhatsApp path |
| 2 | `IMPLEMENTED_WITH_LIMITS` | No PostgreSQL RLS or production multi-tenant certification | Scoped loaders, uniform 404, SQLite/SQLCipher ownership constraints and clinic-isolation tests |
| 3 | `IMPLEMENTED_WITH_LIMITS` | Host retention, crash monitoring and Provider retention are not established | Allowlisted/scrubbed operational logging, edge-log boundary and fixed failure codes |
| 4 | `IMPLEMENTED_AND_VERIFIED` | No production PHI redaction certification | Raw-first persistence and deterministic redaction before the single LLM egress |
| 5 | `IMPLEMENTED_WITH_LIMITS` | No clinic onboarding, first-admin bootstrap or patient import | Device-level AI/Voice settings and secure key verification exist |
| 6 | `IMPLEMENTED_WITH_LIMITS` | Malay-English-Hokkien clinical evaluation is `NOT_RUN` | Unicode transcripts and a multilingual local adapter preserve entered text |
| 7 | `NOT_IMPLEMENTED` | No streaming ASR or in-consult alert surface | Post-consult processing remains honestly labelled |
| 8 | `IMPLEMENTED_WITH_LIMITS` | Real external timeout is `NOT_RUN` | 30 s total deadline, phase bounds, async cancellation, raw preservation and distinct fallback |
| 9 | `IMPLEMENTED_AND_VERIFIED` | Live Provider error rates are not measured | Returning errors/invalid output enter clearly labelled deterministic fallback |
| 10 | `IMPLEMENTED_AND_VERIFIED` | No distributed multi-writer certification | Optimistic compare-and-swap, deterministic 409, versions/diff/revert and refresh/retry UX |
| 11 | `NOT_IMPLEMENTED` | No email/SMS/WhatsApp send, retry or receipt lifecycle | UI does not pretend that instructions or links were externally delivered |
| 12 | `IMPLEMENTED_WITH_LIMITS` | No publish/withdraw/correct/notify/acknowledge lifecycle | Clinician edit/confirmation gate exists for patient instructions |
| 13 | `IMPLEMENTED_AND_VERIFIED` | English bounded assertion extraction is not clinical NLP validation | Allergy conflicts preserve both sources, mark review and surface exact provenance |
| 14 | `IMPLEMENTED_WITH_LIMITS` | No medical calibration or clinical-risk probability | Explainable deterministic priority bands, factor arithmetic and correction workflow |
| 15 | `IMPLEMENTED_WITH_LIMITS` | No trained/served learning model or real-clinician label volume | Auditable Shadow decisions, unsurfaced coverage, freeze/replay/rollback; serving remains base-only |
| 16 | `IMPLEMENTED_AND_VERIFIED` | No production archival/disaster-recovery certification | Source version + quote hash, historical resolution and fail-closed mismatch behavior |

## D-safeguard final review

- Scenario 4 redaction-before-Provider: `SURVIVES`.
- Scenario 9 returning-error fallback: `SURVIVES`.
- Scenario 10 concurrent note conflict and retry: `SURVIVES`.
- Scenario 13 allergy contradiction preservation/review: `SURVIVES`.
- Scenario 16 immutable source binding and historical resolution: `SURVIVES`.

## Repository and delivery status

- Branch at closeout: `main`; HEAD `31a2d75bdaa78f74044e6f308907e1a31408f07b`.
- Local tracking state: two commits ahead of the currently recorded
  `origin/main` ref; no network fetch was performed to refresh that ref.
- A5, reason-code and closeout changes remain uncommitted in the working tree.
- Unrelated untracked `output/docx/`, `output/interview/` and `tmp/` content was
  preserved and excluded from F1/A work.
- No commit, push, release, upload, email or other external delivery was performed.

F1/A is therefore complete within the approved synthetic prototype scope, with
the remaining B/C/productization and `NOT_RUN` evidence explicitly preserved.
