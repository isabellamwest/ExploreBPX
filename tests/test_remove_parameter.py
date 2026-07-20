"""Tests for the remove-parameter feature: a parameter row right-click
context menu ("Remove parameter") and its Delete-key accelerator, completing
the add/remove pair on top of the already-tested RemoveParameter command
(see test_command_service.py C1 section for the command/undo contract
itself).

Creation stays confined to the "+ Add parameter" header (test_add_parameter.py);
this file covers only the row-scoped removal action -- context menu wiring in
isolation, and the full command-execution/undo seam end-to-end via AppDriver,
the same seam _on_add_parameter_requested uses.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QPoint, QTimer
from PySide6.QtWidgets import QApplication

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from ui_qt.parameter_list import ParameterListPanel

_CELL = ("Parameterisation", "Cell")


def _section_node(label: str = "Cell", path=_CELL, parameters=None) -> TreeNode:
    return TreeNode(label=label, path=path, parameters=list(parameters or []))


def _parameter(label: str, path=_CELL) -> ParameterItem:
    return ParameterItem(label=label, path=path + (label,), kind=ParameterKind.SCALAR)


# ---------------------------------------------------------------------------
# ParameterListPanel: context menu + Delete-key wiring
# ---------------------------------------------------------------------------


@pytest.fixture
def panel(qtbot) -> ParameterListPanel:
    p = ParameterListPanel()
    qtbot.addWidget(p)
    qtbot.addWidget(p._popup)
    return p


def _capture_and_close_open_popup(captured: dict) -> None:
    """Grab the currently open native popup's actions, then close it.

    ``QMenu.exec()`` runs a genuinely blocking native modal loop -- a
    Python-level monkeypatch of ``exec`` does not intercept the underlying
    C++ call, so it cannot be swapped out like ``QFileDialog.getOpenFileName``
    elsewhere in this suite. Scheduling this as a zero-delay timer closes the
    menu the instant its event loop starts, letting ``exec()`` return
    immediately -- the standard Qt-test idiom for driving a blocking popup
    without a real user dismissing it.
    """
    popup = QApplication.instance().activePopupWidget()
    if popup is not None:
        captured["actions"] = popup.actions()
        popup.close()


def test_right_click_on_row_selects_it_and_offers_remove(panel):
    # A real schema alias, not a made-up name -- under the schema-consulting
    # can_rename_parameter/can_duplicate_parameter, a made-up name here would
    # wrongly read as a custom (schema-undefined) parameter and offer
    # Rename…/Duplicate too.
    panel.show_node(
        _section_node(parameters=[_parameter("Alpha"), _parameter("Reference temperature [K]")])
    )

    item = panel._list.item(1)
    pos = panel._list.visualItemRect(item).center()
    captured: dict = {}
    QTimer.singleShot(0, lambda: _capture_and_close_open_popup(captured))
    panel._on_context_menu_requested(pos)

    assert panel._list.currentItem() is item  # right-click selects what it clicked
    actions = captured.get("actions")
    assert actions is not None, "No context menu was shown"
    # A schema-fixed row (not user-owned) offers no Rename…/Duplicate; Move
    # up/down are always offered, and this is the last of two rows. A
    # separator precedes "Remove parameter" -- excluded here, its own text
    # is empty and carries no assertion value.
    real_actions = [a for a in actions if not a.isSeparator()]
    assert [a.text() for a in real_actions] == ["Move up", "Move down", "Remove parameter"]
    move_up, move_down, remove = real_actions
    assert move_up.isEnabled() is True
    assert move_down.isEnabled() is False
    # The Remove action declares no shortcut: Delete is bound by the list
    # view's own keyPressEvent, so a QKeySequence here would be a redundant
    # second binding that Qt would also render as a "Del" hint beside the label.
    assert remove.shortcut().isEmpty()


def test_right_click_on_empty_space_shows_no_menu(panel):
    panel.show_node(_section_node())  # no rows -> nothing under any position

    # No row is under the cursor, so the handler returns before ever
    # constructing a menu -- nothing here can block on a native event loop.
    panel._on_context_menu_requested(QPoint(5, 5))

    assert QApplication.instance().activePopupWidget() is None


def test_right_click_with_no_document_shows_no_menu(panel):
    panel.show_node(None)

    panel._on_context_menu_requested(QPoint(5, 5))

    assert QApplication.instance().activePopupWidget() is None


def test_remove_action_emits_current_row_path(panel, qtbot):
    panel.show_node(_section_node(parameters=[_parameter("Alpha")]))
    panel._list.setCurrentRow(0)
    with qtbot.waitSignal(panel.remove_parameter_requested) as blocker:
        panel._remove_action.trigger()
    assert blocker.args[0] == _CELL + ("Alpha",)


def test_delete_key_triggers_removal_of_current_row(panel, qtbot):
    panel.show_node(_section_node(parameters=[_parameter("Alpha")]))
    panel._list.setCurrentRow(0)
    with qtbot.waitSignal(panel.remove_parameter_requested) as blocker:
        qtbot.keyClick(panel._list, Qt.Key_Delete)
    assert blocker.args[0] == _CELL + ("Alpha",)


def test_delete_key_with_no_current_row_is_a_noop(panel, qtbot):
    panel.show_node(_section_node())
    with qtbot.assertNotEmitted(panel.remove_parameter_requested):
        qtbot.keyClick(panel._list, Qt.Key_Delete)


# ---------------------------------------------------------------------------
# End-to-end: context menu / Delete key -> RemoveParameter command, via AppDriver
# ---------------------------------------------------------------------------


def _row_index(labels, prefix):
    return next(i for i, label in enumerate(labels) if label.startswith(prefix))


def test_remove_via_context_menu_updates_raw_dict_and_list_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    index = _row_index(d.parameter_labels(), "Reference temperature")

    d.right_click_parameter_row(index)
    d.activate_remove_parameter_action()

    assert not any(label.startswith("Reference temperature") for label in d.parameter_labels())
    session = d._w._state.active
    assert "Reference temperature [K]" not in session.document.raw["Parameterisation"]["Cell"]


def test_delete_key_removes_selected_parameter_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    index = _row_index(d.parameter_labels(), "Reference temperature")
    d._w._params._list.setCurrentRow(index)

    d.press_delete_in_parameter_list()

    assert not any(label.startswith("Reference temperature") for label in d.parameter_labels())


def test_remove_via_context_menu_is_undoable_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    index = _row_index(d.parameter_labels(), "Reference temperature")

    d.right_click_parameter_row(index)
    d.activate_remove_parameter_action()
    assert not any(label.startswith("Reference temperature") for label in d.parameter_labels())

    d.undo()
    assert any(label.startswith("Reference temperature") for label in d.parameter_labels())


def test_removing_the_inspected_parameter_clears_dangling_selection_end_to_end(
    app_driver, spm_workfile
):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    index = _row_index(d.parameter_labels(), "Reference temperature")
    d.select_parameter(_CELL + ("Reference temperature [K]",))
    assert d.inspector_title() == "Reference temperature [K]"

    d.right_click_parameter_row(index)
    d.activate_remove_parameter_action()

    assert d.showing_placeholder() is True


def test_remove_custom_parameter_end_to_end(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    d.open_add_parameter_popup()
    d.type_new_parameter_alias("My custom parameter")
    d.activate_selected_add_parameter_row()  # expands the inline form
    d.submit_custom_parameter_form()  # Scalar is the default type
    assert any("My custom parameter" in label for label in d.parameter_labels())

    index = _row_index(d.parameter_labels(), "My custom parameter")
    d.right_click_parameter_row(index)
    d.activate_remove_parameter_action()

    assert not any("My custom parameter" in label for label in d.parameter_labels())
    session = d._w._state.active
    assert "My custom parameter" not in session.document.raw["Parameterisation"]["Cell"]


def test_removing_a_required_parameter_produces_a_validation_error_end_to_end(
    app_driver, spm_workfile
):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(_CELL)
    index = _row_index(d.parameter_labels(), "Electrode area")
    errors_before = d._w._state.active.document.error_count

    d.right_click_parameter_row(index)
    d.activate_remove_parameter_action()

    errors_after = d._w._state.active.document.error_count
    assert errors_after > errors_before


def test_add_parameter_button_still_disabled_with_no_document(app_driver):
    assert app_driver.add_parameter_button_enabled() is False
