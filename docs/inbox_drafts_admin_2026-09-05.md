# Work inbox, private note drafts and Admin refresh — 2026-09-05

## Delivered scope

1. **Work inbox**: `/clinical/inbox` projects existing active Tasks across the authenticated clinic. The default view contains own/shared role assignments and patient-reported care actions requiring clinic verification. All clinic work includes other assignees. Priority-review tasks precede patient verification, overdue tasks and other active work, with stable pagination. Opening a task navigates to the correct patient, expands the task and uses the existing source panel. No new task store, LLM ranking call, or change to Glance scoring is introduced.
2. **Private clinician/staff note drafts**: explicit Save private draft / Discard private draft in new-note and existing-note editors. A saved draft restores when its original editor is reopened after navigation or reload. Inputs changed since the last save are labelled unsaved and protected by a leave prompt. New notes publish through the existing create-note API; edits retain the existing formal-version conflict flow.
3. **Admin**: shared ink navigation, warm background, teal actions and serif page headings. Account search and role filtering, readable metrics/table rows, access-audit type filtering and collapsible identifiers. Mobile administration navigation collapses; wide account tables scroll within their panel.

## Data and permission contracts

- `NoteDraft` is a private working copy, separate from Artifact/ArtifactVersion and excluded from patient views and audit content.
- Draft identity includes owner, role, Event and note slot. Server-scoped Event/Artifact loading enforces clinic and section authority. Patient/Admin roles cannot use draft endpoints; unpublished check-ins remain inaccessible.
- The full original ArtifactVersion snapshot accompanies an edit draft, including non-string structured data. Draft fields are bounded and limited to the editable string fields of that snapshot.
- Atomic draft revisions reject stale writes with 409. Clearing retains a revision tombstone to prevent a stale first save from recreating discarded content. Clearing after publication cannot overwrite a newer draft from another tab.
- The additive `note_drafts` table is created at startup if absent. Upgrading does not require reseeding or replacing the project database. Existing configured database storage protections also apply to drafts.
- Inbox authorization is server-side, and Task/Event/Patient clinic identities must all match. Unsubmitted check-in Events are excluded.

## Verification

- Full backend regression: **738 passed, 2 skipped** (optional local ASR tests).
- Final targeted regression after additional hidden-check-in/ordering coverage and date handling cleanup: **34 passed**, including all **20 new inbox/draft tests** and affected workspace interaction contracts.
- TypeScript checks passed; production Vite build passed (115 modules); all 3 frontend Node test files passed; secret scan and git diff whitespace check passed.
- Real Chrome: inbox task opens the correct Maya record, task details and exact source; Verify completion removes it from the active queue; All clinic work shows multiple patients.
- Real Chrome: saved edit draft restores after reload without changing the formal v1 note; a second tab receives 409 and retains its conflicting local text.
- Real Chrome: a new note draft publishes into a separate clinician Artifact; reopening the new-note editor is empty, confirming draft cleanup. This write ran against the explicitly identified disposable synthetic SQLite test database, not `backend/nantingale.db`.
- Real Chrome: Admin name search, combined role filtering and keyboard clearing; real cookie login audit entry and audit-type filter; normal logout; desktop and 390px layouts. Account-table horizontal overflow stays inside its panel; page width stays within the viewport. Responsive override was reset.
- **Browser automation limitation**: the native unsaved-leave confirmation appears, but automation timed out while dismissing it. Do not treat cancellation/back/refresh prompt acceptance as fully browser-verified. This limitation does not affect the verified saved-draft restore, conflict, publish and cleanup paths.

## Current boundaries

- Draft saving is explicit, not automatic. The feature currently covers clinician/staff notes only; raw consult input, tasks and patient instructions do not have these drafts.
- Drafts resume in the original Event editor; no separate draft dashboard or autosave indicator is claimed.
- A newer cross-tab draft remains available if publication cannot clear it with the editor's known revision. Reopen and review/discard it when appropriate.
- Inbox is a refreshed task projection, not external push/email delivery. Task permissions are still checked by the existing action endpoints. It does not include every possible highlight or unread instruction receipt.
- Admin filters apply to loaded results; access audit is not a comprehensive clinical edit history or unlimited historical search.
- The preview remains local, uses synthetic fixtures and mock AI. No live model calls or outgoing notifications were needed.
