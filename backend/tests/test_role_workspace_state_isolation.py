"""E1 frontend contract checks for role workspaces and state boundaries."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_staff_uses_shared_clinical_shell_with_nurse_specific_actions():
    app = _read("frontend/src/App.tsx")
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    sidebar = _read("frontend/src/components/ClinicianSidebar.tsx")
    css = _read("frontend/src/index.css")

    assert "<ClinicianWorkspacePage roleKey={productKey} onLogout={logout} />" in app
    assert "New nurse consultation" in workspace
    assert 'consultKind="nurse"' in workspace
    assert "New consultation" in workspace
    assert "role-${identity.role}" in workspace
    assert "identity.professional_title" in sidebar
    assert ".clinician-shell.role-staff" in css


def test_nurse_preview_and_confirm_are_separate_from_doctor_authority():
    consult = _read("frontend/src/components/NewDoctorConsult.tsx")
    api = _read("frontend/src/api.ts")

    assert "normalizeNurseTranscript" in consult
    assert "createNurseConsult" in consult
    assert "speaker: segment.speaker_candidate as 'nurse' | 'patient'" in consult
    assert "/api/transcripts/nurse-normalize" in api
    assert "/nurse-consults" in api
    assert "Only this explicit selection groups Nurse and Doctor Events" in consult

    detail = _read("frontend/src/components/ClinicalEventDetail.tsx")
    assert "'nurse_consult_create'" in detail
    assert "role === 'staff' ? 'Staff Note' : 'Clinician Note'" in detail


def test_consult_state_is_cleared_across_patient_or_role_remount():
    app = _read("frontend/src/App.tsx")
    consult = _read("frontend/src/components/NewDoctorConsult.tsx")
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")

    assert "window.history.replaceState({}, '', nextPath);" in app
    assert "? '/clinical'" in app
    assert "next.role === 'admin' ? '/admin' : '/patient'" in app
    assert "function roleHomePath(role: string | null | undefined)" in app
    assert "function pathBelongsToRole(path: string, role: string | null | undefined)" in app
    assert "activateIdentity(next, true)" in app
    assert "setPath('/login');" in app
    assert "if (!identity || pathBelongsToRole(path, identity.role)) return;" in app
    assert "currentPath.startsWith('/register') || currentPath.startsWith('/setup')" in app
    assert "abortRef.current?.abort();" in consult
    assert "setText('');" in consult
    assert "setNormalization(null);" in consult
    assert "setEncounterId('');" in consult
    assert "[consultKind, patient.patient_id]" in consult
    assert "key={`${roleKey}:${route.patientId}`}" in workspace
    assert "setProvenance(null);" in workspace
    assert "setCompletion(null);" in workspace


def test_admin_routes_to_oversight_workspace_without_clinical_controls():
    app = _read("frontend/src/App.tsx")
    admin = _read("frontend/src/pages/AdminWorkspacePage.tsx")

    assert "<AdminWorkspacePage" in app
    assert "PatientPage" not in app
    assert "getAdminUsers" in admin
    assert "getAdminAccessAudit" in admin
    assert "revokeAdminUserSessions" in admin
    assert "window.confirm" in admin
    assert "createNote" not in admin
    assert "queryCopilot" not in admin
    assert "transitionTask" not in admin
    assert "New consultation" not in admin
    assert "New nurse consultation" not in admin
