# D5 Task Card — Security and Integration

> Status: D5_AUTOMATED_SECURITY_COMPLETE

## Outcome

Harden the single-machine synthetic demo and prove its security boundaries with executable evidence.

## Deployment decisions

- Product demo storage is SQLCipher; plain SQLite is test/development only.
- Database, backup, and restored-database keys are independent and 32+ characters.
- Caddy terminates local TLS, redirects HTTP, serves the SPA, and proxies to loopback FastAPI.
- Product mode rejects insecure cookies, demo auth, plain storage, debug mode, and non-HTTPS origin.
- Exact-origin CSRF/CORS, request limits, rate limits, secure headers, generic errors, and sanitized logs are enforced.

## Integration contract

Real session-cookie journeys cover clinician, staff, patient, admin, cross-clinic denial, exact provenance, note/Task/instruction authoring, and logout. Demo headers are not used.

## Evidence boundary

Current local evidence proves SQLCipher file/backup/restore protection and Caddy TLS behavior for the synthetic demo. It is not a penetration test, public-host certification, compliance result, production-capacity result, or clinical usability study.

## Exit evidence

Security/integration tests, secret scan, SQLCipher init/backup/restore, Caddy validate/secure-demo verification, dependency checks, and full regressions pass.
