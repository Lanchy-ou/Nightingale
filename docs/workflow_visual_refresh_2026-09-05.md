# Workflow and visual refresh — 2026-09-05

## Direction and scope

A reading-first workspace with warm neutral surfaces, ink-colored navigation,
teal actions, and restrained serif patient headings. Shared theme rules live in
`frontend/src/workspace.css`; document authority badges and warning states retain
separate meanings. This pass changes existing workflows and presentation, without
adding clinical interpretation or changing server permissions.

## Main changes

- Glance: one list instead of a duplicated index/detail layout. Each priority has
  its reason, review state, actual Event date, source/task entry, and review controls.
  Guidance and deterministic ranking remain available in expandable details.
  Confirmed allergy context retains its exact-source button.
- Navigation: Glance, Timeline, Notes and Tasks form the primary work sequence;
  Coverage Review remains accessible as a secondary navigation item. Event back
  links return to the originating view. Cancelling a new consult also returns there.
- Timeline: newest visits first by default, reversible chronological order and an
  Event-type filter. Explicit encounter identity continues to define Clinic Visits.
- Event: direct document selectors precede a full-width reader. Activity is an
  expandable chronological section after the reader. Clinician note creation has
  primary emphasis; task/instruction/comment actions remain explicit. Opening a
  composer scrolls it into view. AI and human documents remain separate.
- Responsive source review: three columns from 1440 px; a contextual drawer below
  that width, including mobile. Opening the drawer moves keyboard focus into it;
  Escape closes it and restores the previous focus where available.
- Patient Today: care actions precede instructions, overdue open/in-progress tasks
  have an explicit text marker, and visit dates are labelled as visit dates.
  Opening an instruction scrolls and focuses its reader. Reading acknowledgment
  and patient-reported task completion retain their distinct server workflows.
- Copy: shorter instructions, fewer schema explanations in primary reading areas,
  consistent consultation entry labels and clearer clinical versus patient actions.

## Verification

Browser checks used an isolated, freshly seeded SQLite database, mock AI and
voice disabled. The workspace database was not used for browser mutations.

Checked at 1280×720, 1600×900 and 390×844:

- Glance source opens the original nurse transcript and highlights the exact quote.
- Source drawer is directly visible on mobile, with a reachable close action.
- Notes → Doctor Consult opens the selected clinician note; Back to Notes returns.
- Event document selectors and note composer remain reachable; opening the composer
  scrolls its input into view. Activity is collapsed and follows the reader in DOM order.
- Timeline Doctor Consult filtering retains explicit Clinic Visit grouping.
- Patient instruction open changes receipt to viewed; acknowledgment is a separate
  action. The reader receives focus on mobile.
- Patient task Start changes to in progress; Report done changes to awaiting clinic
  confirmation, without claiming clinical completion.
- Switching to Patient renders only the patient workspace.

TypeScript check, three frontend Node test files and Vite production build passed
(113 modules). Focused role/interaction/patient-view contracts: 33 passed.
Final complete backend regression: **720 passed, 2 skipped** in 243.77 seconds.
The two skips are the existing optional local-ASR input checks.
Diff whitespace check and repository secret scan passed.

This is a working visual iteration. Browser inspection does not establish clinical
usability under ten seconds; that still requires observation with representative users.
