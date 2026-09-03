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


def test_patient_instruction_is_created_from_event_workflow_not_copilot():
    copilot = _read("frontend/src/components/CopilotPanel.tsx")
    composer = _read("frontend/src/components/PatientInstructionComposer.tsx")
    detail = _read("frontend/src/components/ClinicalEventDetail.tsx")
    assert "Copilot only reads the record" in copilot
    assert "Draft patient instruction" not in copilot
    assert "Add patient instruction" in detail
    assert "Save clinic draft" in composer
    assert "Nothing is patient-visible until a clinician publishes it" in composer
