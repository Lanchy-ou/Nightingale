from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_patient_checkin_frontend_preserves_identity_cleanup_and_message_retry_id():
    source = _read("frontend/src/components/PatientCheckIn.tsx")
    assert "releasePatientCheckInRequest(requestRef.current)" in source
    assert "controller.abort" not in source  # cleanup stays centralized and testable
    assert "}, [patientId, roleKey, load]);" in source
    assert "const message = pending ??" in source
    assert "savePatientCheckInMessage" in source
    assert "processPatientCheckInMessage" in source
    assert "Retry the same saved message" in source
    assert "boundaryGenerationRef" in source
    assert "requestIsCurrent" in source
    assert "actionInFlightRef" in source


def test_patient_and_ai_bubbles_confirmation_and_safety_are_explicit():
    source = _read("frontend/src/components/PatientCheckIn.tsx")
    for label in (
        "Patient",
        "Nightingale AI",
        "Saving your original words safely",
        "Your words are saved",
        "What you just told us",
        "Go back to add or correct",
        "Confirm and submit",
        "Get urgent help now",
        "current.safety_message",
    ):
        assert label in source


def test_clinical_reader_separates_patient_ai_summary_and_exact_sources():
    source = _read("frontend/src/components/ArtifactContent.tsx")
    assert "Patient original messages" in source
    assert "Nightingale AI questions and acknowledgements" in source
    assert "Exact patient sources" in source
    assert "messageOffset" in source
