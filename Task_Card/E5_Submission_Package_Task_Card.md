# E5 Task Card — Final Submission Package

> Status: **IN PROGRESS — EXECUTABLE GATES COMPLETE; OWNER INPUTS REMAIN (2026-08-28)**
>
> Baseline: merged Patient Multi-turn Check-in on `main` (`25a1dc9` before E5 documentation changes)
>
> E5 adds no business functionality and performs no last-minute refactor.

## 1. Objective

Package the verified Nightingale synthetic-data prototype into a concise, reproducible submission without converting expected behavior, historical evidence, mock output, fallback output, or missing manual artifacts into observed results.

Required deliverables:

- English README aligned with the current implementation;
- strict 2–3 page Technical Brief PDF with rendered-page inspection;
- complete `ATTRIBUTION.txt`;
- dated final evidence manifest;
- 6–9 minute real Demo Video plus playback/access verification;
- formal submission-email draft and final attachment/link checklist;
- final repository hygiene, security, build, test, and access checks.

## 2. Frozen capability labels

Every E1–E4 capability and Patient Multi-turn Check-in must use exactly one label:

```text
IMPLEMENTED_AND_VERIFIED
IMPLEMENTED_WITH_LIMITS
DESIGN_ONLY
NOT_INCLUDED
```

E5 itself is not complete while a required owner-supplied identity, link, or independently recorded/played video is absent.

## 3. Identity and external-action gate

Before calling the package Submission Ready, confirm the submitter's exact name, final repository/zip link, Technical Brief attachment, Demo Video link and playback, email recipients/subject, and attachment access. Do not leave `<Your Name>`, fake URLs, test links, or invented evidence. Missing values are `NEEDS_OWNER_INPUT`.

E5 is not authorized to send email, upload/share files, publish a repository, or change access/visibility. Those actions require a separate owner instruction.

## 4. Claim boundary

Allowed claims must match current evidence:

- synthetic-data prototype, not a production medical system;
- server-side RBAC and exact clinic/patient scope;
- explicit Event → Artifact → Span provenance;
- local synthetic performance only;
- current local TLS/SQLCipher results only;
- mock, DeepSeek, deterministic fallback, ASR, and `NOT_RUN` results reported separately;
- Voice described only to the extent currently observed;
- Patient Multi-turn Check-in described as bounded non-emergency information collection;
- high-risk rules are transparent rules, not formal medical triage;
- self-learning is bounded interaction weighting, not clinical learning;
- data decay is a verified shadow-payload policy, not demonstrated total storage savings.

Forbidden claims include production readiness, clinical validation, formal triage, clinic notification, production capacity, regulatory compliance, external ASR privacy, diarization, real-clinician usability, or a successful full live Provider journey without matching evidence.

## 5. File allowlist

E5 may update or add only final documentation/evidence/packaging files and mechanical English-language cleanup:

```text
README.md
AGENTS.md
ATTRIBUTION.txt
backend/requirements.txt
backend/docs/perf_baseline.md
Task_Card/E5_Submission_Package_Task_Card.md
Task_Card/*.md
docs/*.md
Nightingale_72H_Development_Plan.md
frontend/src/components/ArtifactEdit.tsx
output/pdf/Nightingale_Technical_Brief.pdf
tmp/pdfs/*
```

Any source-code or business-behavior change is a stop condition.

## 6. README gate

README must state actual setup, architecture, Candidate Brief mapping, RBAC, redaction, the single `LLMClient` exit, Provider/fallback status, provenance, performance, Voice, Check-in, known limits, and final evidence paths.

## 7. Technical Brief PDF gate

The PDF must be exactly 2–3 pages and contain:

1. problem framing, user journeys, architecture diagram, and trust boundaries;
2. comprehensive schema linking Brief `Entry` to Event/Artifact, Comments, Versions, Highlights, Provenance, AI-scribed notes, Tasks, identity, E2, E3, E4, and Check-in;
3. measured evidence, security/Provider boundaries, trade-offs, status table, and known limits.

All pages must be rendered to images and visually inspected. No clipped text, overflow, broken characters, or unsupported numbers are allowed.

## 8. Demo Video gate

The real 6–9 minute video must use product session mode, not the demo role selector. It must show login/context, Glance in under 10 seconds, exact Highlight source, longitudinal Timeline, Patient Multi-turn Check-in, clinician Check-in review and exact message source, Task authority, collaboration/audit, and explicit known limits.

The file must be played from start to finish. Record duration, resolution, audio intelligibility, and link access. A script, storyboard, screenshots, seed rows, or browser QA is not a substitute for an actual video.

## 9. Attribution gate

List all actual libraries, deployment tools, Providers, models, data/requirement sources, and licenses. Do not attribute unused experiments as runtime components. Confirm that no model weights, Caddy binary, secret, private database, raw recording, real patient data, or unlicensed asset is committed.

## 10. Final evidence manifest

Create `docs/final_submission_evidence_2026-08-28.md` containing final local/remote commit ids, environment, exact commands and counts, D3/D4 output, E1–E4/Check-in status, SQLCipher/Caddy/performance/dependency/security results, Provider/ASR separation, PDF rendering, video/access status, failures/skips, limitations, and `NEEDS_OWNER_INPUT`.

## 11. Final verification matrix

```text
backend full pytest
required RBAC/revision/provenance/concurrency tests
Patient Multi-turn Check-in targeted tests
security/integration tests
E1–E4 targeted regression
D3 corpus validation + deterministic runtime
D4 frozen Copilot eval
frontend Node interaction checks
frontend production build
Glance performance harness
E3 storage-policy harness
SQLCipher init + separate-key backup + rotated-key restore
Caddy validate + secure Demo verification
pip check + npm ls --depth=0
secret scan + tracked/untracked asset audit
git diff --check
PDF page count + render + visual inspection
Demo Video full playback + access check
repo/zip and attachment/link access check
```

## 12. Git gate

After E5 files are complete:

1. create `docs(submission): finalize Nightingale submission package`;
2. rerun final verification on that commit;
3. ensure evidence refers to the commit actually verified;
4. fetch and compare `origin/main` again;
5. if no unknown drift, push normally to `origin/main`;
6. verify local main, remote main, and final evidence hash alignment;
7. never rebase, force-push, amend, or rewrite history.

If the manifest must be updated with a post-commit hash, use an additional evidence-only commit and proportionate rerun rather than rewriting history.

## 13. Stop conditions

Stop and report if E5 would require a business feature, fabricated identity/link/metric/video/Provider/ASR evidence, deleting failures/skips, committing private assets, unauthorized external actions, rebase/force push, or claiming Submission Ready without full video playback and verified access.

## 14. Current status (2026-08-28)

Executable repository, security, performance, PDF, English-documentation, and packaging gates are being completed. These inputs remain `NEEDS_OWNER_INPUT`:

- exact submitter name;
- actual 6–9 minute Demo Video file/link and full-playback evidence;
- final attachment/link confirmation from the submitter's intended email/account context.

Until those inputs are supplied and verified, E5 and the overall submission remain **NOT SUBMISSION READY**.
