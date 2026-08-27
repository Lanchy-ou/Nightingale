# E1 Task Card — Role Workspaces

> Status: IMPLEMENTED_AND_VERIFIED

## Outcome

Complete role-specific Nurse, Clinician, Admin, and Patient journeys without creating disconnected data models.

## Permanent contract

- Nurse remains RBAC role staff with optional professional_title presentation metadata.
- Nurse transcript normalization has a separate nurse/patient speaker contract.
- Nurse Consult stores immutable raw Transcript first and uses the existing AI pipeline.
- Staff and clinician share the clinical shell but receive only role-authorized controls.
- Admin has identity/session/invite/access-audit oversight only and no clinical authoring.
- Patient remains in the independent patient-safe shell.
- Explicit encounter id may group Nurse and Doctor Events; date alone never does.
- Patient/role/session changes clear drafts, context, and requests.

## Exit evidence

Nurse ingestion/normalization, Admin oversight, workspace state isolation, RBAC, D3/D4 regressions, frontend build, and browser journeys pass.
