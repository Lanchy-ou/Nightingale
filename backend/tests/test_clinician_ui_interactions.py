"""Dependency-free probes for clinician workspace interaction affordances."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_glance_source_preempts_copilot_in_patient_context_rail():
    source = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    handler = source[source.index("function handleViewSource"):source.index("function handleOpenCopilotEvidence")]
    assert "setProvenance(next);" in handler
    assert "setContextTab('source');" in handler
    assert "{contextTab === 'source' && provenance && (" in source
    assert "{contextTab === 'copilot' && identity.role === 'clinician' && (" in source


def test_lifecycle_only_uses_buttons_for_selectable_artifacts():
    source = _read("frontend/src/components/ClinicalEventDetail.tsx")
    assert "disabled={!item.artifact}" not in source
    assert ">Event timeline</h3>" in source
    assert "lifecycle.map((item) =>" in source
    assert "return item.artifact ? (" in source
    assert '<div key={item.key} className={`lifecycle-item ${item.kind}`}>' in source
    assert "Task created" in source


def test_glance_review_controls_explain_their_effect():
    source = _read("frontend/src/components/GlancePanel.tsx")
    assert "reviewRole === 'staff' ? 'Acknowledge' : 'Confirm'" in source
    assert "reviewRole === 'staff' ? 'Keep visible' : 'Keep on top'" in source
    assert ">Hide from Overview</button>" in source
    assert "None of these actions creates or edits a clinical note" in source
    assert ">Clinical Overview</h2>" in source


def test_clinical_sidebars_are_bounded_and_user_resizable():
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    styles = _read("frontend/src/index.css")
    assert 'role="separator"' in workspace
    assert 'label="Resize patient navigation"' in workspace
    assert 'label="Resize clinical context"' in workspace
    assert "min={196} max={310}" in workspace
    assert "min={280} max={520}" in workspace
    assert "var(--sidebar-width, 216px)" in styles
    assert "var(--context-width, 320px)" in styles


def test_tasks_and_event_creation_forms_use_progressive_disclosure():
    tasks = _read("frontend/src/components/ClinicalTasksView.tsx")
    event = _read("frontend/src/components/ClinicalEventDetail.tsx")
    assert "const [showCreate, setShowCreate] = useState(false);" in tasks
    assert "{showCreate && <div className=\"task-create-card\">" in tasks
    assert "const [composerMode, setComposerMode]" in event
    assert "{composerMode === 'note'" in event
    assert "{composerMode === 'task'" in event


def test_staff_workspace_has_explicit_support_identity_and_no_copilot_default():
    sidebar = _read("frontend/src/components/ClinicianSidebar.tsx")
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    overview = _read("frontend/src/components/GlancePanel.tsx")
    assert "Clinical support workspace" in sidebar
    assert "Clinical support context" in workspace
    assert "Staff Notes · Tasks · collaboration" in workspace
    assert "identity.role === 'clinician' ? 'copilot' : 'source'" in workspace
    assert "Staff review never becomes clinician confirmation" in overview


def test_staff_task_verification_affordance_is_explicit():
    tasks = _read("frontend/src/components/ClinicalTasksView.tsx")
    assert "Clinic verification required" in tasks
    assert "task.status === 'reported_done'" in tasks
    assert ">Verify complete</button>" in tasks
