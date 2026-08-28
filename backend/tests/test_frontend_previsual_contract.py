"""Static regression gates for the pre-visual frontend acceptance repairs."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_product_shell_uses_full_height_and_demo_mode_owns_toolbar_offset():
    css = _read("frontend/src/index.css")
    assert ".product-root { min-height: 100vh; }" in css
    assert ".demo-toolbar + .product-root { min-height: calc(100vh - 36px); }" in css
    assert "height: 100vh; min-height: 680px" in css
    assert ".demo-toolbar + .product-root .clinician-shell" in css


def test_focus_and_small_text_tokens_are_visible():
    css = _read("frontend/src/index.css")
    assert "summary:focus-visible" in css
    assert "[role='separator']:focus-visible" in css
    assert "outline: 3px solid #0f6f57" in css
    assert ".clinician-sidebar button:focus-visible" in css
    assert "rgba(30, 106, 87, 0.28)" not in css
    assert ".artifact-authority { max-width: 180px; color: #52645e; font-size: 11px" in css
    assert ".lifecycle-list small { color: #52645e; font-size: 10px; }" in css
    assert ".patient-latest-event { margin-top: 2px; color: #52645e" in css


def test_medium_clinical_layout_protects_the_reader():
    css = _read("frontend/src/index.css")
    assert "@media (max-width: 1199px) and (min-width: 901px)" in css
    assert "grid-template-columns: minmax(0, 1fr) minmax(260px, 280px)" in css
    assert ".event-detail-columns, .notes-grid { grid-template-columns: 1fr; }" in css
    assert ".workspace-area > .panel-resizer { display: none; }" in css


def test_patient_mobile_actions_have_minimum_touch_height():
    css = _read("frontend/src/index.css")
    assert ".patient-navigation button" in css and "min-height: 44px" in css
    assert ".patient-logout" in css and "min-height: 44px" in css
    assert ".patient-task-actions button" in css and "min-height: 44px" in css
