# D5 Automated Evidence - 2026-08-27

This record contains observed automated results, not expected annotations.

> Status: **D5_AUTOMATED_SECURITY_COMPLETE**
>
> Remaining: **D5_USABILITY_GATE_BLOCKED_EXTERNAL_OBSERVERS**

## Pre-change D1-D4 baseline

- clean `main` worktree at `0d9425d`;
- 324 backend tests passed;
- D3 corpus validation and runtime hard gates passed;
- D4 frozen Copilot evaluation passed;
- dependency check passed;
- frontend production build passed after a writable cache rerun.

## Added D5 evidence

- SQLCipher database/backup/restore: PASS (`4.12.0 community`, plain reader
  blocked, plaintext header absent, restored schema 13 tables);
- encrypted seed counts: 2 patients / 14 artifacts;
- Caddy release: v2.11.4; official archive SHA-256
  `1708333f79e274c7697285afe6d592ab39314e0b131e9ec6bea08ad27df62ebf`;
- Caddy config validation: PASS;
- HTTP path/query redirect to HTTPS: PASS;
- TLS chain: PASS (`TLSv1.3`, `TLS_AES_128_GCM_SHA256`);
- strict Origin CSRF, CORS allowlist, secure cookie, security headers and logout
  revocation over the running Caddy deployment: PASS;
- high-confidence repository secret scan: PASS;
- three independent real-session integration journeys: PASS in automated tests.
- clinician journey uses one newly invited account and one unchanged Cookie
  session for the complete Invite-to-Logout flow: PASS;
- invite preview uses `POST /api/auth/invites/preview` with token in JSON only;
  the old URL-token endpoint returns 404;
- offline-upstream Caddy probe: 502 response, Caddy stdout/stderr and inactive
  application log sink contain no fake preview token;
- database/backup/restore keys are 32+ characters and pairwise distinct;
  missing/short/same/wrong keys and existing output paths fail closed;
- final backend regression: **342 passed**;
- security/integration subset: **17 passed**;
- D3 corpus/runtime and D4 frozen Copilot evaluations: PASS after D5 changes;
- frontend production build, dependency check, Caddy validation and
  `git diff --check`: PASS;
- listener scope: Caddy `127.0.0.1:8080/8443`; FastAPI `127.0.0.1:8000` only.
- Caddy `skip_install_trust`: local CA installation disabled; TLS verifier used
  an explicit CA file and did not bypass verification.

## Honest remaining gates

- **D5_USABILITY_GATE_BLOCKED_EXTERNAL_OBSERVERS**: the required 5-8
  independent observers are not available. The blank protocol remains blank;
  no participants or outcomes were simulated.
- The local Caddy CA was not installed or bypassed, per owner instruction.
- Therefore this document does **not** declare D5 or Phase D complete; the
  strongest allowed status is `D5_AUTOMATED_SECURITY_COMPLETE`.
