# Frontend Pre-visual Repair Task Card

> Status: COMPLETE — REPAIR IMPLEMENTED AND RE-VERIFIED (2026-08-28)
>
> Frozen baseline: `8f05ab48aff1d02a2767df08d2fdec362ae0667c`

## Outcome

Repair the blocking and material findings from the independent product-mode frontend acceptance before any broader visual redesign.

## Scope

- Make first-read Admin device settings initialization concurrency-safe.
- Canonicalize product login, restore, logout, and history paths by authenticated role.
- Remove the product-only 36 px clinical-shell gap.
- Protect the central reader at 1024 px without weakening the three-column desktop workspace.
- Strengthen focus visibility, small metadata legibility, and Patient mobile touch targets.
- Add regression coverage and a current evidence record without rewriting historical E5 results.

## Permanent boundaries

- Preserve Patient → Event → Artifact → exact Span.
- Do not change RBAC, clinical authority, provenance, Task authority, Provider exits, or Patient View field projection.
- Product-mode verification uses server sessions; demo headers and the role selector are not acceptance evidence.
- Historical E5 evidence remains historical. Current results belong in a separate dated repair record.

## Exit gates

1. Concurrent first Admin settings reads return the same single device row with no 500.
2. Every authenticated role has a canonical URL after login, restore, logout, revoke, and browser history changes.
3. Clinical shells use the full product viewport and retain no page-level horizontal overflow at 1440, 1280, or 1024.
4. At 1024, Event Detail uses a readable central column and bounded Context Rail.
5. Keyboard focus indicators and critical metadata are visibly legible; Patient mobile actions meet the chosen minimum touch height.
6. Full backend, focused authorization/concurrency, frontend checks, production build, dependency, secret, and diff checks pass.
7. Product-mode browser journeys pass for Clinician, Staff, Patient, and Admin using a disposable synthetic database.

## Exit evidence

- Concurrent first Admin settings reads returned 200/200 with one device row and version 1.
- Product login, restore, history correction, logout, and revoked-session recovery use canonical role paths.
- 1440×900 and 1280×800 clinical shells use the full viewport; 1024×768 Event Detail measured a 520 px main area, 469 px reader, and 280 px Context Rail with no page-level horizontal overflow.
- Patient 390×844 navigation, logout, Start, and Report done controls measured 44 px high with no page-level horizontal overflow.
- Full backend collected 524 tests: 522 passed and 2 explicit local-ASR-input tests skipped. Production build passed with 60 modules.
- D3 hard gates, D4 mock evaluation, frontend Node checks, dependencies, secret scan, and diff check passed.
- Browser console warning/error count was zero. Patient production requests remained limited to the patient-safe projection and explicitly selected Patient features.
