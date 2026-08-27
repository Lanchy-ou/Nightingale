from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.main import app


SENTINEL = "D5_RAW_PROVIDER_PAYLOAD_SECRET_SENTINEL"
PATH = "/api/__d5_sanitized_error_probe"


def _raise_sensitive_error():
    raise RuntimeError(SENTINEL)


if not any(getattr(route, "path", None) == PATH for route in app.routes):
    app.add_api_route(PATH, _raise_sensitive_error, methods=["GET"], include_in_schema=False)


def test_unhandled_error_body_and_application_log_are_sanitized(caplog):
    caplog.set_level(logging.ERROR)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get(PATH)

    assert response.status_code == 500
    assert response.json() == {
        "error": {"code": "internal_error", "message": "Internal server error"}
    }
    assert SENTINEL not in response.text
    assert SENTINEL not in caplog.text
