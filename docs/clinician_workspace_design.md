# Clinician Workspace Design — English Record

## Decision

Use a persistent three-column desktop clinical shell:

- left: signed-in role and clinic-authorized patient navigation;
- center: patient Clinical Overview, Timeline, Event Detail, Notes, and Tasks;
- right: Copilot or contextual Source, Comments, Versions, and Audit.

## UX principles

- A clinician should understand current state and next actions in under 10 seconds.
- Exact source verification must be available without losing patient context.
- Timeline shows real-world Events, not every comment/edit/audit action.
- Event Detail progressively discloses Artifacts and collaboration lifecycle.
- Clinic Visit grouping requires a shared explicit encounter id; date alone is insufficient.
- Patient switching remounts the workspace and clears sensitive state.
- Staff and clinician share the shell but receive role-authorized controls.
- Admin does not enter the clinical authoring shell.
- Patient View is independent and never a filtered copy of this workspace.

## Authority cues

- Raw Transcript/Conversation: immutable.
- AI Summary: system-generated, not clinician assessment.
- Clinician Note and Staff Note: separate role-owned Artifacts.
- Patient Instruction: clinician-authored patient-facing Artifact.
- Task: first-class action with Event origin and optional exact source.
- Comments: collaboration only.
- Copilot: evidence-bound retrieval and editable preview only.

## Implemented outcome

The current React workspace follows this information architecture, includes responsive/resizable rails, and preserves Event → Artifact → Span navigation. Detailed implementation and current evidence are in README.md and the final evidence manifest.
