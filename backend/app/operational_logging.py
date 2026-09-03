"""Allowlisted operational logging (F_A4).

Operational logs are the process-stderr records emitted by the application for
diagnostics. They are deliberately NOT the clinical ``AuditLog``:

- Clinical ``AuditLog`` lives in the encrypted SQLCipher database, carries the
  who/acted-on-what metadata contract, and is read through role-scoped API
  endpoints with its own retention ownership (owner policy).
- Operational logs are structured single-line JSON to stderr only. No file, no
  rotation, no retention is invented here; host-side capture/retention of the
  process stream is ``NOT_ESTABLISHED``.

Permissions (in order, primary -> last resort):

1. Fixed event names and fixed field keys. Unknown keys are dropped; unknown
   event names collapse to ``invalid_event``.
2. **Value validation** — each allowed field has a validator over a narrow
   domain (fixed enum / HTTP method / integer / symbol / route template /
   server request id). A value that does not match its domain is DROPPED, never
   emitted. This is what enforces "no patient message / Provider payload / free
   text" rather than a name-only allowlist.
3. A deterministic scrubber (IC/ID, phone, placeholder, long token-like) runs
   as defense in depth — it is never the permission to log unsafe values.

``emit_log`` must never raise: it sits on the unhandled-exception path and a
logging bug must not mask the original failure.
"""
from __future__ import annotations

import json
import logging
import re

from starlette.routing import BaseRoute

logger = logging.getLogger("nantingale.operational")

EVENT_ALLOWLIST = frozenset(
    {
        "unhandled_error",
        "sweep_error",
        "provider_error",
        "provider_usage",
    }
)

FIELD_ALLOWLIST = frozenset(
    {
        "event",
        "method",
        "route_template",
        "status_code",
        "error_code",
        "error_type",
        "latency_ms",
        "request_id",
        "model",
        "input_tokens",
        "output_tokens",
    }
)

_HTTP_METHODS = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"})
_ERROR_CODE_ALLOWLIST = frozenset({"internal_error", "provider_timeout"})
_MODEL_ALLOWLIST = frozenset({"deepseek-v4-flash"})
# Exception type names only: a Python class-name shape ending in Error/Exception.
# This rejects free text (spaces, separators) and identifier-shaped non-exception
# strings such as a patient-message sentinel.
_EXCEPTION_TYPE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,63}(?:Error|Exception)$")
# A Starlette matched route template: slash-separated literals and {params},
# with no spaces, query, fragment or authority characters.
_ROUTE_TEMPLATE_RE = re.compile(r"^/[A-Za-z0-9_/{}.@~-]*$")
_REQUEST_ID_RE = re.compile(r"^req_[0-9a-f]{16}$")
_HANDLED_EXCEPTION_ATTR = "_nantingale_sanitized_exception"

# Defense-in-depth scrubber patterns (mirror the M4 redaction classes, plus a
# generic long token-like class for accidental secrets). These are never the
# permission to log unsafe values.
_IC_RE = re.compile(r"\b\d{6}-\d{2}-\d{4}\b")
_PHONE_RE = re.compile(r"\b(?:\+?60|0060|0)?1\d[-\s]?\d{3,4}[-\s]?\d{4}\b")
_PLACEHOLDER_RE = re.compile(r"\[(?:NAME|ID|PHONE)_\d+\]")
_LONG_TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{40,}")


def _is_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _valid_method(value) -> bool:
    return isinstance(value, str) and value in _HTTP_METHODS


def _route_template_value(value) -> str | None:
    """Return a template only when it came from Starlette's matched route.

    A plain string is deliberately rejected even when it looks path-shaped:
    syntax alone cannot distinguish ``/patients/{id}`` from a raw path carrying
    a concrete patient id.
    """
    if not isinstance(value, BaseRoute):
        return None
    path = getattr(value, "path", None)
    if not isinstance(path, str) or not _ROUTE_TEMPLATE_RE.fullmatch(path):
        return None
    return path


def _valid_status_code(value) -> bool:
    return _is_int(value) and 100 <= value <= 599


def _valid_error_code(value) -> bool:
    return isinstance(value, str) and value in _ERROR_CODE_ALLOWLIST


def _valid_symbol(value) -> bool:
    return isinstance(value, str) and bool(_EXCEPTION_TYPE_RE.fullmatch(value))


def _valid_latency(value) -> bool:
    return _is_int(value) and value >= 0


def _valid_request_id(value) -> bool:
    return isinstance(value, str) and bool(_REQUEST_ID_RE.fullmatch(value))


def _valid_model(value) -> bool:
    return isinstance(value, str) and value in _MODEL_ALLOWLIST


def _valid_tokens(value) -> bool:
    return _is_int(value) and value >= 0


_FIELD_VALIDATORS = {
    "method": _valid_method,
    "status_code": _valid_status_code,
    "error_code": _valid_error_code,
    "error_type": _valid_symbol,
    "latency_ms": _valid_latency,
    "request_id": _valid_request_id,
    "model": _valid_model,
    "input_tokens": _valid_tokens,
    "output_tokens": _valid_tokens,
}

_LEVELS = {
    "debug": logger.debug,
    "info": logger.info,
    "warning": logger.warning,
    "error": logger.error,
    "critical": logger.critical,
}


class _SuppressHandledUvicornTraceback(logging.Filter):
    """Suppress only the duplicate traceback for an application-marked error."""

    def filter(self, record):
        try:
            if "Exception in ASGI application" not in record.getMessage():
                return True
            exc_info = record.exc_info
            if not isinstance(exc_info, tuple) or len(exc_info) < 2:
                return True
            exception = exc_info[1]
            return not bool(getattr(exception, _HANDLED_EXCEPTION_ATTR, False))
        except Exception:
            return True


def mark_exception_sanitized(exception: BaseException) -> None:
    """Mark the exact exception already covered by the sanitized app record."""
    try:
        setattr(exception, _HANDLED_EXCEPTION_ATTR, True)
    except Exception:
        # If an exotic exception cannot carry the marker, retain uvicorn's
        # traceback rather than suppressing an unproven record.
        pass


def suppress_server_duplicate_tracebacks() -> None:
    """Drop the server's duplicate raw traceback for handled exceptions.

    Starlette 1.6 wires an ``Exception`` handler into ``ServerErrorMiddleware``
    and ALWAYS re-raises after it returns, so uvicorn logs a second raw
    "Exception in ASGI application" traceback. Our handler already emitted the
    sanitized ``unhandled_error`` record, so the server's duplicate (which can
    carry exception text / provider payloads / SQL fragments) is dropped here.
    """

    for name in ("uvicorn", "uvicorn.error"):
        target = logging.getLogger(name)
        if not any(
            isinstance(item, _SuppressHandledUvicornTraceback)
            for item in target.filters
        ):
            target.addFilter(_SuppressHandledUvicornTraceback())


def _scrub(value):
    if isinstance(value, bool) or isinstance(value, int):
        return value
    text = str(value)
    text = _IC_RE.sub("<redacted>", text)
    text = _PHONE_RE.sub("<redacted>", text)
    text = _PLACEHOLDER_RE.sub("<redacted>", text)
    text = _LONG_TOKEN_RE.sub("<redacted>", text)
    return text


def _validate(key: str, value) -> bool:
    validator = _FIELD_VALIDATORS.get(key)
    if validator is None:
        return False
    try:
        return validator(value)
    except Exception:
        return False


def _validated_value(key: str, value):
    if key == "route_template":
        return _route_template_value(value)
    return value if _validate(key, value) else None


def emit_log(event: str, *, level: str = "info", **fields) -> None:
    """Emit one allowlisted, value-validated operational log record.

    Never raises: any failure collapses to a minimal ``logging_failure`` record.
    """
    try:
        record: dict = {
            "event": event if (isinstance(event, str) and event in EVENT_ALLOWLIST) else "invalid_event"
        }
        for key, value in fields.items():
            if key not in FIELD_ALLOWLIST or value is None:
                continue
            validated = _validated_value(key, value)
            if validated is not None:
                record[key] = _scrub(validated)
        message = json.dumps(record, sort_keys=True, ensure_ascii=False, default=str)
    except Exception:
        try:
            message = json.dumps({"event": "logging_failure"})
        except Exception:
            message = '{"event":"logging_failure"}'
    try:
        _LEVELS.get(level, logger.info)(message)
    except Exception:
        pass
