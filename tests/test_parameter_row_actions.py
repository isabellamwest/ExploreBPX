"""Tests for the parameter-list row context menu's Rename.../Duplicate/Move
up/down actions -- row-scoped structural actions, alongside the
already-tested "Remove parameter" (see test_remove_parameter.py)
and the MoveParameter/DuplicateParameter command contract itself (see
test_command_service.py).

Menu construction is inspected directly via ParameterListPanel._build_row_menu
(no QMenu.exec()), the same "build, don't exec" convention
tests/test_tree_editing.py uses for the tree's own structure menu
(TreePanel._build_menu), avoiding QMenu.exec()'s blocking native modal loop
entirely. The end-to-end sections drive the real window through AppDriver.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from ui_qt.parameter_list import ParameterListPanel

_CELL = ("Parameterisation", "Cell")
_USER_DEFINED = ("Parameterisation", "User-defined")


def _section_node(path, parameters) -> TreeNode:
    return TreeNode(label=path[-1], path=path, parameters=list(parameters))


def _parameter(path, label) -> ParameterItem:
    return ParameterItem(label=label, path=path + (label,), kind=ParameterKind.SCALAR)


@pytest.fixture
def panel(qtbot) -> ParameterListPanel:
    p = ParameterListPanel()
    qtbot.addWidget(p)
    qtbot.addWidget(p._popup)
    return p


# ---------------------------------------------------------------------------
# Menu construction: gating by structure.can_rename/can_duplicate, and
# Move up/down disabled at the first/last real row
# ---------------------------------------------------------------------------


def test_schema_only_row_menu_is_move_and_remove(panel):
    # A real schema alias, not a made-up name -- under the schema-consulting
    # can_rename_parameter/can_duplicate_parameter, a made-up name here would
    # wrongly read as a custom (schema-undefined) parameter. See
    # test_card_rename.py, which uses the same alias as its schema-blocked
    # example.
    label = "Reference temperature [K]"
    panel.show_node(_section_node(_CELL, [_parameter(_CELL, label)]))
    menu = panel._build_row_menu(_CELL + (label,))
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Move up", "Move down", "Remove parameter"]


def test_custom_parameter_under_a_schema_section_offers_rename_and_duplicate(panel):
    """A schema-undefined parameter leaf offers Rename…/Duplicate even
    directly inside a schema section (Cell), not only inside User-defined --
    the fixed-alias row above ("Reference temperature [K]") stays
    Move/Remove-only for contrast."""
    node = _section_node(_CELL, [_parameter(_CELL, "myname [cm7]")])
    panel.show_node(node)
    menu = panel._build_row_menu(_CELL + ("myname [cm7]",))
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Rename…", "Duplicate", "Move up", "Move down", "Remove parameter"]


def test_user_defined_row_menu_offers_rename_and_duplicate(panel):
    node = _section_node(_USER_DEFINED, [_parameter(_USER_DEFINED, "Alpha"), _parameter(_USER_DEFINED, "Beta")])
    panel.show_node(node)
    menu = panel._build_row_menu(_USER_DEFINED + ("Alpha",))
    labels = [a.text() for a in menu.actions() if not a.isSeparator()]
    assert labels == ["Rename…", "Duplicate", "Move up", "Move down", "Remove parameter"]


def test_first_row_has_move_up_disabled(panel):
    node = _section_node(_USER_DEFINED, [_parameter(_USER_DEFINED, "Alpha"), _parameter(_USER_DEFINED, "Beta")])
    panel.show_node(node)
    menu = panel._build_row_menu(_USER_DEFINED + ("Alpha",))
    actions = {a.text(): a for a in menu.actions() if not a.isSeparator()}
    assert actions["Move up"].isEnabled() is False
    assert actions["Move down"].isEnabled() is True


def test_last_row_has_move_down_disabled(panel):
    node = _section_node(_USER_DEFINED, [_parameter(_USER_DEFINED, "Alpha"), _parameter(_USER_DEFINED, "Beta")])
    panel.show_node(node)
    menu = panel._build_row_menu(_USER_DEFINED + ("Beta",))
    actions = {a.text(): a for a in menu.actions() if not a.isSeparator()}
    assert actions["Move up"].isEnabled() is True
    assert actions["Move down"].isEnabled() is False


def test_middle_row_has_both_moves_enabled(panel):
    node = _section_node(
        _USER_DEFINED,
        [
            _parameter(_USER_DEFINED, "Alpha"),
            _parameter(_USER_DEFINED, "Beta"),
            _parameter(_USER_DEFINED, "Gamma"),
        ],
    )
    panel.show_node(node)
    menu = panel._build_row_menu(_USER_DEFINED + ("Beta",))
    actions = {a.text(): a for a in menu.actions() if not a.isSeparator()}
    assert actions["Move up"].isEnabled() is True
    assert actions["Move down"].isEnabled() is True


# ---------------------------------------------------------------------------
# Action wiring: each action emits the matching request signal
# ---------------------------------------------------------------------------


def test_rename_action_emits_rename_parameter_requested(panel):
    node = _section_node(_USER_DEFINED, [_parameter(_USER_DEFINED, "Alpha")])
    panel.show_node(node)
    fired = []
    panel.rename_parameter_requested.connect(fired.append)
    menu = panel._build_row_menu(_USER_DEFINED + ("Alpha",))
    next(a for a in menu.actions() if a.text() == "Rename…").trigger()
    assert fired == [_USER_DEFINED + ("Alpha",)]


def test_duplicate_action_emits_duplicate_parameter_requested(panel):
    node = _section_node(_USER_DEFINED, [_parameter(_USER_DEFINED, "Alpha")])
    panel.show_node(node)
    fired = []
    panel.duplicate_parameter_requested.connect(fired.append)
    menu = panel._build_row_menu(_USER_DEFINED + ("Alpha",))
    next(a for a in menu.actions() if a.text() == "Duplicate").trigger()
    assert fired == [_USER_DEFINED + ("Alpha",)]


def test_move_actions_emit_direction(panel):
    node = _section_node(_CELL, [_parameter(_CELL, "Alpha"), _parameter(_CELL, "Beta")])
    panel.show_node(node)
    fired = []
    panel.move_parameter_requested.connect(lambda path, direction: fired.append((path, direction)))
    menu = panel._build_row_menu(_CELL + ("Alpha",))
    next(a for a in menu.actions() if a.text() == "Move down").trigger()
    assert fired == [(_CELL + ("Alpha",), "down")]


# ---------------------------------------------------------------------------
# End-to-end: window wiring, real document, undo
# ---------------------------------------------------------------------------


@pytest.fixture
def user_defined_window(app_driver, spm_workfile):
    """A live window with a two-parameter User-defined bucket."""
    d = app_driver
    d.open(spm_workfile)
    window = d._w
    window._on_add_section_requested(("Parameterisation",), "User-defined")
    window._on_add_parameter_requested(_USER_DEFINED, "Foo [V]", 0.0)
    window._on_add_parameter_requested(_USER_DEFINED, "Bar [A]", 0.0)
    d.select_object(_USER_DEFINED)
    return d


def _row_index(labels, prefix):
    return next(i for i, label in enumerate(labels) if label.startswith(prefix))


def test_move_via_menu_reorders_and_survives_save_order_end_to_end(user_defined_window):
    d = user_defined_window
    session = d._w._state.active
    before = list(session.document.raw["Parameterisation"]["User-defined"])
    assert before == ["Foo [V]", "Bar [A]"]

    index = _row_index(d.parameter_labels(), "Foo")
    d.trigger_parameter_row_menu_action(index, "Move down")

    after = list(d._w._state.active.document.raw["Parameterisation"]["User-defined"])
    assert after == ["Bar [A]", "Foo [V]"]
    labels = d.parameter_labels()
    assert _row_index(labels, "Bar") < _row_index(labels, "Foo")


def test_move_via_menu_is_undoable_end_to_end(user_defined_window):
    d = user_defined_window
    index = _row_index(d.parameter_labels(), "Foo")
    d.trigger_parameter_row_menu_action(index, "Move down")
    assert list(d._w._state.active.document.raw["Parameterisation"]["User-defined"]) == [
        "Bar [A]",
        "Foo [V]",
    ]
    d.undo()
    assert list(d._w._state.active.document.raw["Parameterisation"]["User-defined"]) == [
        "Foo [V]",
        "Bar [A]",
    ]


def test_duplicate_selects_the_new_adjacent_row_end_to_end(user_defined_window):
    d = user_defined_window
    index = _row_index(d.parameter_labels(), "Foo")
    d.trigger_parameter_row_menu_action(index, "Duplicate")

    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert list(bucket) == ["Foo [V]", "Foo (2) [V]", "Bar [A]"]
    assert d.shown_parameter_path() == _USER_DEFINED + ("Foo (2) [V]",)
