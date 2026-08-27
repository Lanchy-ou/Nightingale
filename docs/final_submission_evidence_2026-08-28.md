# Nightingale Final Submission Evidence Manifest — 2026-08-28

> Overall status: **NOT SUBMISSION READY — NEEDS_OWNER_INPUT**
>
> This manifest records observed executable evidence. It does not convert a design, mock result, fallback result, historical result, skipped test, missing link, or missing video into a successful current run.

## 1. Git lineage

- Original Phase E baseline: `7b6da1d63245f45c60143e3a1bd6ac6b406255e4`
- Patient Multi-turn Check-in feature: `b4a5d21` (`feat(patient): add bounded multi-turn check-in`)
- Check-in no-fast-forward merge on main: `25a1dc9f7ac46eca048c217486e52b7ebf4b2cbb`
- E5 package commit: `b0bef9d65b58ccdd5fa2ab79b8ffc6d4302faef2` (`docs(submission): finalize Nightingale submission package`).
- `origin/main` before E5: `7b6da1d63245f45c60143e3a1bd6ac6b406255e4`

The Check-in branch was verified to have the expected baseline and no E5/unrelated changes before its feature commit. `origin/main` was fetched after the feature commit and had not drifted, so the authorized normal `--no-ff` merge proceeded. No rebase, force push, amend, or history rewrite was used.

## 2. Environment

- Date/time zone: 2026-08-28, Asia/Singapore
- OS: Windows 11 (`10.0.22000`)
- Python: 3.13.5
- Node.js: 24.15.0
- npm: 11.12.1
- FastAPI: 0.141.1
- SQLAlchemy: 2.0.52
- Pydantic: 2.13.4
- SQLite: 3.50.2
- SQLCipher: 4.12.0 community
- Caddy: 2.11.4
- Frontend build: Vite 5.4.21, 59 transformed modules

## 3. Capability status freeze

| Capability | Status | Evidence boundary |
|---|---|---|
| E1 Role workspaces | `IMPLEMENTED_AND_VERIFIED` | Nurse/staff, clinician, admin, patient workspace/RBAC/state-isolation tests and full regression pass. |
| E2 Self-Learning Importance | `IMPLEMENTED_AND_VERIFIED` | Bounded same-clinic entity-type feedback, caps/protections, 18-case test suite, no clinical-learning claim. |
| E3 Data Decay | `IMPLEMENTED_AND_VERIFIED` | Protection-first shadow payload, round-trip/provenance/idempotency tests and current local maintenance harness. No total-storage-savings claim. |
| E4 Voice | `IMPLEMENTED_WITH_LIMITS` | Default-off local lifecycle/RBAC/review/backup contracts pass. Two current real-local-ASR tests skipped because ignored model/audio inputs are absent. Historical synthetic local slice only. |
| Patient Multi-turn Check-in | `IMPLEMENTED_AND_VERIFIED` | 29 targeted tests, full backend, browser runtime journey, mock/fallback, concurrency, raw-first, RBAC, safety, exact provenance. |
| E5 Submission Package | `NOT COMPLETE` | README/PDF/attribution/evidence/runbook/email draft can be completed; submitter identity, actual video/playback, and external access remain owner inputs. |

## 4. Patient Multi-turn Check-in independent review

Blocking findings were reproduced with regression tests before fixes:

1. explicit safety negations could false-escalate;
2. a free supplement could receive a repeated question type;
3. Provider output could cite an older patient message and ignore the newest one;
4. common diagnose/stop/double-dose/test-result requests needed deterministic refusal coverage;
5. concurrent start/save/process and rapid UI actions needed stronger idempotency guards;
6. repeat submit was not idempotent;
7. hidden drafts leaked existence through permission/source-ingest branching;
8. Copilot evidence-row deduplication contained an indentation regression;
9. deterministic Summary text could omit a late correction after four messages.

Repairs include narrow explicit-negation handling, non-repeating question planning, newest-message Provider reference enforcement, deterministic medical-request fallback, concurrency/idempotency recovery, submit replay, scope-before-visibility-before-permission ordering, generic source-ingest draft hiding, synchronous frontend in-flight/request-generation guards, and all-message correction-preserving summaries.

Runtime browser QA used a fresh synthetic database and verified rapid double-send, refresh restore, adaptive supplement response, Task narrative, medical-advice refusal, four-question cap, return/correct, rapid double-submit, history, safety negation, deterministic safety stop, clinical Timeline/Event Detail, patient/AI separation, exact patient sources, and role-switch draft clearing. Browser console warnings/errors: 0. Horizontal overflow: false.

## 5. Automated tests and builds

### Backend full

Command:

```text
backend\.venv\Scripts\python.exe -m pytest
```

Observed after the E5 package commit: **509 passed, 2 skipped, 1 cache warning, 64.65 s**.

The warning was an environment permission issue creating pytest cache/cleanup paths; the test process exited 0. The two skips were re-run with `-rs` and are exactly:

- local ASR smoke requires explicit ignored model and synthetic audio paths;
- local ASR endpoint journey requires explicit ignored model and audio paths.

### Check-in targeted

```text
backend\.venv\Scripts\python.exe -m pytest tests -k patient_checkin -q
```

Observed: **29 passed**. Collection by file: lifecycle 10; safety/Provider 9; RBAC 3; frontend contract 3; Provider/redaction 2; security 1; integration 1.

### Security/integration

```text
backend\.venv\Scripts\python.exe -m pytest tests\security tests\integration -q
```

Observed: **22 passed**.

### E1–E4 targeted

The role-workspace, Nurse Consult, self-learning, data-decay/archive, phase-E, and Voice selection completed with all selected key-free tests passing and the same two explicit real-local-ASR skips. Full backend evidence above is authoritative for the total.

### Required original micro-tests

RBAC scope, revision history, Highlight provenance, concurrent edits, and Self-Learning Importance are included in the 509-test full pass.

### Frontend

```text
node tests/transcriptRange.test.mjs
node tests/voiceCapture.test.mjs
node tests/patientCheckIn.test.mjs
npm run build
npm ls --depth=0
```

Observed: all **3 Node checks passed**; TypeScript/Vite production build passed with **59 modules**; dependency tree resolved without missing/extraneous top-level dependencies.

The first sandboxed build attempt failed only because TypeScript could not write `tsconfig.tsbuildinfo` (`EPERM`). A writable rerun passed. This is recorded, not hidden.

## 6. D3 and D4 evaluations

### D3 corpus validation

```text
backend\.venv\Scripts\python.exe scripts\evaluate_transcripts.py --validate-corpus
```

Observed: `CORPUS_VALIDATION_PASS`; 40 cases; development 26 / frozen holdout 14; manifest hashes 40/40; frozen digest `e2b429ff98cfc802b307c7de46f4ffa0006e12211cce7efaf37799b762a4d962`.

### D3 deterministic runtime

```text
backend\.venv\Scripts\python.exe scripts\evaluate_transcripts.py --evaluate-runtime
```

Observed: `HARD_GATES_PASS`; known-PHI unredacted payload 0; silent speaker invention 0; silent truncation 0; fallback unanchored candidate 0. The runner reports `PROVIDER_LAYER_NOT_RUN` and `DETERMINISTIC_FALLBACK_REPORTED_SEPARATELY`.

### D4 Copilot frozen eval

```text
backend\.venv\Scripts\python.exe -B scripts\evaluate_copilot.py
```

Observed after the E5 package commit: `D4_COPILOT_EVAL_PASS`; Provider `mock`; four questions; AI self-citation rejected; forged confirmation rejected. Reported Copilot read-path P50/P95: 17.115/57.243 ms (not Glance latency).

## 7. Provider, fallback, and ASR separation

| Layer | Current result |
|---|---|
| Check-in `mock` | Full bounded journey passed in automation and browser runtime. |
| Check-in deterministic fallback | Provider error/missing/invalid schema, raw-first persistence, bounded medical refusal, and exact submitted provenance passed. |
| Check-in DeepSeek live | An unrestricted-network synthetic smoke reached a non-degraded live turn. The strict final Summary failed schema/validation and the server used deterministic fallback. **Full live Check-in journey: `LIVE_NOT_VERIFIED_CURRENT`.** |
| First sandboxed DeepSeek attempt | Provider error/fallback, consistent with restricted network; not treated as a live result. |
| D3 live Provider layer | `NOT_RUN` by frozen-runner design. |
| E4 mock ASR | Key-free lifecycle tests passed; test-only, not a product Provider claim. |
| E4 local faster-whisper | Historical dated synthetic slice exists. Current final run: two real-ASR tests skipped for absent ignored inputs. |
| Physical microphone, diarization, clinical/noisy accuracy | `NOT_RUN`. |

No Provider/API key, raw Provider payload, model weight, or raw patient text was written to logs/evidence.

## 8. Performance and E3 maintenance evidence

`measure_glance.py` used a throwaway seeded SQLite database, 10 warm-ups, and 100 samples per endpoint.

| Endpoint | Layer A P50/P95 | Layer B P50/P95 |
|---|---:|---:|
| Glance | 4.026 / 4.626 ms | 4.402 / 5.115 ms |
| Events | 7.289 / 8.030 ms | 7.155 / 8.189 ms |
| Patient View | 5.867 / 6.521 ms | 5.727 / 6.434 ms |

The first sandboxed measurement completed but could not write `backend/docs/perf_baseline.md`; the writable rerun succeeded. These are local single-user synthetic results, not production capacity.

`measure_storage_policy.py` observed: dry run 12.1761 ms; first apply 9.7958 ms; identical rerun 4.3934 ms; 1,000 archive build/restore samples P50/P95 0.0256/0.0326 ms; one sample 235 original bytes / 180 compressed bytes; tiers hot/warm/cold 12/1/1. Authoritative content coexists with the shadow payload, so this is not total database savings.

## 9. SQLCipher and Caddy evidence

SQLCipher init, separately keyed backup, and rotated-key restore each passed with:

- SQLCipher 4.12.0 community;
- 18 tables;
- `plaintext_header=false`;
- `plain_reader_blocked=true`.

Caddy 2.11.4 validation returned `Valid configuration`.

The current secure Demo was actually started and `verify_secure_demo.py` returned `SECURE_DEMO_VERIFICATION_PASS`:

- HTTP 301 to `https://127.0.0.1:8443/probe`;
- TLSv1.3 / `TLS_AES_128_GCM_SHA256`;
- verified local-CA chain and non-expired certificate;
- frontend 200;
- anonymous API 401;
- CSRF without Origin 403;
- product login 200;
- Secure + HttpOnly + SameSite=Lax cookie;
- allowed preflight 204 / denied preflight 403;
- logout 200 / after-logout access 401;
- all required security headers present.

No CA trust-store installation or TLS bypass was performed. Temporary SQLCipher databases/backups/restores were checked by exact path and removed individually. Caddy local state is ignored and not tracked.

## 10. Dependencies, secrets, private assets, and language audit

- `pip check`: no broken requirements.
- `npm ls --depth=0`: resolved.
- `backend/scripts/check_no_secrets.py`: `SECRET_SCAN_PASS` before E5; rerun after final commit is required below.
- Duplicate `faster-whisper==1.2.1` line was mechanically removed from `backend/requirements.txt`; dependency scope did not change.
- Human-readable repository documents and product UI copy were converted to English.
- Remaining Chinese text is intentional synthetic D3 bilingual/unknown-label test input in two frozen JSON cases and their two corresponding regression tests. It is not user-facing documentation.
- No tracked secret, Provider key, `.env`, private DB/backup, raw recording, real patient data, Caddy binary/state/key, or model weight is permitted.

## 11. Technical Brief

- Path: `output/pdf/Nightingale_Technical_Brief.pdf`
- Format: PDF 1.4, US Letter
- Page count: **3**
- Content: product/architecture/trust boundaries; comprehensive schema/RBAC/Check-in provenance; evidence/status/Provider/ASR/Submission gate.
- Render: all three pages rendered at 160 DPI and visually inspected.
- QA: no clipped text, overflow, broken characters, or unsupported metric found. An initial page-2 bottom overlap was found, fixed, re-rendered, and re-inspected.
- Assets: ReportLab built-in fonts and code-drawn vector shapes only; no external image/font/stock asset.

## 12. Repository/link/video/access checks

- Repository configured remote: `https://github.com/Lanchy-ou/Nantingale`.
- Unauthenticated HTTP check returned **404**, and public search did not discover this repository. Therefore recipient/submission-context access is **not verified** and repository visibility/access must not be changed without owner authorization.
- Local submission zip: generated only after the final commit; upload/link remains owner-controlled.
- Demo Video: **no file or link is present**. Full playback, duration, resolution, audio, journey coverage, and external access are `NOT_RUN`.
- Email: draft prepared but not sent.
- Upload/share/publication/visibility change: not performed and not authorized.

## 13. NEEDS_OWNER_INPUT

1. Exact submitter name for the required subject and signature.
2. Actual 6–9 minute Demo Video file or link, recorded in product session mode and played from start to finish.
3. Verification that the video visibly includes Patient Multi-turn Check-in, clinician review, and exact provenance.
4. A repository or zip delivery path accessible to the intended recipient from the submitter's intended account/context.
5. Final attachment/link check from that account/context.
6. Separate explicit authorization before sending email, uploading/sharing files, publishing the repository, or changing access/visibility.

## 14. Final Git and verification attestation

Package attestation at the time this evidence-only update was prepared:

- package commit: `b0bef9d65b58ccdd5fa2ab79b8ffc6d4302faef2`;
- package commit full backend: 509 passed / 2 explicit local-ASR-input skips;
- package commit security/integration: 22 passed;
- package commit D3: corpus validation and deterministic runtime hard gates passed; Provider layer `NOT_RUN`;
- package commit D4: frozen mock eval passed;
- package commit frontend: three Node checks and 59-module production build passed;
- package commit dependencies/secret: `pip check`, `npm ls --depth=0`, and `SECRET_SCAN_PASS`;
- PDF: 3 pages, rendered and visually inspected;
- final evidence-only attestation commit: the commit containing this section and `.gitattributes`;
- final local/remote hashes, worktree status, and submission zip SHA-256: recorded after this attestation commit and push in the final report.

Because a commit cannot contain its own hash, the immutable package commit above is the hash tested before this evidence-only attestation commit. The final report separately states the final local/remote attestation hash. No history rewrite is used.

## 15. Submission Ready decision

**NOT SUBMISSION READY.** All executable repository gates may pass, but required manual identity, video/full-playback, and recipient-access evidence are missing. Documentation and browser QA are not substitutes.
