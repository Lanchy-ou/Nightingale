# M6 Task Card — Patient View

> Status: COMPLETE

## Outcome

Deliver an independent patient-safe projection rather than a filtered clinical workspace.

## Permanent contract

- Patient route renders Today, Care Plan, Check-in, and Visit Summaries.
- The aggregate endpoint explicitly allowlists fields.
- Only clinician-authored, same-clinic patient instructions are projected.
- No internal comments, audit, versions, Highlights, risk scores, or raw clinical AI notes appear.
- Patient identity may read only its own record.
- Patient/session/role changes remount and clear sensitive state.
- Read-time projection performs no LLM call.

## Exit evidence

Exact-key-set, sentinel anti-leak, authorship, ordering, own-session, RBAC, and frontend-call-contract tests pass.
