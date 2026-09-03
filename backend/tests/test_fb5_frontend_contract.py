from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_setup_route_uses_fragment_token_and_returns_to_existing_login():
    app = _read("frontend/src/App.tsx")
    setup = _read("frontend/src/pages/SetupPage.tsx")
    api = _read("frontend/src/api.ts")
    assert "path.startsWith('/setup')" in app
    assert "window.location.hash.slice(1)" in setup
    assert "window.location.search" not in setup
    assert "/api/onboarding/preview" in api
    assert "/api/onboarding/complete" in api
    assert "Sign in" in setup
    assert "onAuthenticated" not in setup


def test_admin_patient_import_has_preview_commit_report_and_no_auto_invite():
    workspace = _read("frontend/src/pages/AdminWorkspacePage.tsx")
    page = _read("frontend/src/pages/AdminPatientImportsPage.tsx")
    api = _read("frontend/src/api.ts")
    assert "Patient import" in workspace
    assert "external_patient_id,name" in page
    assert "Preview import" in page
    assert "Download report" in page
    assert "Conflicts are reported and never overwrite" in page
    assert "/api/admin/patient-imports/preview" in api
    assert "/commit" in api
    assert "createInvite" not in page
