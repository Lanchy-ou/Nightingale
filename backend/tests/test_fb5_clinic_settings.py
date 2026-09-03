from __future__ import annotations

from sqlalchemy import select

from app.models import AuditLog, ClinicSettings, SystemSettings, User
from app.system_settings import effective_ai_config, effective_voice_enabled, ensure_settings
from seed import fixture


def _clinic_b_admin(db_session) -> str:
    user_id = "usr_admin_fb5_settings_b"
    db_session.add(
        User(
            user_id=user_id,
            clinic_id=fixture.CLINIC_B_ID,
            name="Other Clinic Admin",
            role="admin",
            patient_id=None,
        )
    )
    db_session.commit()
    return user_id


def test_clinic_settings_inherit_device_defaults_and_hide_secret_metadata(
    admin_client, db_session, monkeypatch
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-device-key")
    device = ensure_settings(db_session)
    device.ai_mode = "deepseek"
    device.voice_enabled = False
    device.deepseek_key_source = "environment"
    device.deepseek_key_suffix = "-key"
    db_session.commit()

    response = admin_client.get("/api/admin/clinic-settings")
    assert response.status_code == 200
    body = response.json()
    assert body["scope"] == "clinic"
    assert body["clinic_id"] == fixture.CLINIC_ID
    assert body["ai"] == {
        "selected_mode": "inherit",
        "effective_mode": "deepseek",
        "inherited": True,
        "provider_available": True,
        "online_text_egress": True,
    }
    assert body["voice"]["selected_mode"] == "inherit"
    assert body["voice"]["effective_enabled"] is False
    serialized = response.text.lower()
    assert "key_suffix" not in serialized
    assert "credential_manager" not in serialized
    assert "synthetic-device-key" not in serialized


def test_two_clinics_have_independent_overrides_and_runtime_resolution(
    admin_client, client, db_session, monkeypatch
):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-device-key")
    device = ensure_settings(db_session)
    device.ai_mode = "deepseek"
    device.voice_enabled = False
    device.deepseek_key_source = "environment"
    db_session.commit()
    admin_b_id = _clinic_b_admin(db_session)

    initial_a = admin_client.get("/api/admin/clinic-settings").json()
    changed_a = admin_client.patch(
        "/api/admin/clinic-settings",
        json={
            "expected_version": initial_a["version"],
            "ai_mode": "local",
            "voice_mode": "disabled",
        },
    )
    assert changed_a.status_code == 200, changed_a.text

    initial_b = client.get(
        "/api/admin/clinic-settings", headers={"X-User-Id": admin_b_id}
    ).json()
    assert initial_b["ai"]["selected_mode"] == "inherit"
    assert initial_b["ai"]["effective_mode"] == "deepseek"

    db_session.expire_all()
    assert effective_ai_config(db_session, fixture.CLINIC_ID).provider == "local"
    assert effective_ai_config(db_session, fixture.CLINIC_B_ID).provider == "deepseek"
    assert effective_voice_enabled(db_session, fixture.CLINIC_ID) is False


def test_setting_deepseek_or_voice_fails_closed_when_device_unavailable(
    admin_client, db_session, monkeypatch
):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("Natingale_API_KEY", raising=False)
    device = ensure_settings(db_session)
    device.ai_mode = "local"
    device.deepseek_secret_ref = None
    device.deepseek_key_source = None
    db_session.commit()
    initial = admin_client.get("/api/admin/clinic-settings").json()

    unavailable_ai = admin_client.patch(
        "/api/admin/clinic-settings",
        json={"expected_version": initial["version"], "ai_mode": "deepseek"},
    )
    assert unavailable_ai.status_code == 409

    monkeypatch.setattr(
        "app.api.clinic_settings.model_status",
        lambda: {
            "status": "missing",
            "model": "tiny.en",
            "revision": "fixed",
            "download_bytes_approx": 1,
            "error_code": None,
        },
    )
    unavailable_voice = admin_client.patch(
        "/api/admin/clinic-settings",
        json={"expected_version": initial["version"], "voice_mode": "enabled"},
    )
    assert unavailable_voice.status_code == 409


def test_clinic_setting_cas_roles_audit_and_device_write_boundary(
    admin_client, clinician_client, db_session
):
    assert clinician_client.get("/api/admin/clinic-settings").status_code == 403
    assert clinician_client.patch(
        "/api/admin/clinic-settings",
        json={"expected_version": 1, "ai_mode": "local"},
    ).status_code == 403

    initial = admin_client.get("/api/admin/clinic-settings").json()
    changed = admin_client.patch(
        "/api/admin/clinic-settings",
        json={"expected_version": initial["version"], "ai_mode": "local"},
    )
    assert changed.status_code == 200
    stale = admin_client.patch(
        "/api/admin/clinic-settings",
        json={"expected_version": initial["version"], "voice_mode": "disabled"},
    )
    assert stale.status_code == 409

    assert admin_client.patch(
        "/api/admin/system-settings",
        json={"expected_version": 1, "ai_mode": "local"},
    ).status_code == 403
    assert admin_client.post(
        "/api/admin/system-settings/deepseek-key",
        json={"expected_version": 1, "api_key": "not-a-real-key"},
    ).status_code == 403
    assert admin_client.post("/api/admin/system-settings/voice-model").status_code == 403

    audits = db_session.scalars(
        select(AuditLog).where(
            AuditLog.action == "clinic_ai_mode_changed",
            AuditLog.clinic_id == fixture.CLINIC_ID,
        )
    ).all()
    assert len(audits) == 1
    assert audits[0].details == {"from": "inherit", "to": "local"}


def test_setting_inherit_restores_device_default(admin_client, db_session):
    device = ensure_settings(db_session)
    device.ai_mode = "local"
    device.voice_enabled = True
    db_session.commit()
    initial = admin_client.get("/api/admin/clinic-settings").json()
    changed = admin_client.patch(
        "/api/admin/clinic-settings",
        json={
            "expected_version": initial["version"],
            "ai_mode": "local",
            "voice_mode": "disabled",
        },
    ).json()
    restored = admin_client.patch(
        "/api/admin/clinic-settings",
        json={
            "expected_version": changed["version"],
            "ai_mode": "inherit",
            "voice_mode": "inherit",
        },
    )
    assert restored.status_code == 200
    body = restored.json()
    assert body["ai"]["inherited"] is True
    assert body["voice"]["inherited"] is True
    assert body["voice"]["effective_enabled"] is True
    db_session.expire_all()
    row = db_session.get(ClinicSettings, fixture.CLINIC_ID)
    assert row.ai_mode_override is None
    assert row.voice_enabled_override is None
