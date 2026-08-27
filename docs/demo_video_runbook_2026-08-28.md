# Nightingale Demo Video Runbook — 2026-08-28

> Required duration: 6–9 minutes.
>
> Current status: `NEEDS_OWNER_INPUT`. No final video file or link is present, so playback and submitter-view access are not verified.

## Recording rules

- Use product session mode. Keep `VITE_DEMO_AUTH` and `NANTINGALE_DEMO_AUTH` false/unset; no role selector or demo banner may appear.
- Use only the seeded synthetic patient Alice Tan.
- Do not show environment secrets, terminal history, private Caddy keys, database paths, Provider keys, or real personal data.
- Do not claim diagnosis, formal triage, clinic notification, production readiness, clinical validation, or full live DeepSeek success.
- Record the actual running application. Static designs, seeded database inspection, screenshots, or this script are not substitutes.

## Pre-record checklist

1. Build the frontend and initialize a fresh synthetic product-mode database.
2. Confirm product-mode login works for patient and clinician seeded accounts.
3. Confirm no draft Check-in is left from a previous rehearsal.
4. Keep Voice default-off unless the current ignored local model/audio inputs are deliberately prepared. Voice is not required for this video.
5. Set Provider to `mock` for a deterministic complete journey. State verbally that mock and fallback are verified; the current full DeepSeek Check-in journey is not verified.
6. Use a 1280×720 or higher capture and readable browser zoom.
7. Verify system audio/microphone level before the full take.

## 7:30 target script

### 0:00–0:35 — Product boundary and login

- Show the product login page with no demo controls.
- Say: "Nightingale is a synthetic-data longitudinal care-record prototype, not a production medical system."
- Log in as the seeded clinician.

### 0:35–1:25 — Glance in under 10 seconds

- Open Alice Tan from Clinic Patients.
- Pause on Clinical Overview and identify the first current priority and open action.
- Open one Highlight's exact source.
- Show Event, AI Summary Artifact, raw Artifact, highlighted exact Span, author, and event time.

### 1:25–2:10 — Longitudinal record and authority

- Open Timeline and show the 2025 historical review, 2026 historical review, Nurse Consult, Doctor Consult, patient follow-up, and clinician review.
- Open a Doctor or Nurse Consult.
- Point out immutable Transcript, system-authored AI Summary, separate clinician/staff Artifact, and exact source.

### 2:10–4:20 — Patient Multi-turn Check-in

- Log out, then log in as the seeded patient; do not use a role switcher.
- Open Check-in and read the non-emergency/non-diagnostic boundary.
- Start a Check-in.
- Answer: "My headache is 4 out of 10 and I still feel nauseous."
- Use Add something: "I also feel dizzy when I stand up."
- Report: "I completed the blood test task today."
- Ask: "Should I stop propranolol or double my dose, and is my result normal?"
- Show the deterministic refusal and four-question cap.
- Return to correct: "Correction: the headache is 3 out of 10, not 4."
- Confirm the source-preserving recap and submit.
- State that every patient message was saved first with one stable message id and that Check-in did not change the Task or care plan.

### 4:20–5:20 — Clinician Check-in review and exact provenance

- Log out and log in as the clinician.
- Open the new Patient Check-in Event from Timeline.
- Show Patient original messages and Nightingale AI questions/acknowledgements in separate sections.
- Open AI Patient Session Summary and its exact patient-source list.
- Open one resulting Highlight/source and show the stable patient message id plus quote/offset.
- State that active/unconfirmed drafts are hidden from clinical readers.

### 5:20–6:10 — Task and collaboration authority

- Open Tasks and show that patient-reported done waits for clinic verification.
- Show one Comment or note version/audit action.
- Point out that clinician and staff Artifacts remain separate and AI cannot author as either role.

### 6:10–7:10 — Security, fallback, and limits

- Briefly show the README evidence section or an in-app authority cue, not terminal secrets.
- Say: "Text is redacted before the single LLMClient exit. Mock and deterministic fallback complete the journey. A current live DeepSeek turn succeeded, but strict live Summary validation fell back, so a full live journey is not claimed."
- Say: "Voice is default-off, local-only, has no diarization, and the final environment did not rerun two real-ASR tests because the ignored model/audio inputs are absent."
- Say: "Self-learning is bounded interaction weighting; data decay is a verified shadow payload, not clinical learning or demonstrated total storage savings."

### 7:10–7:30 — Close

- Return to Clinical Overview.
- Close with the three product principles: Timeline is what happened; Glance is what matters now; Patient View is what the patient needs to know or do.

## Post-record validation

Record all results in the final evidence manifest:

- exact file path and SHA-256;
- duration (must be 6–9 minutes);
- resolution and codec/container;
- audio intelligibility;
- full playback from 0:00 to end with no missing/corrupt segment;
- verification that Patient Check-in, clinician review, and exact provenance are visibly demonstrated;
- final video link and access from the submitter's intended account/context.

Until every item above is observed, use `NEEDS_OWNER_INPUT` and do not claim Submission Ready.
