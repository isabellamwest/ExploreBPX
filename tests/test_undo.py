"""Undo and redo: value edits are undoable/redoable, both reachable from the
toolbar.

These tests guard against two defects:

  - ``DocumentSession.apply_value`` rebuilt the document without recording
    history, so a committed value edit -- the single most common mutation in
    the app -- could not be undone at all, despite add/remove being undoable.
  - Undo existed only as a ``DocumentSession`` method with no affordance.

Undo has two surfaces with deliberately different behaviour:

  - the **toolbar button** is a document command, like Save and Export beside
    it, and a toolbar button takes no focus;
  - **Ctrl+Z** is focus-aware, because a window-level shortcut is matched
    before the focused widget sees the key and would otherwise steal undo from
    every text field, the search box included.

Tests drive the real action and the real ``QShortcut`` rather than synthesising
a ``Ctrl+Z`` key event: ``QTest`` delivers key events straight to the target
widget and never consults the shortcut map, so a key press would exercise
nothing.

Redo is the symmetric stack, added later to close the "no redo anywhere"
debt. It mirrors Undo's toolbar-button-vs-shortcut split exactly (see the
"Redo" section below), plus its own rule: a new command clears the redo
stack, since the redone-future of a reverted change is no longer reachable
once history branches.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtGui import QKeySequence

from core.commands import AddParameter, RemoveParameter, SetValue

_CELL = ("Parameterisation", "Cell")
_CAPACITY = _CELL + ("Nominal cell capacity [A.h]",)
_REFERENCE_TEMPERATURE = _CELL + ("Reference temperature [K]",)
_ELECTRODE_PAIRS = _CELL + (
    "Number of electrode pairs connected in parallel to make a cell",
)
_MODEL = ("Header", "Model")
_ORIGINAL_CAPACITY = 5


def _capacity(session) -> object:
    return session.document.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]


# ----------------------------------------------------------------------
# DocumentSession: a value edit is a command like any other
# ----------------------------------------------------------------------


def _session(valid_spm_path):
    from state.app_state import AppState

    state = AppState()
    state.open(valid_spm_path)
    return state.active


def test_apply_value_is_undoable(valid_spm_path):
    """The headline defect: apply_value must record undo history."""
    session = _session(valid_spm_path)
    assert _capacity(session) == _ORIGINAL_CAPACITY

    session.apply_value(_CAPACITY, 999.0)
    assert _capacity(session) == 999.0
    assert session.can_undo

    session.undo()
    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_apply_value_pushes_one_undo_entry_per_commit(valid_spm_path):
    session = _session(valid_spm_path)
    assert not session.can_undo

    session.apply_value(_CAPACITY, 1.0)
    session.apply_value(_CAPACITY, 2.0)
    session.apply_value(_CAPACITY, 3.0)

    assert _capacity(session) == 3.0
    session.undo()
    assert _capacity(session) == 2.0
    session.undo()
    assert _capacity(session) == 1.0
    session.undo()
    assert _capacity(session) == _ORIGINAL_CAPACITY
    assert not session.can_undo


def test_apply_value_selects_the_edited_parameter(valid_spm_path):
    """Rerouting through SetValue must preserve today's selection behaviour."""
    session = _session(valid_spm_path)
    session.apply_value(_CAPACITY, 7.0)

    assert session.selected_parameter_path == _CAPACITY
    assert session.selected_path == _CAPACITY[:-1]


def test_apply_value_without_document_still_raises():
    from state.document_session import DocumentSession

    with pytest.raises(ValueError):
        DocumentSession().apply_value(_CAPACITY, 1.0)


def test_apply_value_matches_set_value_command(valid_spm_path):
    """apply_value is exactly SetValue -- no second mutation path."""
    direct = _session(valid_spm_path)
    via_command = _session(valid_spm_path)

    direct.apply_value(_CAPACITY, 42.0)
    via_command.execute_command(SetValue(_CAPACITY, 42.0))

    assert direct.document.raw == via_command.document.raw
    assert direct.selected_parameter_path == via_command.selected_parameter_path


# ----------------------------------------------------------------------
# Toolbar action: presence, shortcut, enabled state
# ----------------------------------------------------------------------


def test_undo_action_carries_the_platform_undo_shortcut(app_driver):
    assert app_driver.undo_shortcut() == QKeySequence(QKeySequence.Undo).toString()


def test_undo_disabled_with_no_document(app_driver):
    assert app_driver.undo_enabled() is False


def test_undo_disabled_on_a_freshly_opened_document(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)
    assert app_driver.undo_enabled() is False


def test_undo_enabled_after_a_commit_and_disabled_once_the_stack_empties(
    app_driver, spm_workfile
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    assert app_driver.undo_enabled() is True

    app_driver.undo()
    assert app_driver.undo_enabled() is False


def test_undo_on_a_disabled_action_does_nothing(app_driver, valid_spm_path):
    """A disabled QAction ignores trigger(), as it ignores a click."""
    app_driver.open(valid_spm_path).go_to(_CAPACITY)
    app_driver.undo()

    assert app_driver.field_value() == _ORIGINAL_CAPACITY


# ----------------------------------------------------------------------
# Undo through the UI: the document reverts and selection survives
# ----------------------------------------------------------------------


def test_undo_reverts_a_committed_edit_and_keeps_the_card_open(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    assert app_driver.field_value() == 999.0

    app_driver.undo()

    assert app_driver.field_value() == _ORIGINAL_CAPACITY
    assert app_driver.showing_placeholder() is False
    assert main_window._state.active.selected_parameter_path == _CAPACITY


def test_undo_returns_to_the_parameter_it_changed(
    app_driver, spm_workfile, main_window
):
    """Undo must never revert an off-screen parameter without revealing it.

    The user commits an edit, navigates elsewhere, then undoes. Restoring the
    document alone would silently change a parameter they are not looking at.
    """
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.go_to(_REFERENCE_TEMPERATURE)
    assert app_driver.shown_parameter_path() == _REFERENCE_TEMPERATURE

    app_driver.undo()

    assert _capacity(main_window._state.active) == _ORIGINAL_CAPACITY
    assert app_driver.shown_parameter_path() == _CAPACITY
    assert app_driver.field_value() == _ORIGINAL_CAPACITY


def test_undo_of_an_added_parameter_returns_to_where_it_was_added(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).select_object(_CELL)
    session = main_window._state.active

    session.execute_command(AddParameter(_CELL, "Zzz custom [K]", None))
    main_window._refresh_all()
    assert session.selected_parameter_path == _CELL + ("Zzz custom [K]",)

    app_driver.undo()

    assert "Zzz custom [K]" not in session.document.raw["Parameterisation"]["Cell"]
    assert session.selected_path == _CELL
    assert session.selected_parameter_path is None
    assert app_driver.showing_placeholder() is True


def test_undo_of_a_removed_parameter_restores_and_reveals_it(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_REFERENCE_TEMPERATURE)
    session = main_window._state.active

    session.execute_command(RemoveParameter(_REFERENCE_TEMPERATURE))
    main_window._refresh_all()

    app_driver.undo()

    assert "Reference temperature [K]" in session.document.raw["Parameterisation"]["Cell"]
    assert app_driver.shown_parameter_path() == _REFERENCE_TEMPERATURE


def test_undo_restores_selection_for_each_step_of_a_multi_step_history(
    app_driver, spm_workfile, main_window
):
    """Each entry carries its own selection, not just the newest one."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.go_to(_REFERENCE_TEMPERATURE).edit_field(300.0).commit()
    app_driver.go_to(_CAPACITY)

    app_driver.undo()
    assert app_driver.shown_parameter_path() == _REFERENCE_TEMPERATURE

    app_driver.undo()
    assert app_driver.shown_parameter_path() == _CAPACITY
    assert _capacity(main_window._state.active) == _ORIGINAL_CAPACITY


# ----------------------------------------------------------------------
# Ctrl+Z is focus-aware; the toolbar button is not
# ----------------------------------------------------------------------


def test_ctrl_z_with_a_focused_editor_undoes_typing_not_the_document(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    # The committed card is rebuilt fresh; typing gives it its own history.
    app_driver.focus_field().type_in_field("123")
    assert app_driver.field_text() == "999.0123"

    app_driver.press_undo_shortcut()

    assert app_driver.field_text() == "999.0"
    assert _capacity(session) == 999.0
    assert app_driver.undo_enabled() is True


def test_ctrl_z_falls_through_to_the_document_once_typing_is_exhausted(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.focus_field().type_in_field("123")
    app_driver.press_undo_shortcut()  # consumes the widget's typing history
    assert _capacity(session) == 999.0

    app_driver.press_undo_shortcut()  # nothing left in the widget -> document

    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_ctrl_z_with_a_fresh_untyped_editor_focused_undoes_the_document(
    app_driver, spm_workfile, main_window
):
    """A freshly rebuilt card has no typing history, so Ctrl+Z reaches the document."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.focus_field()
    app_driver.press_undo_shortcut()

    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_ctrl_z_in_the_search_box_undoes_the_query_not_the_document(
    app_driver, spm_workfile, main_window
):
    """The shortcut intercepts Ctrl+Z from the search box, so it must hand it back."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.focus_search().type_in_search("capacity")
    assert app_driver.search_text() == "capacity"

    app_driver.press_undo_shortcut()

    assert app_driver.search_text() == ""
    assert _capacity(session) == 999.0


def test_the_undo_button_ignores_focus_and_undoes_the_document(
    app_driver, spm_workfile, main_window
):
    """A toolbar button takes no focus, so Undo must not edit the search box."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.focus_search().type_in_search("capacity")
    app_driver.undo()

    assert app_driver.search_text() == "capacity"
    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_the_undo_button_ignores_a_focused_card_editor(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.focus_field().type_in_field("123")
    app_driver.undo()

    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_ctrl_z_undoes_typing_even_with_an_empty_document_history(
    app_driver, valid_spm_path
):
    """The shortcut stays live when the Undo button is greyed out."""
    app_driver.open(valid_spm_path).go_to(_CAPACITY)
    assert app_driver.undo_enabled() is False

    app_driver.focus_field().type_in_field("7")
    assert app_driver.field_text() == "57"

    app_driver.press_undo_shortcut()

    assert app_driver.field_text() == "5"


# ----------------------------------------------------------------------
# Ctrl+Z must never step past an uncommitted draft into the document
# ----------------------------------------------------------------------
#
# A QSpinBox and a QComboBox are not QLineEdits and hold no undo history of
# their own, so an unguarded Ctrl+Z fell straight through to the document and
# reverted the *previous* commit -- silently, to a parameter off-screen. These
# are the regression tests for that.


def test_ctrl_z_on_a_spinbox_draft_does_not_touch_the_document(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.go_to(_ELECTRODE_PAIRS)
    original = app_driver.field_value()
    app_driver.focus_field().edit_field(original + 1)
    assert app_driver.card_is_dirty() is True

    app_driver.press_undo_shortcut()

    assert _capacity(session) == 999.0, "an unrelated commit was reverted"
    assert app_driver.shown_parameter_path() == _ELECTRODE_PAIRS
    assert app_driver.field_value() == original + 1, "the draft was discarded"
    assert app_driver.undo_enabled() is True


def test_ctrl_z_on_a_combobox_draft_does_not_touch_the_document(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.go_to(_MODEL).focus_field().edit_field("SPMe")
    assert app_driver.card_is_dirty() is True

    app_driver.press_undo_shortcut()

    assert _capacity(session) == 999.0, "an unrelated commit was reverted"
    assert app_driver.field_value() == "SPMe", "the draft was discarded"


def test_ctrl_z_on_a_clean_spinbox_still_undoes_the_document(
    app_driver, spm_workfile, main_window
):
    """The guard is the uncommitted draft, not the widget type."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.go_to(_ELECTRODE_PAIRS).focus_field()
    assert app_driver.card_is_dirty() is False

    app_driver.press_undo_shortcut()

    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_the_undo_button_still_reverts_the_document_past_a_draft(
    app_driver, spm_workfile, main_window
):
    """Only Ctrl+Z is guarded; the button is an explicit document command."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.go_to(_ELECTRODE_PAIRS)
    app_driver.focus_field().edit_field(app_driver.field_value() + 1)

    app_driver.undo()

    assert _capacity(session) == _ORIGINAL_CAPACITY
    assert app_driver.shown_parameter_path() == _CAPACITY


# ----------------------------------------------------------------------
# Redo
# ----------------------------------------------------------------------
#
# DocumentSession: the symmetric stack
# ----------------------------------------------------------------------


def test_redo_restores_a_value_undo_reverted(valid_spm_path):
    session = _session(valid_spm_path)
    session.apply_value(_CAPACITY, 999.0)
    session.undo()
    assert _capacity(session) == _ORIGINAL_CAPACITY
    assert session.can_redo

    session.redo()
    assert _capacity(session) == 999.0
    assert session.can_redo is False


def test_a_new_command_after_undo_clears_the_redo_stack(valid_spm_path):
    """Command A -> undo -> command B branches history: A's redone-future is
    no longer reachable."""
    session = _session(valid_spm_path)
    session.apply_value(_CAPACITY, 999.0)  # command A
    session.undo()
    assert session.can_redo

    session.apply_value(_REFERENCE_TEMPERATURE, 250.0)  # command B

    assert session.can_redo is False


def test_redo_stack_survives_multiple_undos(valid_spm_path):
    """A, B -> undo, undo -> redo, redo returns to the post-B state."""
    session = _session(valid_spm_path)
    session.apply_value(_CAPACITY, 111.0)  # A
    session.apply_value(_CAPACITY, 222.0)  # B

    session.undo()
    session.undo()
    assert _capacity(session) == _ORIGINAL_CAPACITY

    session.redo()
    assert _capacity(session) == 111.0
    session.redo()
    assert _capacity(session) == 222.0
    assert session.can_redo is False


def test_can_redo_is_false_on_a_fresh_session(valid_spm_path):
    session = _session(valid_spm_path)
    assert session.can_redo is False


def test_can_redo_is_false_with_no_document():
    from state.document_session import DocumentSession

    assert DocumentSession().can_redo is False


def test_redo_on_an_empty_stack_does_nothing(valid_spm_path):
    session = _session(valid_spm_path)
    session.redo()
    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_redo_restores_the_selection_of_the_redone_change(valid_spm_path):
    """Redo must land on the change it reapplied, even if the user navigated
    elsewhere before undoing it -- the same guarantee undo makes.

    Navigating away *before* undo (not after) is the ordering that actually
    exercises this guarantee: undo's own transition already carries the
    selection that was current when the command ran, so undoing right after
    the commit and navigating away only afterwards would pass even with the
    before/after selection drift this guards against.
    """
    session = _session(valid_spm_path)
    session.select_parameter(_CAPACITY)  # the user must select before editing
    session.apply_value(_CAPACITY, 999.0)
    session.select_parameter(_REFERENCE_TEMPERATURE)

    session.undo()
    assert session.selected_parameter_path == _CAPACITY

    session.redo()

    assert session.selected_parameter_path == _CAPACITY


# ----------------------------------------------------------------------
# Toolbar action: presence, shortcut, enabled state
# ----------------------------------------------------------------------


def test_redo_action_carries_the_platform_redo_shortcut(app_driver):
    assert app_driver.redo_shortcut() == QKeySequence(QKeySequence.Redo).toString()


def test_every_registered_shortcut_key_still_dispatches(spm_workfile):
    """Regression test for the dead Ctrl+Shift+Z: two ``WindowShortcut``s
    registered with the same key sequence make Qt emit
    ``activatedAmbiguously`` and fire *neither* handler's ``activated``, so
    the key goes silently dead.

    This bit even on Windows: ``QKeySequence.keyBindings(QKeySequence.Redo)``
    already includes Ctrl+Shift+Z there, and ``QShortcut(QKeySequence.Redo,
    ...)`` matches every one of its platform's standard-key bindings at
    dispatch time -- not just the single sequence its own ``.key()`` reports
    ("Ctrl+Y"). Registering a second, explicit "Ctrl+Shift+Z" ``QShortcut``
    alongside it therefore collided on every platform, not only macOS/X11.

    Comparing each shortcut's own ``.key()`` would not catch it (no shortcut
    reports "Ctrl+Shift+Z" as its own key once the fix aliases the alternate
    to the primary), so this has to drive real key presses. It runs in a
    subprocess because it cannot be done from inside the suite at all: under
    pytest-qt the window never activates offscreen -- ``isActiveWindow()``
    stays False, ``focusWidget()`` stays None, and ``qtbot.waitActive``
    returns anyway -- so ``QTest.keySequence`` matches nothing and an in-suite
    version of this test passes no matter what. See
    ``tests/shortcut_dispatch_probe.py``.
    """
    import json
    import subprocess
    import sys
    from pathlib import Path

    probe = Path(__file__).with_name("shortcut_dispatch_probe.py")
    result = subprocess.run(
        [sys.executable, str(probe), str(spm_workfile)],
        capture_output=True,
        text=True,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr

    # The probe prints one JSON line; bpx's pyparsing warnings share stdout.
    report = json.loads(
        next(line for line in result.stdout.splitlines() if line.startswith("{"))
    )

    # Without a genuinely active window nothing dispatches and every later
    # assertion would hold vacuously -- the exact failure this test replaced.
    assert report["active"] is True, "probe window never activated; result is void"
    assert report["keys"], "no shortcut keys were found to test"
    assert report["dead"] == [], (
        f"registered key(s) that fired no handler: {report['dead']} -- "
        f"claims: {report['claims']}"
    )


def test_redo_disabled_with_no_document(app_driver):
    assert app_driver.redo_enabled() is False


def test_redo_disabled_on_a_freshly_opened_document(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)
    assert app_driver.redo_enabled() is False


def test_redo_enabled_after_an_undo_and_disabled_once_the_stack_empties(
    app_driver, spm_workfile
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    assert app_driver.redo_enabled() is False

    app_driver.undo()
    assert app_driver.redo_enabled() is True

    app_driver.redo()
    assert app_driver.redo_enabled() is False


def test_redo_on_a_disabled_action_does_nothing(app_driver, valid_spm_path):
    """A disabled QAction ignores trigger(), as it ignores a click."""
    app_driver.open(valid_spm_path).go_to(_CAPACITY)
    app_driver.redo()

    assert app_driver.field_value() == _ORIGINAL_CAPACITY


# ----------------------------------------------------------------------
# Redo through the UI: the document reapplies and selection lands on it
# ----------------------------------------------------------------------


def test_redo_reapplies_an_undone_edit_and_keeps_the_card_open(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    assert app_driver.field_value() == _ORIGINAL_CAPACITY

    app_driver.redo()

    assert app_driver.field_value() == 999.0
    assert app_driver.showing_placeholder() is False
    assert main_window._state.active.selected_parameter_path == _CAPACITY


def test_redo_returns_to_the_parameter_it_reapplied(
    app_driver, spm_workfile, main_window
):
    """Redo must never reapply an off-screen change without revealing it.

    Navigating away *before* undo (not after) is the ordering that actually
    exercises this guarantee -- see the DocumentSession-level
    ``test_redo_restores_the_selection_of_the_redone_change`` for why.
    """
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.go_to(_REFERENCE_TEMPERATURE)

    app_driver.undo()
    assert app_driver.shown_parameter_path() == _CAPACITY

    app_driver.redo()

    assert _capacity(main_window._state.active) == 999.0
    assert app_driver.shown_parameter_path() == _CAPACITY
    assert app_driver.field_value() == 999.0


def test_a_new_commit_after_undo_disables_redo_through_the_ui(
    app_driver, spm_workfile
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    assert app_driver.redo_enabled() is True

    app_driver.go_to(_REFERENCE_TEMPERATURE).edit_field(300.0).commit()

    assert app_driver.redo_enabled() is False


# ----------------------------------------------------------------------
# Redo is focus-aware; the toolbar button is not
# ----------------------------------------------------------------------


def test_ctrl_y_with_a_focused_editor_redoes_typing_not_the_document(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    session = main_window._state.active

    app_driver.focus_field().type_in_field("123")
    app_driver.press_undo_shortcut()  # gives the widget its own redo history
    assert app_driver.field_text() == "999.0"

    app_driver.press_redo_shortcut()

    assert app_driver.field_text() == "999.0123"
    assert _capacity(session) == 999.0


def test_ctrl_shift_z_also_redoes_a_focused_editor(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()

    app_driver.focus_field().type_in_field("123")
    app_driver.press_undo_shortcut()
    assert app_driver.field_text() == "999.0"

    app_driver.press_redo_shortcut_alt()

    assert app_driver.field_text() == "999.0123"


def test_ctrl_y_in_the_search_box_redoes_the_query_not_the_document(
    app_driver, spm_workfile, main_window
):
    """The shortcut intercepts Ctrl+Y from the search box, so it must hand it back."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    session = main_window._state.active

    app_driver.focus_search().type_in_search("capacity")
    app_driver.press_undo_shortcut()  # search box: "capacity" -> ""
    assert app_driver.search_text() == ""

    app_driver.press_redo_shortcut()

    assert app_driver.search_text() == "capacity"
    assert _capacity(session) == _ORIGINAL_CAPACITY


def test_the_redo_button_ignores_focus_and_redoes_the_document(
    app_driver, spm_workfile, main_window
):
    """A toolbar button takes no focus, so Redo must not edit the search box."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    session = main_window._state.active

    app_driver.focus_search().type_in_search("capacity")
    app_driver.redo()

    assert app_driver.search_text() == "capacity"
    assert _capacity(session) == 999.0


def test_the_redo_button_ignores_a_focused_card_editor(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    session = main_window._state.active

    app_driver.focus_field().type_in_field("123")
    app_driver.redo()

    assert _capacity(session) == 999.0


# ----------------------------------------------------------------------
# Redo must never step past an uncommitted draft into the document
# ----------------------------------------------------------------------
#
# Mirrors the Ctrl+Z spinbox/combobox draft guard above: reapplying a commit
# while a card holds an uncommitted draft would silently alter a parameter
# the user is not looking at.


def test_ctrl_y_on_a_spinbox_draft_does_not_touch_the_document(
    app_driver, spm_workfile, main_window
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    session = main_window._state.active

    app_driver.go_to(_ELECTRODE_PAIRS)
    original = app_driver.field_value()
    app_driver.focus_field().edit_field(original + 1)
    assert app_driver.card_is_dirty() is True

    app_driver.press_redo_shortcut()

    assert _capacity(session) == _ORIGINAL_CAPACITY, "an unrelated undo was redone"
    assert app_driver.shown_parameter_path() == _ELECTRODE_PAIRS
    assert app_driver.field_value() == original + 1, "the draft was discarded"
    assert app_driver.redo_enabled() is True


def test_the_redo_button_still_reapplies_the_document_past_a_draft(
    app_driver, spm_workfile, main_window
):
    """Only Ctrl+Y is guarded; the button is an explicit document command."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(999.0).commit()
    app_driver.undo()
    session = main_window._state.active

    app_driver.go_to(_ELECTRODE_PAIRS)
    app_driver.focus_field().edit_field(app_driver.field_value() + 1)

    app_driver.redo()

    assert _capacity(session) == 999.0
    assert app_driver.shown_parameter_path() == _CAPACITY
