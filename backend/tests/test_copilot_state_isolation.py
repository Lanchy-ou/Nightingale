"""D4 frontend contract probes kept dependency-free with the backend suite."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_copilot_resets_on_patient_role_and_session_boundary():
    source = (ROOT / "frontend" / "src" / "components" / "CopilotPanel.tsx").read_text(encoding="utf-8")
    workspace = (ROOT / "frontend" / "src" / "pages" / "ClinicianWorkspacePage.tsx").read_text(encoding="utf-8")
    assert "}, [patientId, roleKey]);" in source
    assert "setResponse(null);" in source
    assert "}, [patientId, identity.role, identity.user_id]);" in workspace
    assert "setCopilotEvidence(null);" in workspace


def test_patient_view_never_imports_or_calls_copilot():
    source = (ROOT / "frontend" / "src" / "pages" / "PatientViewPage.tsx").read_text(encoding="utf-8")
    assert "Copilot" not in source
    assert "queryCopilot" not in source
