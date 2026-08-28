from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_admin_settings_are_routed_and_secret_input_is_ephemeral():
    app = _read("frontend/src/App.tsx")
    workspace = _read("frontend/src/pages/AdminWorkspacePage.tsx")
    settings = _read("frontend/src/pages/AdminSettingsPage.tsx")
    api = _read("frontend/src/api.ts")
    assert "/admin/settings" in app
    assert "AI &amp; Voice settings" in workspace
    assert "AI API key" in settings
    assert "DeepSeek API key" not in settings
    assert "type=\"password\"" in settings
    assert "autoComplete=\"off\"" in settings
    assert "localStorage" not in settings
    assert "sessionStorage" not in settings
    assert "Test, save and enable" in settings
    assert "Currently active" in settings
    assert "Set up AI API" in settings
    assert 'type="radio"' in settings
    assert "<strong>AI API</strong>" in settings
    assert "Remove key" in settings
    assert "/api/admin/system-settings/deepseek-key" in api


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
