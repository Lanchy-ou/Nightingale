from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_clinical_publication_controls_are_explicit_and_versioned():
    control = _read("frontend/src/components/InstructionPublicationControl.tsx")
    detail = _read("frontend/src/components/ClinicalEventDetail.tsx")
    api = _read("frontend/src/api.ts")
    for text in (
        "Draft · not visible to patient",
        "Publish to Patient portal",
        "Correct instruction",
        "Confirm withdrawal",
        "Lineage history",
        "No external message is sent",
    ):
        assert text in control
    assert "InstructionPublicationControl" in detail
    for route in ("/publish", "/correct", "/withdraw", "/publication-history"):
        assert route in api


def test_copilot_patient_instruction_saves_draft_not_fake_publication():
    copilot = _read("frontend/src/components/CopilotPanel.tsx")
    assert "saved as a clinic draft; publish separately" in copilot
    assert "Confirm and create draft" in copilot
    assert "patient visible if confirmed" not in copilot
