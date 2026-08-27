"""Verify the running Caddy + SQLCipher D5 demo without disabling TLS checks."""
from __future__ import annotations

import argparse
import hashlib
import json
import socket
import ssl
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPRedirectHandler, Request, build_opener
from urllib.parse import urlparse

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from seed import fixture  # noqa: E402


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _redirect(http_url: str) -> tuple[int, str]:
    try:
        build_opener(_NoRedirect).open(Request(http_url), timeout=5)
    except HTTPError as response:
        return response.code, response.headers.get("Location", "")
    raise RuntimeError("HTTP endpoint did not redirect")


def _tls_probe(base_url: str, ca_file: Path) -> dict[str, object]:
    parsed = urlparse(base_url)
    host = parsed.hostname
    port = parsed.port or 443
    if not host:
        raise RuntimeError("base URL must contain a host")
    context = ssl.create_default_context(cafile=str(ca_file))
    with socket.create_connection((host, port), timeout=5) as raw:
        with context.wrap_socket(raw, server_hostname=host) as secured:
            certificate = secured.getpeercert()
            der = secured.getpeercert(binary_form=True)
            expires = datetime.fromtimestamp(
                ssl.cert_time_to_seconds(certificate["notAfter"]), timezone.utc
            )
            if expires <= datetime.now(timezone.utc):
                raise RuntimeError("TLS certificate is expired")
            return {
                "protocol": secured.version(),
                "cipher": secured.cipher()[0],
                "issuer": certificate.get("issuer"),
                "not_after": expires.isoformat(),
                "sha256_fingerprint": hashlib.sha256(der).hexdigest(),
                "verification": "OK",
            }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://127.0.0.1:8443")
    parser.add_argument("--http-url", default="http://127.0.0.1:8080/probe")
    parser.add_argument("--ca-file", required=True, type=Path)
    args = parser.parse_args()

    base = args.base_url.rstrip("/")
    redirect_status, location = _redirect(args.http_url)
    if redirect_status not in {301, 302, 307, 308} or not location.startswith(base):
        raise RuntimeError("HTTP redirect does not target the configured HTTPS origin")

    tls = _tls_probe(base, args.ca_file.resolve())
    with httpx.Client(verify=str(args.ca_file.resolve()), trust_env=False) as client:
        frontend = client.get(base + "/")
        anonymous = client.get(base + "/api/auth/session")
        blocked = client.post(
            base + "/api/auth/login",
            json={
                "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
                "password": fixture.DEMO_PASSWORD,
            },
        )
        login = client.post(
            base + "/api/auth/login",
            headers={"Origin": base},
            json={
                "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
                "password": fixture.DEMO_PASSWORD,
            },
        )
        allowed_preflight = client.options(
            base + "/api/auth/login",
            headers={
                "Origin": base,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied_preflight = client.options(
            base + "/api/auth/login",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )
        logout = client.post(base + "/api/auth/logout", headers={"Origin": base})
        after_logout = client.get(base + "/api/patients")

    cookie = login.headers.get("set-cookie", "")
    required_headers = {
        "strict-transport-security",
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
    }
    missing = sorted(required_headers - set(anonymous.headers))
    checks = {
        "frontend_status": frontend.status_code,
        "anonymous_api_status": anonymous.status_code,
        "csrf_without_origin_status": blocked.status_code,
        "login_status": login.status_code,
        "secure_cookie": all(
            marker in cookie for marker in ("Secure", "HttpOnly", "SameSite=Lax")
        ),
        "cors_allowed_status": allowed_preflight.status_code,
        "cors_denied_status": denied_preflight.status_code,
        "logout_status": logout.status_code,
        "after_logout_status": after_logout.status_code,
        "missing_security_headers": missing,
    }
    expected = {
        "frontend_status": 200,
        "anonymous_api_status": 401,
        "csrf_without_origin_status": 403,
        "login_status": 200,
        "secure_cookie": True,
        "cors_allowed_status": 204,
        "cors_denied_status": 403,
        "logout_status": 200,
        "after_logout_status": 401,
        "missing_security_headers": [],
    }
    if checks != expected:
        raise RuntimeError(f"Secure demo verification failed: {checks}")
    print(
        json.dumps(
            {
                "status": "SECURE_DEMO_VERIFICATION_PASS",
                "redirect": {"status": redirect_status, "location": location},
                "tls": tls,
                "checks": checks,
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
