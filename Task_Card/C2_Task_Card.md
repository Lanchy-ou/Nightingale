# C2 Task Card — Clinician Workspace and Consult Review UX

> Status: COMPLETE

## Outcome

Deliver the three-column desktop clinical shell: clinic patients at left, patient workspace in the center, and contextual Source/Comments/History at right.

## Permanent contract

- Patient selection is a security/remount boundary.
- Center views are Clinical Overview, Timeline, Notes, and Tasks.
- Event Detail shows the Artifact/comment/revision lifecycle without flattening audit actions into medical Events.
- Doctor Consult review follows Paste → Review → Confirm.
- Raw transcripts remain immutable; corrections use comments or a role-authored note.
- Staff and clinician authorship remain separate.
- No fake assignment, appointment, AI Assistant, or Nurse-only workspace is introduced.

## Exit evidence

Desktop journey, source navigation, comments, versions, audit, patient/role switching, frontend build, and backend regressions pass.
