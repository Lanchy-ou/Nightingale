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
    assert ">Hide from Glance</button>" in source
    assert "These controls do not teach future ranking" in source
    assert "remain Shadow-only" in source
    assert ">Glance</h2>" in source
    assert "function nextStepText" in source
    assert "function evidenceText" in source
    assert "Recommended action" in source
    assert "An exact ${kind} is preserved in the source record" in source
    assert "create a follow-up Task with an owner and due date" in source
    assert "Inspect the exact supporting span before recording a review decision" not in source


def test_clinical_sidebars_are_bounded_and_user_controllable():
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    sidebar = _read("frontend/src/components/ClinicianSidebar.tsx")
    styles = _read("frontend/src/index.css")
    assert 'role="separator"' in workspace
    assert 'label="Resize clinical context"' in workspace
    assert "min={280} max={520}" in workspace
    assert "sidebarCollapsed ? '64px' : '232px'" in workspace
    assert "SIDEBAR_COLLAPSED_KEY" in workspace
    assert "'Expand patient navigation' : 'Collapse patient navigation'" in sidebar
    assert "var(--sidebar-width, 232px)" in styles
    assert "var(--context-width, 320px)" in styles


def test_tasks_and_event_creation_forms_use_progressive_disclosure():
    tasks = _read("frontend/src/components/ClinicalTasksView.tsx")
    event = _read("frontend/src/components/ClinicalEventDetail.tsx")
    assert "const [showCreate, setShowCreate] = useState(false);" in tasks
    assert "{showCreate && <div className=\"task-create-card\">" in tasks
    assert "const [composerMode, setComposerMode]" in event
    assert "{composerMode === 'note'" in event
    assert "{composerMode === 'task'" in event
    assert "{composerMode === 'instruction'" in event


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
    assert "Patient reported done · clinic verification required" in tasks
    assert "task.status === 'reported_done'" in tasks
    assert "label: 'Verify completion'" in tasks


def test_event_comments_are_visible_and_last_task_menu_opens_upward():
    event = _read("frontend/src/components/ClinicalEventDetail.tsx")
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    styles = _read("frontend/src/index.css")
    assert 'onOpenComments: () => void;' in event
    assert 'onClick={onOpenComments}>Comments</button>' in event
    assert "setContextTab('comments');" in workspace
    assert "setContextDrawerOpen(true);" in workspace
    assert ".task-group-list > li:last-child .task-overflow-menu[open] > div" in styles
    assert "bottom: calc(100% + 5px)" in styles


def test_workspace_tabs_and_copilot_use_one_read_only_chat_composer():
    workspace = _read("frontend/src/pages/ClinicianWorkspacePage.tsx")
    copilot = _read("frontend/src/components/CopilotPanel.tsx")
    styles = _read("frontend/src/index.css")
    assert "workspace-tabs ${route.mode === 'event' ? 'with-event-detail' : ''}" in workspace
    assert "min-width: 72px; flex: 1 1 0" in styles
    assert "Copilot only reads the record" in copilot
    assert "Use Notes, Tasks, or Comments to record clinical work" in copilot
    assert "copilot-input-shell" in copilot
    assert "Draft patient instruction" not in copilot
    assert "copilot-chip-group" not in copilot
    assert ".copilot-input-toolbar { display: flex" in styles


def test_clinician_priority_review_defaults_to_an_owned_follow_up_task():
    tasks = _read("frontend/src/components/ClinicalTasksView.tsx")
    assert "Choose the next action" in tasks
    assert "Create Task and complete review" in tasks
    assert "Close review without follow-up" in tasks
    assert "Monitor / record · routine" not in tasks
    assert "setExpandedTaskId(followUp.task_id)" in tasks
