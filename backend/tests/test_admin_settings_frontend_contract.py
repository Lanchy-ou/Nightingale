from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_settings_are_clinic_scoped_and_device_secrets_are_not_editable():
    app = _read("frontend/src/App.tsx")
    workspace = _read("frontend/src/pages/AdminWorkspacePage.tsx")
    settings = _read("frontend/src/pages/AdminSettingsPage.tsx")
    api = _read("frontend/src/api.ts")
    assert "/admin/settings" in app
    assert "AI &amp; Voice settings" in workspace
    assert "Clinic setting" in settings
    assert "Use device default" in settings
    assert "Applies to this clinic only" in settings
    assert "type=\"password\"" not in settings
    assert "localStorage" not in settings
    assert "sessionStorage" not in settings
    assert 'type="radio"' in settings
    assert "Remove key" not in settings
    assert "/api/admin/clinic-settings" in api
    assert "storeDeepSeekKey" not in settings
    assert "prepareVoiceModel" not in settings


def test_voice_disabled_and_provider_labels_are_visible():
    voice = _read("frontend/src/components/VoiceCapture.tsx")
    checkin = _read("frontend/src/components/PatientCheckIn.tsx")
    detail = _read("frontend/src/components/ClinicalEventDetail.tsx")
    assert "Voice Capture is disabled by Admin" in voice
    assert "The local speech model is not installed" in voice
    assert "10_000" in voice and "releaseAll();" in voice
    for label in ("DeepSeek AI", "Local deterministic", "Safe fallback"):
        assert label in checkin
        assert label in detail
