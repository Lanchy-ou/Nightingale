# Existing-feature repair evidence — 2026-09-05

Scope: four defects reproduced during the current-feature review. No navigation/layout redesign, new clinical capability, provider call, schema migration, deployment or publication is included. Validation uses disposable synthetic databases; the user's existing database is untouched.

## Reproductions and repairs

1. **Note edit conflicts lost the draft.** Previously a 409 called the parent refresh, unmounting the editor and discarding local text. The editor now keeps its draft, fetches the latest saved note through the existing scoped endpoint, and blocks saving until the user explicitly reviews it. Retry retains edited fields and adopts current content for unchanged fields, using the reviewed version as the optimistic lock. Repeated conflicts return to the same comparison flow; failed loading leaves the draft available with a retry action. Event refresh retains already loaded content, and editor identity is keyed to the Artifact.
2. **Clinician confirmation after Staff acknowledgement was a no-op.** Same-status requests now distinguish first clinician confirmation from a true duplicate. The existing status history records only actual transitions; the metadata audit records the confirmation actor and status/confirmation flags. Status plus update time guard concurrent writes, including two same-status confirmations. No new role authority or learning signal is introduced.
3. **Recency stayed true after the event aged.** The existing exact seven-day window is shared by ingestion, seeding and projection rebuilding. Record-derived Highlights use Event.started_at; Task-owned Highlights use Task.created_at so newly assigned work on an old Event can be recent. Future timestamps are excluded. The existing maintenance worker refreshes changed recency and overdue boundaries, including startup recovery; it does not recompute unchanged patients every tick. Source content, provenance, protected bands and base-only serving are preserved. The canonical seed explicitly uses its frozen SEED_AS_OF; runtime maintenance advances it to runtime time.
4. **Fixed allergy context lacked source navigation.** Each fixed allergy item now invokes the existing provenance endpoint and contextual source reader. It does not re-enter the dynamic five or lose its source-version/hash checks.

## Observed browser acceptance

Local Vite / FastAPI with mock Provider and isolated synthetic data:

- Edited the Plan in a v1 note; a parallel API request wrote both Assessment and Plan at v2. The stale browser save kept the original draft, displayed the v2 comparison and disabled Save. Explicit review retained the edited Plan, adopted the other reviewer's Assessment and enabled retry. Saving created v3 with both intended values. The original versions and conflict audit remained available.
- Created a synthetic exact-source allergy through the existing pipeline with an injected deterministic MockLLMClient. In the browser, Staff acknowledged it first; Clinician then confirmed it. It moved to fixed allergy context, whose new source button displayed the verbatim patient sentence and Event → AI Summary → raw Transcript → segment chain.
- Switching to Patient removed the clinical source panel and rendered only the independent Patient View.
- Conflict comparison was visually inspected in the existing desktop layout. This is bounded browser acceptance, not comprehensive usability or accessibility certification.

## Automated verification

- New failure-first API regressions cover Staff → Clinician accepted/pinned handoff, idempotent retries and simultaneous same-status clinician confirmations with exactly one clinician audit.
- Time tests cover future exclusion, the exact seven-day edge, one-year expiry, unchanged-patient isolation, no-op maintenance, Task due crossing and protection of a newly created Task on an old Event. The last case caught pending Task timestamps being read before flush; rebuilding now flushes the caller's pending changes before taking time snapshots.
- Legacy tests that assumed August fixture records stayed recent now establish a recent Event explicitly. The data-decay comparison uses a repeated historical item instead of falsely marking old data recent. The audit privacy test asserts the exact content-free metadata payload.
- Targeted repair/regression run: 53 passed before the final added concurrency/protection cases.
- TypeScript no-emit: passed. Existing three Node state-machine suites: passed. Vite production build: passed, 112 modules. Vite used the same React plugin/configuration in memory and a temporary output directory because the workspace restricts generated config/cache writes.
- Final backend suite: **720 passed, 2 skipped**, 722 collected, 252.33 seconds. The two skips remain the existing optional local-ASR input tests. Eight new regression cases were added. Command: `.venv/Scripts/python.exe -m pytest -p no:cacheprovider --tb=short`, with a fresh `PYTEST_DEBUG_TEMPROOT` to avoid another user's inaccessible pytest cleanup directory.
- Final `git diff --check` and secret scan: passed.
- Local HTTP Glance check on the seeded database plus the synthetic allergy: 10 warm-ups, 100 samples, P95 6.819 ms, median 5.567 ms. This excludes browser rendering and does not establish production capacity.

## Remaining boundaries

Draft recovery applies while the editor is mounted; it is not autosave across reload, patient/role switching or navigation. Maintenance is interval-based (60 seconds by default); open pages display new ordering on their next fetch. Learning remains Shadow-only. The broader UX recommendations from the review remain outside this repair scope.
