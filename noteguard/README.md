# Nightingale Noteguard

An independent, synthetic, browser-memory demonstration of multidisciplinary record reconciliation. It is separate from the parent Nightingale longitudinal-record application.

**Not production medical software. Use synthetic material only. There is no server authentication, persistent clinical storage, external AI, real EMR connection, notification delivery, or clinical validation. Demo role checks are bypassable and do not protect real patient data.**

## Run

Node.js 22.12+ or 24 recommended. From this directory:

```sh
npm ci
npm run dev
```

Open http://127.0.0.1:5178. For the production bundle:

```sh
npm run build
npm run preview
```

The app uses a dedicated port; the original frontend/backend are untouched. The host must provide HTTPS outside localhost. Vite preview is for local demonstration, not a production server. Keep this build local; do not expose it to clinical users as an authenticated service.

## Demonstrate the workflow

1. Load the synthetic encounter: six multidisciplinary records produce potassium, allergy, dose and pending-follow-up questions.
2. Click an evidence card to inspect the immutable source and exact highlighted quotation.
3. Accept responsibility for the potassium concern with a rationale. The closure blocker remains.
4. Add the later clinician response. Checks recognise the response, but existing concerns remain for human disposition.
5. Review the response under Source records; confirm a concern resolved or superseded with a rationale. Observe the change in closure status.
6. Upload `output/pdf/selectable-report.pdf`, `scanned-report.pdf` or `partial-report.pdf` through Add record. Inspect page extraction and the original PDF.
7. Open Handover summary, follow citations, and explicitly export the summary.
8. Refresh or reset: imported data, attachments, flags, draft text and decisions disappear. Changing demo perspective also clears the case.

No mock AI is presented as a live model. The Clinical Augmented Intelligence question bubbles are deterministic, bounded questions over supplied evidence.

## Verification

```sh
npm test
npm run build
# Keep npm run preview running in a separate terminal:
npm run test:browser
```

Browser tests use installed Microsoft Edge by default. Set `NG_BROWSER=chrome` to use installed Chrome. Alternatively install a Playwright-supported channel on your platform. Browser results/screenshots are written to ignored `test-results/`. The browser suite tests actual PDF intake/rendering, not a simulated parser.

`test_access_control` proves an in-memory policy model only. **Server access-control acceptance: NOT IMPLEMENTED.** This explicitly uses the browser-memory demonstrator exception in the acceptance appendix. Frontend scope tests must never be reported as production security evidence.

## Input and safety contracts

See [INPUT_CONTRACT.md](docs/INPUT_CONTRACT.md) for supported English expressions, known limits and cases. Source identity includes encounter, namespace, source ID and version. Reusing a version with changed content/metadata is rejected. PDF file SHA-256 and extracted-text SHA-256 are distinct. Source versions are frozen; exact evidence resolves against the original version.

No raw-content logging exists. Clinical text, PDFs and decisions stay in JavaScript memory. No localStorage, sessionStorage, IndexedDB, Cache API, telemetry or remote model is used. The service worker has no fetch handler and no offline cache; installation does not imply offline clinical access. Dev/preview responses use `private, no-store`. Export intentionally creates a user-owned file and is never automatic. The JavaScript PDF parser disables eval and PDF scripting; attachments are rendered as canvas, not embedded active PDFs. Malware scanning and sandboxed production parsing/OCR are NOT implemented.

`src/privacy.mjs` tests a local redacted derived copy and offset mapping. Known names, common national IDs, tagged IDs, emails and phone patterns are covered. This is not exhaustive de-identification and does not authorise disclosure. There is no external-service exit in this build.

Rules are independently testable in `src/core.mjs`. The potassium threshold and supported expressions are demonstrator acceptance examples, not clinical recommendations. Absence is reported only within supplied sources. A later response suppresses a new candidate; reconciliation does not auto-close existing issues. Accepted and edited Tier 1 concerns still block closure until an explicit human disposition.

## Deliverables

- [Goal plan and traceability](docs/acceptance.md)
- [Input contract and synthetic scenarios](docs/INPUT_CONTRACT.md)
- [Research basis](docs/research.md)
- [Architecture and integration/governance path](docs/architecture.md)
- [Four-page technical brief](output/pdf/Noteguard_Technical_Brief.pdf)
- Recorded demonstration: supplied separately by the owner; the video file is not stored in this GitHub branch.
- [Attribution and licenses](ATTRIBUTION.txt)

To rebuild PDFs, use Python with `reportlab`, `Pillow`, `pypdf` and run `python scripts/build-pdfs.py`. To record the demo, install the Playwright encoder (`npx playwright install ffmpeg`), run preview, then `node scripts/record-demo.mjs`. Generated PDFs/video use synthetic content exclusively. Submission email and the ambiguous deadline require owner confirmation; this application does not send anything.
