from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AuditLog, SystemSettings
from app.system_settings import SETTINGS_ID, ensure_settings


def test_concurrent_first_read_initializes_one_device_row(monkeypatch):
    barrier = Barrier(2)
    from app import system_settings

    original = system_settings._bootstrap_values

    def synchronized_bootstrap():
        values = original()
        barrier.wait(timeout=5)
        return values

    monkeypatch.setattr(system_settings, "_bootstrap_values", synchronized_bootstrap)

    def load_once():
        with SessionLocal() as db:
            return ensure_settings(db).settings_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: load_once(), range(2)))

    assert results == [SETTINGS_ID, SETTINGS_ID]
    with SessionLocal() as db:
        assert db.scalar(select(func.count()).select_from(SystemSettings)) == 1


def test_admin_settings_are_device_scoped_safe_defaults_and_admin_only(
    client, clinician_client, staff_client, patient_client, admin_client, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("NANTINGALE_VOICE_ENABLED", "false")
    assert client.get("/api/admin/system-settings").status_code == 401
    for role_client in (clinician_client, staff_client, patient_client):
        assert role_client.get("/api/admin/system-settings").status_code == 403
    response = admin_client.get("/api/admin/system-settings")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"scope", "version", "ai", "voice", "updated_at"}
    assert body["scope"] == "device"
    assert body["ai"]["mode"] == "local"
    assert body["ai"]["key_configured"] is False
    assert body["voice"]["enabled"] is False
    assert "path" not in response.text.lower()


def test_key_rotation_enable_remove_never_persists_or_returns_secret(
    admin_client, db_session, monkeypatch
):
    vault = {}
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "mock")
    monkeypatch.setattr("app.api.system_settings.store_secret", lambda deployment, ref, value: vault.__setitem__((deployment, ref), value))
    monkeypatch.setattr("app.api.system_settings.read_secret", lambda deployment, ref: vault.get((deployment, ref)))
    monkeypatch.setattr("app.system_settings.read_secret", lambda deployment, ref: vault.get((deployment, ref)))
    monkeypatch.setattr("app.api.system_settings.delete_secret", lambda deployment, ref: vault.pop((deployment, ref), None))
    monkeypatch.setattr("app.api.system_settings.DeepSeekAdapter.verify_connection", lambda self: None)

    initial = admin_client.get("/api/admin/system-settings").json()
    raw_key = "synthetic-deepseek-key-not-real-1234"
    saved = admin_client.post(
        "/api/admin/system-settings/deepseek-key",
        json={"expected_version": initial["version"], "api_key": raw_key},
    )
    assert saved.status_code == 200
    assert raw_key not in saved.text
    assert saved.json()["ai"]["key_suffix"] == "1234"
    row = db_session.get(SystemSettings, "device")
    assert raw_key not in repr({column.name: getattr(row, column.name) for column in row.__table__.columns})
    assert raw_key not in repr([audit.details for audit in db_session.scalars(select(AuditLog)).all()])

    enabled = admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": saved.json()["version"], "ai_mode": "deepseek"},
    )
    assert enabled.status_code == 200
    assert enabled.json()["ai"]["mode"] == "deepseek"
    removed = admin_client.request(
        "DELETE",
        "/api/admin/system-settings/deepseek-key",
        json={"expected_version": enabled.json()["version"]},
    )
    assert removed.status_code == 200
    assert removed.json()["ai"]["mode"] == "local"
    assert removed.json()["ai"]["key_configured"] is False
    assert not vault


def test_deepseek_and_voice_activation_fail_closed_and_use_version_cas(
    admin_client, monkeypatch
):
    initial = admin_client.get("/api/admin/system-settings").json()
    no_key = admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": initial["version"], "ai_mode": "deepseek"},
    )
    assert no_key.status_code == 409
    monkeypatch.setattr("app.api.system_settings.model_status", lambda: {
        "status": "missing", "error_code": None, "model": "faster-whisper-base",
        "revision": "pinned", "download_bytes_approx": 148_000_000,
    })
    voice = admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": initial["version"], "voice_enabled": True},
    )
    assert voice.status_code == 409
    stale = admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": initial["version"] + 99, "ai_mode": "local"},
    )
    assert stale.status_code == 409


def test_environment_key_is_bootstrap_compatible(admin_client, monkeypatch):
    monkeypatch.setenv("NANTINGALE_LLM_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-synthetic-key-9876")
    response = admin_client.get("/api/admin/system-settings")
    assert response.status_code == 200
    body = response.json()
    assert body["ai"]["mode"] == "deepseek"
    assert body["ai"]["key_configured"] is True
    assert body["ai"]["key_source"] == "environment"
    assert body["ai"]["key_suffix"] == "9876"
    assert "environment-synthetic-key" not in response.text


def test_voice_toggle_updates_runtime_capabilities_and_keeps_disabled_reason_visible(
    admin_client, clinician_client, monkeypatch
):
    monkeypatch.setenv("NANTINGALE_VOICE_ENABLED", "false")
    monkeypatch.setattr("app.api.system_settings.model_status", lambda: {
        "status": "ready", "error_code": None, "model": "faster-whisper-base",
        "revision": "pinned", "download_bytes_approx": 148_000_000,
    })
    monkeypatch.setattr("app.api.voice.asr_runtime_ready", lambda provider: True)
    initial = admin_client.get("/api/admin/system-settings").json()
    enabled = admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": initial["version"], "voice_enabled": True},
    )
    assert enabled.status_code == 200
    capability = clinician_client.get("/api/voice/capabilities").json()
    assert capability["enabled"] is True
    assert capability["allowed_modes"] == ["doctor_consult"]
    disabled = admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": enabled.json()["version"], "voice_enabled": False},
    )
    assert disabled.status_code == 200
    capability = clinician_client.get("/api/voice/capabilities").json()
    assert capability["allowed_modes"] == []
    assert capability["eligible_modes"] == ["doctor_consult"]
    assert capability["disabled_reason"] == "disabled_by_admin"


def test_voice_model_download_is_admin_only_and_single_job_safe(
    admin_client, clinician_client, monkeypatch
):
    missing = {
        "status": "missing", "error_code": None, "model": "faster-whisper-base",
        "revision": "pinned", "download_bytes_approx": 148_000_000,
    }
    downloading = {**missing, "status": "downloading"}
    monkeypatch.setattr("app.api.system_settings.model_status", lambda: missing)
    monkeypatch.setattr("app.api.system_settings.start_model_download", lambda callback: downloading)
    assert clinician_client.post("/api/admin/system-settings/voice-model").status_code == 403
    response = admin_client.post("/api/admin/system-settings/voice-model")
    assert response.status_code == 202
    assert response.json()["status"] == "downloading"
