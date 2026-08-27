"""D5 web/session hardening and production configuration gates.

The deployed single-machine demo is same-origin behind Caddy.  Unsafe browser
requests therefore require the exact configured HTTPS Origin; SameSite=Lax is
an additional cookie boundary, not the sole CSRF control.
"""
from __future__ import annotations

import math
import os
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlparse

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from .errors import error_response

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
DEFAULT_MAX_REQUEST_BYTES = 1_048_576
DEFAULT_AUTH_RATE_LIMIT = 10
DEFAULT_AUTH_RATE_WINDOW_SECONDS = 60


def _truthy(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def production_mode() -> bool:
    return os.environ.get("NANTINGALE_ENV", "development").strip().lower() == "production"


def strict_security_enabled() -> bool:
    return production_mode() or os.environ.get(
        "NANTINGALE_SECURITY_MODE", ""
    ).strip().lower() == "strict"


def frontend_origin() -> str:
    return os.environ.get("NANTINGALE_FRONTEND_ORIGIN", "").strip().rstrip("/")


def max_request_bytes() -> int:
    raw = os.environ.get("NANTINGALE_MAX_REQUEST_BYTES", str(DEFAULT_MAX_REQUEST_BYTES))
    try:
        value = int(raw)
    except ValueError:
        return DEFAULT_MAX_REQUEST_BYTES
    return value if value > 0 else DEFAULT_MAX_REQUEST_BYTES


class _RateLimiter:
    """Small, process-local fixed-window limiter for the single-machine demo.

    It is deliberately not presented as distributed or production-capacity
    infrastructure.  The Caddy/FastAPI deployment is one process and this
    gate protects its invite/login/register endpoints from basic bursts.
    """

    def __init__(self) -> None:
        self._entries: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def reset(self) -> None:
        with self._lock:
            self._entries.clear()

    def allow(self, key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            entries = self._entries[key]
            while entries and entries[0] <= cutoff:
                entries.popleft()
            if len(entries) >= limit:
                retry = max(1, math.ceil(window_seconds - (now - entries[0])))
                return False, retry
            entries.append(now)
        return True, window_seconds


_auth_rate_limiter = _RateLimiter()


def reset_rate_limits() -> None:
    """Test/support hook; never changes persisted security state."""
    _auth_rate_limiter.reset()


def _rate_limit_category(path: str) -> str | None:
    if path == "/api/auth/login":
        return "login"
    if path == "/api/auth/register":
        return "register"
    if path.startswith("/api/auth/invites"):
        return "invite"
    return None


def _client_ip(request: Request) -> str:
    # The D5 backend binds to loopback and Caddy is the only upstream.  Trust
    # X-Forwarded-For only under the explicit deployment flag; otherwise a
    # direct client must not be able to choose its own limiter identity.
    if _truthy("NANTINGALE_TRUST_PROXY"):
        forwarded = request.headers.get("x-forwarded-for", "")
        if forwarded:
            return forwarded.split(",", 1)[0].strip()
    return request.client.host if request.client else "unknown"


def _apply_response_headers(response: Response, request: Request, *, strict: bool) -> None:
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    response.headers.setdefault(
        "Permissions-Policy", "camera=(), microphone=(), geolocation=()"
    )
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; base-uri 'self'; form-action 'self'; "
        "frame-ancestors 'none'; object-src 'none'; script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'",
    )
    if request.url.path.startswith("/api"):
        response.headers.setdefault("Cache-Control", "no-store")
    if strict:
        response.headers.setdefault(
            "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
        )

    allowed = frontend_origin()
    origin = request.headers.get("origin", "").rstrip("/")
    if allowed and origin == allowed:
        response.headers["Access-Control-Allow-Origin"] = allowed
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers.append("Vary", "Origin")


class SecurityMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        strict = strict_security_enabled()
        allowed = frontend_origin()
        origin = request.headers.get("origin", "").rstrip("/")

        if request.method == "OPTIONS" and request.headers.get(
            "access-control-request-method"
        ):
            if not allowed or origin != allowed:
                response = error_response(403, "cors_rejected", "Origin not allowed")
            else:
                response = Response(status_code=204)
                response.headers["Access-Control-Allow-Methods"] = "GET, POST, PATCH, OPTIONS"
                requested = request.headers.get(
                    "access-control-request-headers", "content-type"
                )
                response.headers["Access-Control-Allow-Headers"] = requested
                response.headers["Access-Control-Max-Age"] = "600"
            _apply_response_headers(response, request, strict=strict)
            return response

        if strict and request.method in UNSAFE_METHODS:
            fetch_site = request.headers.get("sec-fetch-site", "")
            if not allowed or origin != allowed or fetch_site == "cross-site":
                response = error_response(
                    403, "csrf_rejected", "Request origin verification failed"
                )
                _apply_response_headers(response, request, strict=strict)
                return response

        if strict:
            category = _rate_limit_category(request.url.path)
            if category is not None:
                try:
                    limit = max(1, int(os.environ.get(
                        "NANTINGALE_AUTH_RATE_LIMIT", str(DEFAULT_AUTH_RATE_LIMIT)
                    )))
                    window = max(1, int(os.environ.get(
                        "NANTINGALE_AUTH_RATE_WINDOW_SECONDS",
                        str(DEFAULT_AUTH_RATE_WINDOW_SECONDS),
                    )))
                except ValueError:
                    limit = DEFAULT_AUTH_RATE_LIMIT
                    window = DEFAULT_AUTH_RATE_WINDOW_SECONDS
                allowed_request, retry = _auth_rate_limiter.allow(
                    f"{_client_ip(request)}:{category}", limit, window
                )
                if not allowed_request:
                    response = error_response(
                        429, "rate_limited", "Too many authentication requests"
                    )
                    response.headers["Retry-After"] = str(retry)
                    _apply_response_headers(response, request, strict=strict)
                    return response

        if request.method in UNSAFE_METHODS:
            limit = max_request_bytes()
            content_length = request.headers.get("content-length")
            if content_length:
                try:
                    declared = int(content_length)
                except ValueError:
                    declared = limit + 1
                if declared > limit:
                    response = error_response(
                        413, "request_too_large", "Request body is too large"
                    )
                    _apply_response_headers(response, request, strict=strict)
                    return response
            body = await request.body()
            if len(body) > limit:
                response = error_response(
                    413, "request_too_large", "Request body is too large"
                )
                _apply_response_headers(response, request, strict=strict)
                return response

        response = await call_next(request)
        _apply_response_headers(response, request, strict=strict)
        return response


def validate_production_settings(
    *,
    database_driver: str,
    database_mode: str,
    database_key: str,
    backup_key: str,
    restored_database_key: str,
) -> list[str]:
    """Return non-secret production configuration failures.

    The caller raises once with the complete list so a deployment fails closed
    before accepting traffic.  Values are parameters to keep the gate directly
    testable without rebuilding the global SQLAlchemy engine.
    """
    errors: list[str] = []
    if database_mode != "sqlcipher" or database_driver != "sqlite+pysqlcipher":
        errors.append("D5 production storage must use the SQLCipher database mode")
    if len(database_key) < 32:
        errors.append("NANTINGALE_DB_KEY must contain at least 32 characters")
    if len(backup_key) < 32:
        errors.append("NANTINGALE_BACKUP_KEY must contain at least 32 characters")
    if len(restored_database_key) < 32:
        errors.append("NANTINGALE_RESTORED_DB_KEY must contain at least 32 characters")
    if all(
        len(key) >= 32
        for key in (database_key, backup_key, restored_database_key)
    ) and len({database_key, backup_key, restored_database_key}) != 3:
        errors.append("Database, backup and restored-database keys must be pairwise distinct")
    if _truthy("NANTINGALE_DEMO_AUTH"):
        errors.append("NANTINGALE_DEMO_AUTH must be disabled in production")
    origin = frontend_origin()
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.netloc:
        errors.append("NANTINGALE_FRONTEND_ORIGIN must be one exact HTTPS origin")
    if not _truthy("NANTINGALE_SECURE_COOKIES"):
        errors.append("NANTINGALE_SECURE_COOKIES must be true in production")
    if _truthy("NANTINGALE_DEBUG"):
        errors.append("NANTINGALE_DEBUG must be disabled in production")
    return errors
