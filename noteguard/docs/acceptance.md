# Goal plan and acceptance ledger

## Goal-based implementation plan

1. **Define input and expectations:** one synthetic encounter; six disciplines; text + PDF; explicit metadata, supported phrases, positive/negative controls. Completed by input contract, fixtures and synthetic PDFs.
2. **Make the source trustworthy:** immutable identities/versions, checksums, chronological inventory, source/import time, cutoff, page/text evidence and extraction limitations. Completed in source model and reader.
3. **Find explainable questions:** deterministic checks, version comparison, conservative response suppression, provenance and accountable owner. Completed for bounded English patterns; broad clinical language is not supported.
4. **Close the human loop:** explicit lifecycle, rationale, reassignment/clarification, history and visible Tier 1 blockers. Completed in session state; no actual clinical closure or notifications.
5. **Communicate current state:** bounded questions, summary/export, mobile review, installable shell, documented governance and integration path. Completed with the limitations below.

## Requirement -> scenario -> verification

| Requirement | Scenario / test | Result |
|---|---|---|
| Critical result + later response | `test_critical_observation_routing`; negated/earlier/unrelated response controls | PASS: candidate suppressed appropriately; pre-existing Tier 1 remains until human disposition |
| Cross-note allergy and dose | `test_cross_note_conflicts`; wrong-dose/negation controls | PASS: two sources, correct tier, responsible clinician and pharmacy contributor |
| Pending owner + time | `test_pending_owner_and_time` | PASS: either missing fails; recognised owner + future deadline passes |
| PDF limits | `test_pdf_extraction_boundary`; browser imports all three generated PDFs | PASS: retained original, page render, unreadable/partial flags |
| Access scope / decision policy | `test_access_control`; outsider perspective browser test | PASS for local policy simulation only; server authentication and authorisation NOT IMPLEMENTED |
| Logs and redaction | `test_log_and_redaction_safety`; browser egress/storage test | PASS within known-name/pattern limits; no external model called |
| Flag and summary provenance | `test_grounding`; browser source and export checks | PASS: exact version/span or attachment/page extraction evidence |
| Differencing | `test_differencing` | PASS: changed and copied text prompts review, not automatic contradiction |
| Question bubble | `test_question_bubble_grounding`; browser ECG | PASS: restricted status, cutoff, source evidence or inspected versions |
| Human lifecycle and closure | acceptance/edit blocker test; browser accept -> response -> supersede | PASS: accepting/editing never resolves Tier 1; human disposition changes blocker count |
| Mobile layout and privacy | 390x844 browser session; refresh/reset | PASS: no page overflow, source controls work, case clears, no local/session/IndexedDB/cache persistence |
| Updated record consistency | immutable/version/cutoff/rerun tests | PASS: old source resolvable, duplicate intake idempotent, decisions retained |

## Verification evidence

Commands: `npm test`, `npm run build`, `npm run test:browser` with preview running. Machine browser ledger and screenshots: ignored `test-results/`; domain tests remain in the repository. Dependency scan after the Vite 6.4.3 patch reported zero known npm vulnerabilities on 22 September 2026. This is a dated scan, not a security guarantee.

The final test counts and media verification are recorded in `verification.json` after final execution. No parent-application tests are claimed: no existing application source was changed.

Four-page PDF rendered and visually inspected on all pages. Browser screenshots inspected at desktop and mobile sizes. Video is an actual browser recording with explanatory captions, not a storyboard presented as a recording.

## Explicit limits and deferred production work

- Browser-memory exception used. No server login, secure clinical access or production authorisation; do not mark the appendix's server access-control proof as passed.
- No clinical validation, measured sensitivity/specificity, representative user study or measured one-minute comprehension.
- Line-oriented English vocabulary only; no multilingual NLP, OCR, full medication ontology, specimen association or complete temporal inference.
- Page text coverage is heuristic. An image region on a text-rich page can be missed; original comparison is required.
- No durable clinical/security audit, encrypted clinical store, production malware scanning or approved real-data hosting.
- No external model, real EMR adapter, real notifications, autonomous decisions, voice capture or automatic learning.
- Governance aggregates represent this synthetic session only. Production quality/legal access and rule release pipeline are architecture, not implemented systems.
- Email submission, recipient access and deadline confirmation were not performed.

## Research and attribution

See `research.md` for original research and AHRQ workflow guidance. The system's clinical rules are acceptance examples, not claims derived from research outcomes. `ATTRIBUTION.txt` lists locked dependencies, document tooling and model absence.
