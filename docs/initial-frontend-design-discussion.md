# Initial Frontend Design Discussion — English Archive

## Original design problem

The prototype needed to avoid a generic dashboard or Notion-like page while making longitudinal context, current priorities, and source trust understandable.

## Decisions retained

- Preserve Glance as a high-signal clinical overview.
- Use Clinic Patients as persistent authorized navigation.
- Keep the center work area focused on one patient.
- Keep Source/Comments/History in a contextual right rail.
- Treat Timeline as Event chronology and Event Detail as the Artifact lifecycle.
- Use progressive disclosure rather than nested timelines.
- Keep Patient Experience action-first and visually separate from the clinical shell.
- Do not expose demo-only identity controls in product mode.
- Do not invent assignments, appointments, notifications, or AI authority.

## Design system

The UI uses restrained green/teal role cues, readable cards, explicit status labels, source/authority badges, clear empty/loading/error states, and scoped responsive behavior. Visual changes are secondary to safe journeys and provenance.

## Final implementation

C2 and E1 implemented the clinical shell; D2 implemented the patient shell; D3/D4/E4 and Patient Multi-turn Check-in added bounded workflows without replacing the core information architecture. Current screenshots/video must come from actual runtime, not this archive.
