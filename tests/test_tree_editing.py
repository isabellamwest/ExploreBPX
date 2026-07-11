"""Tree structure editing: context menu offers, the name popup's gate, and the
window's command wiring (add / rename / remove with confirm-when-populated).

Menus are built (not ``exec``'d) and inspected; the popup is driven through its
input; window handlers are called with a real session so the raw document is
the assertion target -- the same conventions as the remove-parameter and CSV
suites.
"""

from __future__ import annotations

import json
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import QPoint

from core.document import BPXDocument
from ui_qt.name_popup import NamePopup
from ui_qt.tree_panel import TreePanel


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


@pytest.fixture
def blended_validation_tree(valid_spm_dict):
    """A document tree with a blended electrode and a Validation run.

    The SPM fixture already blends the Positive electrode (Primary/Secondary);
    a run is added so every menu flavour has a live target.
    """
    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": {"Time [s]": [0, 100]}}
    return BPXDocument.from_raw(doc, "x.json", "json").tree


def _panel_with(qtbot, tree) -> TreePanel:
    panel = TreePanel()
    qtbot.addWidget(panel)  # owns teardown: the panel parents the name popup
    panel.set_root(tree)
    return panel


def _menu_labels(panel, tree, path):
    node = tree if path == () else _find(tree, path)
    menu = panel._build_menu(node)
    labels = []
    for action in menu.actions():
        labels.append(action.text())
    return menu, labels


def _find(tree, path):
    node = tree
    for depth in range(1, len(path) + 1):
        node = next(child for child in node.children if child.path == path[:depth])
    return node


# ----------------------------------------------------------------------
# Menu construction: only what is legal at the node, nothing disabled
# ----------------------------------------------------------------------


def test_validation_container_offers_add_experiment_and_remove_section(
    qtbot, blended_validation_tree
):
    panel = _panel_with(qtbot, blended_validation_tree)
    _menu, labels = _menu_labels(panel, blended_validation_tree, ("Validation",))
    assert labels == ["Add experiment…", "Remove section"]


def test_a_run_offers_rename_and_remove_only(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    _menu, labels = _menu_labels(
        panel, blended_validation_tree, ("Validation", "C/20 discharge")
    )
    assert labels == ["Rename…", "Remove"]  # user-named: "Remove", not "Remove section"


def test_particle_container_offers_add_material(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    path = ("Parameterisation", "Positive electrode", "Particle")
    _menu, labels = _menu_labels(panel, blended_validation_tree, path)
    assert "Add material…" in labels
    assert "Rename…" not in labels


def test_a_material_offers_rename(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    path = ("Parameterisation", "Positive electrode", "Particle", "Primary")
    _menu, labels = _menu_labels(panel, blended_validation_tree, path)
    assert "Rename…" in labels and "Remove" in labels


def test_root_offers_the_absent_optional_top_level_sections(qtbot, valid_spm_dict):
    """The SPM fixture has State but no Validation, so empty-space right-click
    (the invisible root) offers exactly Validation."""
    tree = BPXDocument.from_raw(dict(valid_spm_dict), "x.json", "json").tree
    panel = _panel_with(qtbot, tree)
    menu, labels = _menu_labels(panel, tree, ())
    assert labels == ["Add section"]
    submenu = menu.actions()[0].menu()
    assert [action.text() for action in submenu.actions()] == ["Validation"]


def test_state_offers_its_absent_schema_children(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    menu, labels = _menu_labels(panel, blended_validation_tree, ("State",))
    assert labels[0] == "Add section"
    submenu = menu.actions()[0].menu()
    offered = [action.text() for action in submenu.actions()]
    assert "Degradation" in offered  # absent from the fixture, schema-declared


def test_header_has_no_structural_actions(qtbot, blended_validation_tree):
    """Protected, schema-named, and with no container children: no menu."""
    panel = _panel_with(qtbot, blended_validation_tree)
    menu, labels = _menu_labels(panel, blended_validation_tree, ("Header",))
    assert labels == []
    assert menu.isEmpty()


def test_add_section_action_emits_the_request(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    fired = []
    panel.add_section_requested.connect(lambda path, key: fired.append((path, key)))
    menu, _ = _menu_labels(panel, blended_validation_tree, ("State",))
    submenu = menu.actions()[0].menu()
    next(a for a in submenu.actions() if a.text() == "Degradation").trigger()
    assert fired == [(("State",), "Degradation")]


def test_remove_action_emits_the_request(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    fired = []
    panel.remove_requested.connect(fired.append)
    menu, _ = _menu_labels(
        panel, blended_validation_tree, ("Validation", "C/20 discharge")
    )
    next(a for a in menu.actions() if a.text() == "Remove").trigger()
    assert fired == [("Validation", "C/20 discharge")]


# ----------------------------------------------------------------------
# NamePopup: refuse-and-explain, emit only a usable name
# ----------------------------------------------------------------------


def test_popup_emits_the_trimmed_name_and_hides(qtbot):
    popup = NamePopup()
    qtbot.addWidget(popup)
    chosen = []
    popup.name_chosen.connect(chosen.append)
    popup.open_at(QPoint(0, 0), "New experiment name…")
    popup._input.setText("  1C discharge  ")
    popup._input.confirm_requested.emit()
    assert chosen == ["1C discharge"]
    assert popup.isHidden()


def test_popup_blocks_a_taken_name_with_a_reason(qtbot):
    popup = NamePopup()
    qtbot.addWidget(popup)
    chosen = []
    popup.name_chosen.connect(chosen.append)
    popup.open_at(QPoint(0, 0), "New material name…", taken=frozenset({"Primary"}))
    popup._input.setText("Primary")
    assert popup._reason.isVisible()
    assert "already used" in popup._reason.text()
    popup._input.confirm_requested.emit()
    assert chosen == []
    assert not popup.isHidden()  # still open for correction


def test_popup_ignores_an_empty_confirm(qtbot):
    popup = NamePopup()
    qtbot.addWidget(popup)
    chosen = []
    popup.name_chosen.connect(chosen.append)
    popup.open_at(QPoint(0, 0), "New name…")
    popup._input.setText("   ")
    popup._input.confirm_requested.emit()
    assert chosen == []


def test_rename_flow_prefills_and_routes_through_one_intent(qtbot, blended_validation_tree):
    """Rename… seeds the popup with the current name (taken includes it), and
    the chosen name comes back as a rename request for the original path."""
    panel = _panel_with(qtbot, blended_validation_tree)
    fired = []
    panel.rename_requested.connect(lambda path, name: fired.append((path, name)))
    node = _find(blended_validation_tree, ("Validation", "C/20 discharge"))

    panel._open_rename(node)
    assert panel._popup._input.text() == "C/20 discharge"
    assert "C/20 discharge" in panel._popup._taken
    # The pre-filled current name is not an error, and confirming it
    # unchanged is a silent no-op, not a rename.
    assert not panel._popup._reason.isVisible()
    panel._popup._input.confirm_requested.emit()
    assert fired == []

    panel._popup._input.setText("C/10 discharge")
    panel._popup._input.confirm_requested.emit()
    assert fired == [(("Validation", "C/20 discharge"), "C/10 discharge")]
    panel._popup.hide()


def test_add_named_flow_takes_existing_children(qtbot, blended_validation_tree):
    panel = _panel_with(qtbot, blended_validation_tree)
    fired = []
    panel.add_section_requested.connect(lambda path, key: fired.append((path, key)))
    node = _find(blended_validation_tree, ("Validation",))

    panel._open_add_named(node, "experiment")
    assert "C/20 discharge" in panel._popup._taken

    panel._popup._input.setText("1C discharge")
    panel._popup._input.confirm_requested.emit()
    assert fired == [(("Validation",), "1C discharge")]
    panel._popup.hide()


# ----------------------------------------------------------------------
# Window wiring: commands hit the raw document; populated removal confirms
# ----------------------------------------------------------------------


@pytest.fixture
def window_with_validation(main_window, tmp_path, valid_spm_dict):
    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": {"Time [s]": [0, 100]}}
    work = tmp_path / "tree_editing.json"
    work.write_text(json.dumps(doc), encoding="utf-8")
    main_window.open_document(work)
    return main_window


def test_add_experiment_lands_in_the_document_and_navigates(window_with_validation):
    window = window_with_validation
    window._on_add_section_requested(("Validation",), "1C discharge")
    session = window._state.active
    assert session.document.raw["Validation"]["1C discharge"] == {}
    assert session.selected_path == ("Validation", "1C discharge")


def test_rename_moves_the_run_and_navigates_to_the_new_address(window_with_validation):
    window = window_with_validation
    window._on_rename_requested(("Validation", "C/20 discharge"), "C/10 discharge")
    session = window._state.active
    assert "C/10 discharge" in session.document.raw["Validation"]
    assert "C/20 discharge" not in session.document.raw["Validation"]
    assert session.selected_path == ("Validation", "C/10 discharge")


def test_removing_a_populated_run_asks_first_and_cancel_keeps_it(
    window_with_validation, monkeypatch
):
    window = window_with_validation
    asked = []
    monkeypatch.setattr(
        type(window),
        "_confirm_populated_removal",
        lambda self, label: asked.append(label) or False,
    )
    window._on_remove_section_requested(("Validation", "C/20 discharge"))
    assert asked == ["C/20 discharge"]
    assert "C/20 discharge" in window._state.active.document.raw["Validation"]


def test_removing_a_populated_run_confirmed_removes_and_undo_restores(
    window_with_validation, monkeypatch
):
    window = window_with_validation
    monkeypatch.setattr(
        type(window), "_confirm_populated_removal", lambda self, label: True
    )
    window._on_remove_section_requested(("Validation", "C/20 discharge"))
    session = window._state.active
    assert "C/20 discharge" not in session.document.raw["Validation"]
    session.undo()
    assert session.document.raw["Validation"]["C/20 discharge"] == {"Time [s]": [0, 100]}


def test_removing_an_empty_section_does_not_ask(window_with_validation, monkeypatch):
    window = window_with_validation
    window._on_add_section_requested(("Validation",), "empty run")

    def _boom(self, label):
        raise AssertionError("an empty section must remove without confirmation")

    monkeypatch.setattr(type(window), "_confirm_populated_removal", _boom)
    window._on_remove_section_requested(("Validation", "empty run"))
    assert "empty run" not in window._state.active.document.raw["Validation"]
