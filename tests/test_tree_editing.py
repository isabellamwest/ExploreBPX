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


def test_popup_shows_and_clears_the_note(qtbot):
    """``open_at``'s optional ``note`` shows a plain informational line for
    the whole time the popup is open, and a later call without one clears it
    (rather than leaving a stale note from a previous rename)."""
    popup = NamePopup()
    qtbot.addWidget(popup)
    popup.open_at(QPoint(0, 0), "New name…", note="A note.")
    assert popup._note.isVisible()
    assert popup._note.text() == "A note."

    popup.open_at(QPoint(0, 0), "New name…")
    assert not popup._note.isVisible()


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


def test_particle_material_rename_popup_shows_the_reference_note(qtbot, blended_validation_tree):
    """A Particle material's old name is never rewritten in a per-material
    reference elsewhere (RenameKey's own docstring); the rename popup notes
    this so the user isn't surprised by the validator flagging it later."""
    panel = _panel_with(qtbot, blended_validation_tree)
    node = _find(
        blended_validation_tree,
        ("Parameterisation", "Positive electrode", "Particle", "Primary"),
    )
    panel._open_rename(node)
    assert (
        panel._popup._note.text()
        == "State-section references are not updated; validation will flag mismatches."
    )
    assert panel._popup._note.isVisible()
    panel._popup.hide()


def test_validation_run_rename_popup_shows_no_note(qtbot, blended_validation_tree):
    """A Validation run's name is never referenced elsewhere, so no note."""
    panel = _panel_with(qtbot, blended_validation_tree)
    node = _find(blended_validation_tree, ("Validation", "C/20 discharge"))
    panel._open_rename(node)
    assert not panel._popup._note.isVisible()
    panel._popup.hide()


def test_user_defined_rename_popup_shows_no_note(qtbot, user_defined_tree):
    """User-defined content is never referenced elsewhere, so no note."""
    panel = _panel_with(qtbot, user_defined_tree)
    node = _find(user_defined_tree, _USER_DEFINED + ("Thermal tweaks",))
    panel._open_rename(node)
    assert not panel._popup._note.isVisible()
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


# ----------------------------------------------------------------------
# User-defined authoring: the one open bucket names both sections and
# parameters freely, and its content is renamable
# ----------------------------------------------------------------------

_USER_DEFINED = ("Parameterisation", "User-defined")


@pytest.fixture
def user_defined_tree(valid_spm_dict):
    """An SPM tree whose Parameterisation carries a populated User-defined
    bucket: one custom subsection (holding a nested value) and one loose
    parameter, so every free-form menu flavour has a live target."""
    doc = dict(valid_spm_dict)
    doc["Parameterisation"] = dict(doc["Parameterisation"])
    doc["Parameterisation"]["User-defined"] = {
        "Thermal tweaks": {"h": 25},
        "loose scalar": 1.5,
    }
    return BPXDocument.from_raw(doc, "x.json", "json").tree


def test_user_defined_bucket_offers_add_subsection(qtbot, user_defined_tree):
    """The bucket names subsections but keeps its own schema name: add a
    subsection, no rename, and "Remove section" (not the user-named "Remove").
    Free-form parameters are added via the parameter list, not this menu."""
    panel = _panel_with(qtbot, user_defined_tree)
    _menu, labels = _menu_labels(panel, user_defined_tree, _USER_DEFINED)
    assert labels == ["Add subsection…", "Remove section"]


def test_user_defined_subsection_offers_authoring_menu(qtbot, user_defined_tree):
    """A user-authored subsection nests further and is itself renamable, so it
    reads the user-named "Remove"."""
    panel = _panel_with(qtbot, user_defined_tree)
    _menu, labels = _menu_labels(panel, user_defined_tree, _USER_DEFINED + ("Thermal tweaks",))
    assert labels == ["Add subsection…", "Rename…", "Remove"]


def test_add_subsection_routes_through_add_section_request(qtbot, user_defined_tree):
    """"Add subsection…" is an ordinary AddSection under the bucket."""
    panel = _panel_with(qtbot, user_defined_tree)
    fired = []
    panel.add_section_requested.connect(lambda path, key: fired.append((path, key)))
    menu, _ = _menu_labels(panel, user_defined_tree, _USER_DEFINED)
    next(a for a in menu.actions() if a.text() == "Add subsection…").trigger()
    assert "Thermal tweaks" in panel._popup._taken  # popup opened over the bucket
    panel._popup._input.setText("Ageing model")
    panel._popup._input.confirm_requested.emit()
    assert fired == [(_USER_DEFINED, "Ageing model")]
    panel._popup.hide()


def test_add_parameter_is_not_offered_on_the_tree_menu(qtbot, user_defined_tree):
    """Adding a free-form parameter lives on the parameter list's
    "+ Add parameter", never the tree context menu."""
    panel = _panel_with(qtbot, user_defined_tree)
    _menu, labels = _menu_labels(panel, user_defined_tree, _USER_DEFINED)
    assert "Add parameter…" not in labels
    assert not hasattr(panel, "add_parameter_requested")


@pytest.fixture
def window_with_user_defined(main_window, tmp_path, valid_spm_dict):
    doc = dict(valid_spm_dict)
    doc["Parameterisation"] = dict(doc["Parameterisation"])
    doc["Parameterisation"]["User-defined"] = {}
    work = tmp_path / "user_defined.json"
    work.write_text(json.dumps(doc), encoding="utf-8")
    main_window.open_document(work)
    return main_window


def test_multiple_subsections_land_in_one_bucket(window_with_user_defined):
    """The old "only one user-defined section" limit is gone: the bucket holds
    as many named subsections as the user adds."""
    window = window_with_user_defined
    window._on_add_section_requested(_USER_DEFINED, "Thermal tweaks")
    window._on_add_section_requested(_USER_DEFINED, "Ageing model")
    bucket = window._state.active.document.raw["Parameterisation"]["User-defined"]
    assert bucket == {"Thermal tweaks": {}, "Ageing model": {}}


def test_add_parameter_into_user_defined_seeds_empty_value(window_with_user_defined):
    """A free-form parameter still lands in the bucket -- added through the
    parameter list's "+ Add parameter" handler (a typed custom name), the one
    surface for parameters now that the tree menu only adds subsections."""
    window = window_with_user_defined
    window._on_add_parameter_requested(_USER_DEFINED, "capacity offset", None)
    bucket = window._state.active.document.raw["Parameterisation"]["User-defined"]
    assert bucket == {"capacity offset": None}


def test_rename_a_user_defined_subsection_moves_it(window_with_user_defined):
    """Renaming user-authored content passes the backend can_rename guard that
    refuses schema property names."""
    window = window_with_user_defined
    window._on_add_section_requested(_USER_DEFINED, "Thermal tweaks")
    window._on_rename_requested(_USER_DEFINED + ("Thermal tweaks",), "Thermal")
    bucket = window._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Thermal" in bucket and "Thermal tweaks" not in bucket
