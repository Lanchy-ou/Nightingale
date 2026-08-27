# D5 Deployment and Security Decisions

## Scope

This document describes the verified single-machine synthetic-data demo. It is not a public-host, production-security, penetration-test, compliance, or medical-safety certification.

## Database

Selected deployment mode: SQLCipher encrypted SQLite.

- Unit tests/development may use disposable plain SQLite.
- Product startup in production mode requires SQLCipher.
- NANTINGALE_DB_KEY, NANTINGALE_BACKUP_KEY, and NANTINGALE_RESTORED_DB_KEY must each be 32+ characters and pairwise different.
- Database initialization, backup, and restore refuse to overwrite existing targets.
- Backup is exported with a separate key.
- Restore writes a new database under a rotated key.
- Authorized application memory contains decrypted synthetic data; file encryption does not protect process memory.

Current observed runtime: SQLCipher 4.12.0 community. Database, backup, and restore files had no plaintext SQLite header and rejected a normal SQLite reader.

## TLS and topology

Selected edge: Caddy 2.11.4.

- FastAPI binds to 127.0.0.1:8000.
- Caddy binds to 127.0.0.1:8080 and 127.0.0.1:8443.
- HTTP redirects to HTTPS while preserving path/query.
- Caddy serves frontend/dist and proxies /api/* to FastAPI.
- Local-CA trust is explicit; Caddy sets skip_install_trust.
- Production access logging remains disabled to reduce accidental sensitive logging.

Current secure-demo verification observed TLS 1.3, TLS_AES_128_GCM_SHA256, verified local-CA chain, secure cookie attributes, exact-origin CSRF/CORS, security headers, logout revocation, and anonymous denial.

## Production configuration gate

NANTINGALE_ENV=production rejects:

- plain SQLite;
- missing/short/same database keys;
- NANTINGALE_DEMO_AUTH=true;
- non-HTTPS NANTINGALE_FRONTEND_ORIGIN;
- NANTINGALE_SECURE_COOKIES not true;
- debug mode;
- insecure security mode.

## Reproduce

Install backend dependencies and build the frontend. Supply private environment variables through a secret manager or process environment; the backend does not load .env automatically.

From backend:

~~~powershell
.venv\Scripts\python.exe scripts\init_encrypted_demo.py
.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
~~~

From deploy with private XDG_DATA_HOME and XDG_CONFIG_HOME:

~~~powershell
caddy validate --config Caddyfile --adapter caddyfile
caddy run --config Caddyfile --adapter caddyfile
~~~

Verify without bypassing TLS:

~~~powershell
Set-Location backend
.venv\Scripts\python.exe scripts\verify_secure_demo.py --ca-file <private-caddy-root.crt>
~~~

Storage evidence:

~~~powershell
.venv\Scripts\python.exe scripts\backup_encrypted_db.py --output <new-backup-path>
.venv\Scripts\python.exe scripts\restore_encrypted_backup.py --input <backup> --output <new-restore-path>
~~~

## Secrets and private assets

Committed files contain no environment secrets, SQLCipher databases/backups, Caddy CA keys/state, Provider keys, model weights, raw recordings, or real patient data. The Caddy binary and local state are ignored. High-confidence secret scanning and tracked/untracked asset audits are required before submission.

## Limitations

The topology is loopback-only and single-machine. It does not prove multi-user capacity, distributed rate limiting, external certificate automation, disaster recovery, endpoint hardening outside the tested host, or production operations.
