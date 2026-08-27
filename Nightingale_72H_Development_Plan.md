# Nightingale 72-Hour Development Plan — English Archive

> Final state: core M1–M7, clinical workflow C1–C2, Phase D D1–D5, Phase E E1–E4, and Patient Multi-turn Check-in are implemented under their dated task cards. E5 packaging remains blocked on owner inputs listed in the final evidence manifest.

## Mission

Build one safe synthetic-data longitudinal record in which Timeline explains what happened, Glance shows what matters now, and Patient View shows what the patient needs to know or do.

## Execution sequence

1. M1–M3: skeleton, Event/Artifact/Span, Timeline/Glance/provenance, collaboration, revision, RBAC.
2. M4–M7: redacted AI pipeline, longitudinal fixture, patient-safe view, core verification.
3. C1–C2: new Doctor Consult backend and clinician review workspace.
4. D1–D5: real identity/session, care Tasks, transcript reliability, evidence-bound Copilot, deployment security/integration.
5. E1–E4: role workspaces, bounded importance learning, shadow data-decay policy, local Voice adapter.
6. Patient Multi-turn Check-in: bounded raw-first patient information collection and clinical review.
7. E5: final English package, Technical Brief, evidence, video, and submission checklist.

## Non-negotiable product rules

- One longitudinal record; no doctor/patient/AI silos.
- Event is the Timeline unit; Artifacts are parallel representations.
- Raw source is immutable and never replaced by AI or human summaries.
- AI artifacts are system-authored and never equal clinician assessment.
- Every important derived item resolves to an exact source Span.
- Server RBAC, clinic scope, and patient ownership are authoritative.
- Clinician/staff role-owned sections do not overwrite one another.
- Patient APIs use explicit allowlists and never expose internal clinical reasoning.
- Redaction precedes every Provider call; logs and audit contain metadata only.
- Deterministic rules own safety, ranking, Task/session state, and permissions.
- Synthetic data only.

## Delivery priorities

Required gates > trust/provenance/security > coherent journeys > bonus behavior > polish.

## Final evidence

Use README.md and docs/final_submission_evidence_2026-08-28.md for current commands, counts, limits, and Submission Ready status. Historical long-form planning remains recoverable from Git history before the E5 English archival rewrite.
