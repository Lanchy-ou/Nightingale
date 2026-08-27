# Patient Experience Design — English Record

## Goal

Help a patient understand what to do next without exposing the internal clinical workspace.

## Navigation

- Today: current instruction, next follow-up, active care actions, entry to Check-in.
- Care Plan: visible Tasks grouped by safe patient status.
- Check-in: bounded non-emergency information collection.
- Visit Summaries: clinician-authored patient-facing instructions.

## Safety and authority

- Patient APIs return explicit field allowlists.
- Internal comments, staff/clinician notes, raw clinical AI summaries, audit, versions, risk scores, and clinical reasoning are excluded.
- Patients can Start or Report done on their own visible Tasks; clinic verification is required for completion.
- Check-in saves patient words first, asks one bounded question at a time, refuses medical advice, and does not change a care plan or Task.
- High-risk rule matches show urgent-help guidance without claiming diagnosis, formal triage, or clinic notification.
- Patient/role/session/logout changes clear drafts and pending responses.

## Interaction quality

Use plain language, clear action labels, patient/AI message separation, visible saving/processing/failure states, refresh recovery, and a confirmation page that shows saved patient messages without editable AI prose.

## Implemented outcome

D2 and Patient Multi-turn Check-in implement this design. The current evidence manifest and runtime video, once supplied, are authoritative.
