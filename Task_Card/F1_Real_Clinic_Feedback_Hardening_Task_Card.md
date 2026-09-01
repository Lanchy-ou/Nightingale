# F1 Task Card — Real-Clinic Feedback Hardening

> Status: ACTIVE — discussion and design only until the owner approves each A workstream
> Revision window: 48-hour improvement period

## Outcome

Turn the official 16-scenario real-clinic feedback into an evidence-backed improvement pass without overclaiming. Preserve the existing longitudinal record, clinician authority, exact provenance, server-side RBAC, synthetic-data boundary, and raw-first failure recovery.

This is one integrated phase. Do not split it into a large set of independent features or start B/C work before the A design and acceptance gates are agreed.

## Owner priority register

### A — discuss first, then implement and verify

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
- **Scenario 11:** appointment/instruction delivery lifecycle, including send status, failure, retry, receipt, and escalation without pretending an external message was delivered.
- **Scenario 12:** clinician publication gate plus correct/withdraw/notify/acknowledge behavior for patient-facing instructions.

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
