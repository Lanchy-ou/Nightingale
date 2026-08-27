# D5 Deployment Security Decisions and Reproduction

> Status: **D5_AUTOMATED_SECURITY_COMPLETE** on 2026-08-27;
> **D5_USABILITY_GATE_BLOCKED_EXTERNAL_OBSERVERS**. D5/Phase D is not complete.

This is a single-machine, synthetic-data product Demo. It is not a production
medical system and makes no production capacity claim.

## Decision Gate 1: deployment database

Selected: **SQLCipher encrypted SQLite deployment + plain SQLite unit tests**.

Why:

- D5 explicitly permits encrypted SQLite/SQLCipher for a single-machine Demo.
- The current host has no Docker/PostgreSQL runtime, so a PostgreSQL claim could
  not be validated here.
- SQLCipher provides inspectable page-level encryption while preserving the
  existing SQLAlchemy schema, exact provenance queries and deterministic tests.
- This choice is not suitable evidence for multi-user database concurrency or
  production capacity. A later multi-user deployment should migrate to managed
  PostgreSQL with provider-confirmed encrypted volumes and backups.

`NANTINGALE_DATABASE_MODE=sqlcipher` selects the encrypted deployment path.
`NANTINGALE_DB_URL=sqlite:///...` remains the isolated unit-test/development path.
Production startup rejects plain SQLite.

## Decision Gate 2: at-rest scope

- Database: the entire SQLCipher file is encrypted, not selected fields.
- Backup: `backup_encrypted_db.py` exports to a separately keyed SQLCipher file.
- Restore: `restore_encrypted_backup.py` exports the backup into a new database
  under a rotated database key. Neither script overwrites an existing file.
- Keys: database, backup and restored-database keys come only from process
  environment variables. They are never put in the URL, repository, database,
  AuditLog or application log. For a maintained deployment, inject them from an
  OS/cloud secret manager and rotate by encrypted export/restore.
- The three keys must each contain at least 32 characters and must be pairwise
  distinct. Production startup and storage scripts reject missing, short or
  duplicate keys before accepting traffic or writing an output file.
- Field encryption: not added. Whole-database encryption is the one protection
  layer; adding overlapping JSON/IC/phone encryption without a query/migration
  design would create more key paths and risk breaking provenance.
- Memory: authorized application processes necessarily hold decrypted synthetic
  values while serving a request. SQLCipher does not protect process memory.
- Search/provenance/migration: the existing query and exact-span contracts are
  unchanged after the database is opened by an authorized process. The current
  canonical fixture is reseeded into a new encrypted database; no real data is
  migrated because the project contains synthetic data only.

Actual evidence on 2026-08-27:

```text
SQLCipher: 4.12.0 community
encrypted database: plaintext_header=false, plain_reader_blocked=true, 13 tables
encrypted backup:   plaintext_header=false, plain_reader_blocked=true, 13 tables
restored database:  plaintext_header=false, plain_reader_blocked=true, 13 tables
seed counts: 2 patients, 14 artifacts
```

## Decision Gate 3: TLS termination

Selected: **Caddy 2.11.4**.

- Caddy binds only to loopback, listens on `http://127.0.0.1:8080`, and redirects every path/query to
  `https://127.0.0.1:8443`.
- Caddy terminates TLS and serves the built SPA. `/api/*` is reverse-proxied to
  FastAPI bound only to `127.0.0.1:8000`.
- The current local Demo uses Caddy's local CA; verification must explicitly
  trust `deploy/caddy-data/caddy/pki/authorities/local/root.crt`. Do not bypass
  browser certificate warnings.
- `skip_install_trust` is set in the Caddyfile, so Caddy does not attempt to
  install its local root into Windows/browser trust. Installation or bypass is
  forbidden unless the owner separately authorizes it.
- A public hostname must remove `local_certs` and use Caddy's public ACME
  certificate flow before exposure. The API must remain loopback/private.

Actual evidence on 2026-08-27:

```text
HTTP redirect: 301 to https://127.0.0.1:8443/<same path/query>
TLS protocol: TLSv1.3
cipher: TLS_AES_128_GCM_SHA256
issuer: Caddy Local Authority - ECC Intermediate
certificate verification: OK
frontend: 200
anonymous protected API: 401
```

## Web/session hardening

`backend/app/security.py` supplies the deployment gate:

- exact HTTPS Origin verification for every unsafe request (CSRF strategy);
- CORS preflight only for the configured frontend origin;
- `Secure + HttpOnly + SameSite=Lax` session cookie, including cookie clearing;
- HSTS, CSP, no-sniff, frame, referrer and permissions headers;
- one-megabyte default actual-body limit (not only `Content-Length`);
- basic process-local IP/route rate limits for login/register/invite;
- generic 500 response and metadata-only error logging;
- production startup rejects demo auth, insecure cookies, debug mode, non-HTTPS
  origin, short/missing database key and non-SQLCipher storage.

The limiter is deliberately process-local because this is a single-process
Demo. It is not a distributed abuse-prevention claim.

## Reproduce

Install dependencies and build the SPA first. Copy `deploy/.env.example` to an
untracked `deploy/.env.local`, replace every placeholder with independent random
secrets, and set private absolute paths for the database and Caddy state.

The backend deliberately does **not** load `.env` files. In every PowerShell
terminal that will run the backend, storage scripts or Caddy, paste the
following allowlisted import command so variables enter that current process:

```powershell
Set-Location E:\桌面\Nantingale\deploy
$d5EnvFile = (Resolve-Path -LiteralPath .\.env.local).Path
Get-Content -LiteralPath $d5EnvFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith('#')) { return }
    if ($line -notmatch '^([A-Z][A-Z0-9_]*)=(.*)$') { throw 'Invalid NAME=value line' }
    $name = $Matches[1]; $value = $Matches[2].Trim()
    if (-not ($name.StartsWith('NANTINGALE_') -or $name -in @('XDG_DATA_HOME','XDG_CONFIG_HOME'))) { throw "Variable outside D5 allowlist: $name" }
    if (-not $value -or $value.Contains('<') -or $value.Contains('>')) { throw "Replace placeholder: $name" }
    [Environment]::SetEnvironmentVariable($name, $value, 'Process')
}
```

The command rejects unedited placeholders and variables outside
`NANTINGALE_*`, `XDG_DATA_HOME` and `XDG_CONFIG_HOME`, and never prints values.
It does not require changing or bypassing the PowerShell execution policy.

From `backend` in a PowerShell process where the variables were imported:

```powershell
.venv\Scripts\python.exe scripts\init_encrypted_demo.py
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

From `deploy`, with the verified Caddy binary available and the same import
performed so `XDG_DATA_HOME` / `XDG_CONFIG_HOME` are explicit private paths:

```powershell
caddy validate --config Caddyfile --adapter caddyfile
caddy run --config Caddyfile --adapter caddyfile
```

Storage evidence:

```powershell
.venv\Scripts\python.exe scripts\backup_encrypted_db.py --output <new-backup-path>
.venv\Scripts\python.exe scripts\restore_encrypted_backup.py --input <backup> --output <new-restore-path>
```

TLS/session evidence:

```powershell
.venv\Scripts\python.exe scripts\verify_secure_demo.py --ca-file <caddy-root.crt>
```

The local root CA is intentionally not committed. Installing it into an OS or
browser trust store is a user-controlled security decision and must be reversed
after the Demo if it is no longer needed.

Invite preview is `POST /api/auth/invites/preview`; the bearer token exists only
in the JSON body and the old URL-token endpoint is removed. Uvicorn access
logging remains disabled and Caddy production access logging remains off as
defense in depth. A dedicated offline-upstream probe enables temporary Caddy
access/error logging and verifies that a fake body token appears in neither
Caddy stdout/stderr, the inactive application log sink nor the 502 response.
