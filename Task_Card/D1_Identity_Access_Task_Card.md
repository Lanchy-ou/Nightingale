# D1 Task Card — Identity, Invite, Login, and Session

> Status: COMPLETE AND RE-VERIFIED

## Outcome

Replace demo headers with a real synthetic invite/register/login/session/logout path while retaining demo mode behind explicit flags.

## Permanent contract

- Invite and session tokens are random; only SHA-256 hashes persist.
- Passwords use Argon2id; plaintext never enters DB, logs, or audit.
- Database User is authoritative for role, clinic, and patient binding.
- HttpOnly SameSite cookies restore identity; logout revokes server state.
- Disabled, expired, revoked, and unknown identities fail closed.
- Legacy X-User-Id/X-Role works only when NANTINGALE_DEMO_AUTH=true.
- Admin invite scope comes from the authenticated admin.

## Exit evidence

Invite concurrency, patient binding, uniform login behavior, session precedence, logout atomicity, RBAC routing, frontend product mode, and secret-free validation tests pass.
