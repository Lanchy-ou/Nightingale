# Frontend Pre-visual Repair Evidence — 2026-08-28

> Status: `REPAIR_IMPLEMENTED_AND_REVERIFIED`
>
> This record is additive. It does not rewrite the historical E5 evidence or convert mock, fallback, skipped, historical, or NOT_RUN layers into current live evidence.

## Baseline and scope

- Frozen committed baseline: `8f05ab48aff1d02a2767df08d2fdec362ae0667c` (`feat: add admin AI and voice settings`).
- Verification target: the uncommitted repair working tree described by `Task_Card/Frontend_Previsual_Repair_Task_Card.md`.
- Existing repository database was not reseeded or overwritten. Browser writes used a disposable synthetic database outside the repository.
- No commit, merge, rebase, push, upload, sharing, or email action was performed.

## Repairs verified

1. Admin device settings first-read initialization uses one atomic SQLite/SQLCipher-compatible insert with conflict-ignore. Two concurrent HTTP reads returned 200/200, version 1, with one device row.
2. Product login and restore canonicalize Clinician/Staff to `/clinical`, Patient to `/patient`, and Admin to `/admin`; logout, revoked sessions, and wrong-role history paths resolve without retaining protected UI state.
3. Product clinical shells use the full viewport. The 36 px offset remains limited to the explicit Demo toolbar layout.
4. At 1024×768 the clinical main area measured 520 px, Event reader 469 px, and Context Rail 280 px. Event Detail stacks its lifecycle and reader; page-level horizontal overflow was false.
5. Focus styles use a solid high-contrast ring on light surfaces and a white ring in the dark clinical sidebar. Critical lifecycle/source metadata uses stronger colors and larger text.
6. At 390×844 Patient navigation, logout, Start, and Report done controls measured 44 px high; horizontal overflow was false.
7. The current repair has its own Task Card and evidence record. Historical E5 counts remain historical.

## Automated evidence

- Full backend: 524 collected; 522 passed; 2 skipped; exit 0.
- Skips: the two real-local-ASR tests requiring explicit ignored model and synthetic audio paths.
- Security/integration/auth/RBAC/Admin/frontend-contract selection: all selected tests passed.
- Frontend: transcript range, Voice state, and Patient Check-in Node checks passed; TypeScript passed.
- Production build: Vite 5.4.21; 60 modules; exit 0.
- D3: 40/40 manifest hashes; corpus validation passed; deterministic runtime hard gates passed; Provider layer `NOT_RUN`.
- D4: frozen Copilot evaluation passed with `provider=mock`.
- `pip check`, `npm ls --depth=0`, secret scan, and `git diff --check`: passed.
- Pytest emitted a Windows temporary-directory cleanup PermissionError after the completed run; process exit remained 0 and no test failed.

## Product-mode browser evidence

- `VITE_DEMO_AUTH` and `NANTINGALE_DEMO_AUTH` were disabled.
- Clinician: canonical `/clinical` login, Glance, Timeline, Event Detail, full-height shell, and 1440/1280/1024 layouts passed.
- Staff: canonical `/clinical`; Nurse workspace visible; Copilot and Doctor controls absent.
- Patient: canonical `/patient`; 390×844 passed; no internal clinical UI. Production network loaded only `patient-view` until the user explicitly opened another Patient feature.
- Admin: canonical `/admin`; AI & Voice Settings loaded without error; wrong-role `/clinical/...` navigation corrected to `/admin`.
- Revoked Admin session: refresh returned the login page at `/login`; protected Admin and patient content were absent.
- Browser console warnings/errors: 0.

## Evidence-layer separation

- Browser runtime AI: Local deterministic.
- D4 frozen evaluation: mock.
- Deterministic fallback: covered by existing automated tests and D3 runtime reporting.
- DeepSeek live: NOT_RUN in this repair.
- D3 Provider layer: NOT_RUN by frozen-runner design.
- Real local ASR: NOT_RUN in this repair; two explicit input-dependent skips.
- Physical microphone, diarization, clinical accuracy, production capacity, and human clinical usability: NOT_RUN.

## Decision

The blocking Admin settings race and the reported routing/layout/accessibility defects are repaired. No P0/P1 blocker was observed in the repaired product-mode baseline. The project may enter a separately discussed visual-optimization phase, while the established medical authority, provenance, RBAC, Patient View, and evidence boundaries remain frozen.
