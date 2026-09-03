# F1 Task Card — Real-Clinic Feedback Hardening

> Status: `F1_A_COMPLETE_WITH_LIMITS` — A1–A5 and final D/reason-code/browser/regression closeout completed 2026-09-02. Evidence: `docs/f1_a_closeout_2026-09-02.md`.
> Revision window: 48-hour improvement period

## Outcome

Turn the official 16-scenario real-clinic feedback into an evidence-backed improvement pass without overclaiming. Preserve the existing longitudinal record, clinician authority, exact provenance, server-side RBAC, synthetic-data boundary, and raw-first failure recovery.

This is one integrated phase. Do not split it into a large set of independent features or start B/C work before the A design and acceptance gates are agreed.

## Owner priority register

### A — discuss first, then implement and verify

Canonical A-level task cards, each requiring separate owner approval:

1. `Task_Card/F_A2_Importance_Semantics_Task_Card.md`
2. `Task_Card/F_A1_Self_Learning_Trust_Task_Card.md`
3. `Task_Card/F_A3_Clinic_Isolation_Defense_Task_Card.md`
4. `Task_Card/F_A4_Log_Privacy_Boundary_Task_Card.md`
5. `Task_Card/F_A5_Provider_Total_Timeout_Task_Card.md`

F_A1 is the highest optimization priority, but F_A2 is the first implementation item because it defines the ranking, role-workflow and evidence contract that F_A1 must learn from. The summaries below do not override the individual task cards.

Current status: F_A2 deterministic scope plus itemized review/action-closure hardening, F_A1 auditable Shadow foundation, F_A3 clinic-isolation defense in depth, F_A4 log/operational privacy boundary (allowlisted stderr logging, edge access/error-log discard, fixed ASR failure codes), and F_A5 explicit Provider total timeout (30 s wall-clock deadline, async cancellation, distinct `provider_timeout`) are implemented and verified with stated limits. Formal Glance remains A2 base-only; no model has been trained or authorized for serving. F_A3 is application query isolation plus SQLite/SQLCipher ownership enforcement, not database RLS or production multi-tenant certification. F_A4 classifies crash monitoring and Provider retention as `NOT_ESTABLISHED` and leaves clinical `AuditLog` retention to owner policy. F_A5 is an MVP interaction policy, not a Provider SLA, and no live Provider timeout was observed. The final reason-code matrix is complete for mock, deterministic fallback and exact source mismatch; live Provider remains separately `NOT_RUN`.

1. **Self-Learning trust and blind-spot control (scenario 15; highest optimization focus)**
   - Address the fact that interaction feedback exists only for surfaced candidates.
   - Discuss shadow/unsurfaced-candidate audit, exploration or sampling limits, fatigue/bulk-dismiss safeguards, and rollback/freeze controls.
   - Preserve clinic scope, bounded adjustments, latest-signal semantics, exact provenance eligibility, and hard protection for risk, unresolved Task, clinician-confirmed, pinned, and `needs_review` content.
   - Do not claim learned clinical truth, clinician preference validity, or outcome calibration without matching evidence.

2. **Importance meaning and failure handling (scenario 14; core ranking contract)**
   - Keep `importance_score` an explainable retrieval heuristic, never a clinical-risk probability.
   - Define factor-level explanation, falsification checks, and what the UI/workflow does when the ranking is judged wrong.
   - Evaluate surfaced and unsurfaced candidates together with synthetic, reproducible evidence.

3. **Clinic-isolation defense in depth (scenario 2)**
   - Map every patient/clinic read and write path, including list and direct-object routes.
   - Decide how a second enforcement layer should complement `authorize_scope` without creating inconsistent authorization authorities.
   - Define the blast radius of a missing/incorrect scope check and add regression evidence for the selected design.

4. **Log and operational privacy boundary (scenario 3)**
   - Inventory application, edge/access, exception, audit, crash/monitoring, and Provider-side data paths separately.
   - Define what may be logged, where it is scrubbed, retention/deletion expectations, and what third-party behavior remains outside product control.
   - Use synthetic sentinels to prove application-owned paths; do not call absent production or third-party evidence verified.

5. **Explicit Provider total timeout (scenario 8)**
   - Bound the complete Provider wait, not only connection establishment.
   - Preserve the already-committed raw source, enter deterministic fallback on timeout, and label the degraded result in the clinician UI.
   - Test a Provider that never returns, not only one that raises an immediate error.

### B — design after A

- **Scenario 5:** clinic onboarding, first-admin bootstrap, patient import, and device-level versus clinic-level AI/Voice settings.
- **Scenario 6:** synthetic Malay-English-Hokkien transcript and downstream evaluation; no real-world accuracy claim without matching evidence.
- **Scenario 7:** real-time in-consult alerting as a separate streaming product, not a relabeling of post-consult processing.
- **Scenario 11 (owner-narrowed B11):** authenticated Patient portal instruction visibility, deliberate open and acknowledgement receipts; external Email/SMS/WhatsApp delivery remains `NOT_IMPLEMENTED`.
- **Scenario 12 (B12 implemented):** clinician publication gate plus correction, withdrawal and in-product new/unread behavior; acknowledgement remains the separate exact-version B11 receipt.

### C — after A and B

- **Scenario 1:** non-email patient access. Treat identity, account recovery, patient-record binding, and message delivery as separate security decisions. Phone/WhatsApp UI alone is not completion.

### D — preserve and re-audit after all higher-priority work

- **Scenario 4:** redaction-before-Provider ordering.
- **Scenario 9:** clearly labelled deterministic fallback when the Provider returns an error.
- **Scenario 10:** optimistic-concurrency conflict handling and visible refresh/retry.
- **Scenario 13:** allergy contradiction review across patient/AI and clinical records.
- **Scenario 16:** source-version/hash-bound Highlight provenance with historical resolution and fail-closed mismatch behavior.

D work is regression review, evidence refresh, and documentation only unless a regression is found. Do not refactor working safeguards merely to create activity.

## Execution contract

For each A workstream:

1. Inspect the current user/clinician journey and executable contract.
2. Explain the first visible failure and challenge the proposed design.
3. Present the smallest viable alternatives and trade-offs.
4. Wait for owner approval of that workstream's design.
5. Add a failing regression or evaluation case.
6. Implement the minimum approved change.
7. Run targeted tests, the full backend regression, frontend production build, and the relevant product-session browser journey.
8. Update the readiness ledger with `SURVIVES / PARTIAL / DOES NOT`, exact file/line evidence, first break, remaining risk, and non-claims.

One clinical/security risk is repaired at a time. A passing plan, mock, skipped test, historical run, or UI label is never counted as current runtime evidence.

## Permanent boundaries

- Synthetic data only; no real PHI.
- `Patient -> Event -> Artifact -> Span` remains canonical.
- Raw source is preserved before derived processing.
- AI never overwrites or impersonates clinician/staff-authored content.
- Conflicting records preserve both sources and request human review.
- RBAC remains server-side and DB identity remains authoritative.
- Patient View remains an explicit allowlist, not a filtered clinical workspace.
- Provider, fallback, mock, ASR, and `NOT_RUN` evidence remain separate.
- No production medical, regulatory, public-host, delivery, multilingual-accuracy, or clinical-learning claim without matching evidence.
- This card does not authorize future merge, push, external delivery, Provider spend, or third-party account/service changes.

## Phase exit gate

F1 is complete only when:

- every A workstream has an owner-approved design and a recorded implementation or an explicit evidence-backed decision not to implement;
- every implemented A change passes targeted and full regression evidence plus its relevant browser journey;
- B/C remain accurately classified if not implemented;
- D safeguards pass regression review after all A changes;
- the 16-scenario readiness ledger identifies exact implementation/absence, first visible break, remaining risk, and the improvement made;
- repository status and external delivery status are reported separately.

### Exit result — 2026-09-02

All gates above are satisfied within the approved synthetic prototype scope.
A/D targeted regression passed (`124` tests); full backend passed (`609`, with
`2` existing local-ASR-input skips); frontend production build passed (`62`
modules); Patient/Nurse/Clinician/Admin server-session browser acceptance passed
with zero warning/error. The final 16-scenario ledger, reason-code matrix and
repository/external-delivery status are recorded in
`docs/f1_a_closeout_2026-09-02.md`. Live Provider and other named production
evidence remain explicitly `NOT_RUN`, not silently counted as passes.
