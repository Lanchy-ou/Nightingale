# D5 Independent Usability Gate Protocol

> Status: **D5_USABILITY_GATE_BLOCKED_EXTERNAL_OBSERVERS**. The required 5-8
> independent observers are currently unavailable. This file remains a blank
> protocol/evidence form; no participant or result is simulated.

## Participants and setup

- Recruit 5-8 observers who did not implement Nightingale.
- Use synthetic data only and a fresh clinician, patient or staff session.
- Do not show the development Role selector and do not coach users through a
  failed step.
- Record task completion, elapsed time, misunderstandings and blockers; do not
  ask only whether the interface "looks good".

## Tasks

| ID | Role | Observable task | Pass condition |
|---|---|---|---|
| U1 | Clinician | Identify the most important current problem and next action | Correct answer within 10 seconds |
| U2 | Clinician | Verify one AI fact | Opens the exact supporting source span |
| U3 | Clinician | Import a transcript containing one ambiguous speaker | Finds the ambiguity and fixes/rejects it before confirm |
| U4 | Patient | Explain what to do next | Correctly states the visible next action |
| U5 | Patient | Report a Task done | Reaches `reported_done` and understands clinic verification is pending |
| U6 | Staff | Find and verify a reported Task | Finds `reported_done`, changes it to `completed`, and can identify the patient |
| U7 | All | Log out and try to return to protected content | Protected content is unavailable and login is required |

## Observation record

Create one row per observer/task. Do not prefill results.

| Observer | Role | Task ID | Success | Seconds | Misunderstanding | Blocker | Severity | Fix/retest evidence |
|---|---|---|---|---:|---|---|---|---|
| | | | | | | | | |

Severity:

- Blocker: the required journey cannot be completed or protected content leaks.
- High: completion requires developer coaching or the user takes an unsafe action.
- Medium: completion succeeds after a material misunderstanding/backtrack.
- Low: cosmetic or wording issue that does not change task completion.

## Gate rule

D5 cannot be marked complete until all seven tasks have observed evidence,
blockers are zero, high-severity issues are fixed and retested, and the final
summary reports failures as well as successes. Changing demo narration or
training observers does not close a product defect.
