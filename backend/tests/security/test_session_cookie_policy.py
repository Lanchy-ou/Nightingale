from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app
from app.security import reset_rate_limits, validate_production_settings
from seed import fixture


ORIGIN = "https://127.0.0.1:8443"


def _strict(monkeypatch, *, rate_limit: int = 20) -> None:
    monkeypatch.setenv("NANTINGALE_SECURITY_MODE", "strict")
    monkeypatch.setenv("NANTINGALE_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("NANTINGALE_SECURE_COOKIES", "true")
    monkeypatch.setenv("NANTINGALE_AUTH_RATE_LIMIT", str(rate_limit))
    monkeypatch.setenv("NANTINGALE_AUTH_RATE_WINDOW_SECONDS", "60")
    reset_rate_limits()


def _login(client: TestClient, *, origin: str | None = ORIGIN):
    headers = {"Origin": origin} if origin else {}
    return client.post(
        "/api/auth/login",
        headers=headers,
        json={
            "email": fixture.DEMO_EMAILS[fixture.USER_CLINICIAN_ID],
            "password": fixture.DEMO_PASSWORD,
        },
    )


def test_strict_cookie_and_security_header_contract(monkeypatch):
    _strict(monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        response = _login(client)

    assert response.status_code == 200, response.text
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "Secure" in cookie
    assert "SameSite=Lax" in cookie
    assert response.headers["strict-transport-security"].startswith("max-age=")
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
    assert response.headers["cache-control"] == "no-store"


def test_strict_csrf_origin_gate_covers_login_and_authenticated_writes(monkeypatch):
    _strict(monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        assert _login(client, origin=None).status_code == 403
        assert _login(client, origin="https://evil.example").status_code == 403
        assert _login(client).status_code == 200

        no_origin = client.post("/api/auth/logout")
        assert no_origin.status_code == 403
        assert no_origin.json()["error"]["code"] == "csrf_rejected"

        logout = client.post("/api/auth/logout", headers={"Origin": ORIGIN})
        assert logout.status_code == 200
        cleared = logout.headers["set-cookie"]
        assert "HttpOnly" in cleared
        assert "Secure" in cleared
        assert "SameSite=Lax" in cleared


def test_cors_preflight_allows_only_the_deployment_origin(monkeypatch):
    _strict(monkeypatch)
    with TestClient(app, base_url=ORIGIN) as client:
        allowed = client.options(
            "/api/auth/login",
            headers={
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        denied = client.options(
            "/api/auth/login",
            headers={
                "Origin": "https://evil.example",
                "Access-Control-Request-Method": "POST",
            },
        )

    assert allowed.status_code == 204
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert denied.status_code == 403
    assert "access-control-allow-origin" not in denied.headers


def test_request_body_limit_checks_actual_bytes_not_only_content_length(monkeypatch):
    _strict(monkeypatch)
    monkeypatch.setenv("NANTINGALE_MAX_REQUEST_BYTES", "256")
    with TestClient(app, base_url=ORIGIN) as client:
        response = client.post(
            "/api/auth/login",
            headers={"Origin": ORIGIN},
            content=b"{" + (b"x" * 300) + b"}",
        )

    assert response.status_code == 413
    assert response.json()["error"]["code"] == "request_too_large"


def test_basic_auth_rate_limit_is_ip_and_route_scoped(monkeypatch):
    _strict(monkeypatch, rate_limit=2)
    with TestClient(app, base_url=ORIGIN) as client:
        first = _login(client)
        second = _login(client)
        blocked = _login(client)

    assert first.status_code == 200
    assert second.status_code == 200
    assert blocked.status_code == 429
    assert blocked.headers["retry-after"] == "60"
    assert blocked.json()["error"]["code"] == "rate_limited"


def test_production_settings_fail_closed_for_plain_sqlite(monkeypatch):
    monkeypatch.setenv("NANTINGALE_ENV", "production")
    monkeypatch.setenv("NANTINGALE_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("NANTINGALE_SECURE_COOKIES", "true")
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)

    errors = validate_production_settings(
        database_driver="sqlite+pysqlite",
        database_mode="sqlite",
        database_key="",
        backup_key="",
        restored_database_key="",
    )

    assert any("SQLCipher" in error for error in errors)


def test_production_settings_reject_duplicate_storage_keys(monkeypatch):
    monkeypatch.setenv("NANTINGALE_FRONTEND_ORIGIN", ORIGIN)
    monkeypatch.setenv("NANTINGALE_SECURE_COOKIES", "true")
    monkeypatch.delenv("NANTINGALE_DEMO_AUTH", raising=False)
    duplicate = "same-storage-key-must-be-rejected-123456"

    errors = validate_production_settings(
        database_driver="sqlite+pysqlcipher",
        database_mode="sqlcipher",
        database_key=duplicate,
        backup_key=duplicate,
        restored_database_key="independent-restored-database-key-123456",
    )

    assert any("pairwise distinct" in error for error in errors)
