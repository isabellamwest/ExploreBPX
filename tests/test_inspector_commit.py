"""Tests for InspectorPanel's commit-only-when-dirty guard and the live
Issues-tab count during preview (docs/03-features.md §4 "Input system" /
§5 "Issues tab").
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from state.app_state import AppState
from ui_qt.inspector import InspectorPanel

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
_MODEL = ("Header", "Model")


def _panel_on(qtbot, spm_workfile, path):
    state = AppState()
    state.open(spm_workfile)
    session = state.active
    session.select(path[:-1])
    session.select_parameter(path)

    panel = InspectorPanel(state)
    qtbot.addWidget(panel)
    panel.show_parameter(session.selected_parameter())
    return state, panel


_TITLE = ("Header", "Title")


@pytest.fixture()
def null_title_workfile(tmp_path, spm_workfile):
    """A document whose ``Header.Title`` is an explicit ``null``.

    ``null`` is invalid for Title (the validator wants a string), so this is
    exactly the sort of broken value the app exists to let a user inspect and
    repair -- without the act of inspecting it silently rewriting it.
    """
    raw = json.loads(spm_workfile.read_text())
    raw["Header"]["Title"] = None
    workfile = tmp_path / "null_title.json"
    workfile.write_text(json.dumps(raw))
    return workfile


def test_noop_enter_does_not_rewrite_a_stored_null_text_value(qtbot, null_title_workfile):
    """A TextCard renders a stored ``null`` as an empty box, so ``value()``
    reads back ``""``. Selecting the parameter and pressing Enter without
    typing must still leave the document untouched: an untouched card cannot
    express an intent to change anything.
    """
    state, panel = _panel_on(qtbot, null_title_workfile, _TITLE)
    session = state.active
    assert session.document.raw["Header"]["Title"] is None
    assert panel._card.value() == "", "the card reads back '' for a stored null"

    panel._on_commit()

    assert session.document.raw["Header"]["Title"] is None
    assert not session.dirty


def test_typing_into_a_null_text_value_does_commit(qtbot, null_title_workfile):
    """The guard must not block a real edit to that same null value."""
    state, panel = _panel_on(qtbot, null_title_workfile, _TITLE)
    panel._card._editor._edit.setPlainText("LGM50")

    panel._on_commit()

    assert state.active.document.raw["Header"]["Title"] == "LGM50"
    assert state.active.dirty


def test_escape_then_enter_does_not_commit(qtbot, spm_workfile):
    """Escape reverts the draft *and* the touched flag, so a following Enter
    is a no-op rather than re-committing the reverted value."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    session = state.active
    before = json.dumps(session.document.raw, sort_keys=True)

    panel._card._editor._edit.setText("999")
    assert panel._card.is_dirty
    panel._card._editor._reset_draft()
    assert not panel._card.is_dirty

    panel._on_commit()

    assert json.dumps(session.document.raw, sort_keys=True) == before
    assert not session.dirty


def test_retyping_the_same_value_is_not_dirty(qtbot, spm_workfile):
    """Touched, but the draft equals the original: nothing to commit."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    original = state.active.document.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]

    panel._card._editor._edit.setText(str(original))

    assert not panel._card.is_dirty


def test_noop_enter_does_not_mutate_document(qtbot, spm_workfile):
    """Pressing Enter without editing anything must not rewrite the stored
    value -- the exact case that would otherwise turn a stored null into ""
    or 0."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    session = state.active
    before = json.dumps(session.document.raw, sort_keys=True)
    assert not session.dirty

    panel._on_commit()

    assert json.dumps(session.document.raw, sort_keys=True) == before
    assert not session.dirty


def test_noop_enter_does_not_emit_committed(qtbot, spm_workfile):
    _, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    received = []
    panel.committed.connect(lambda: received.append(True))

    panel._on_commit()

    assert received == []


def test_real_edit_still_commits_and_emits(qtbot, spm_workfile):
    """The dirty guard must not block a genuine edit."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    session = state.active
    received = []
    panel.committed.connect(lambda: received.append(True))

    panel._card._editor._edit.setText("7.0")
    panel._on_commit()

    assert received == [True]
    assert session.document.find_parameter(_CAPACITY).value == 7.0


def test_issues_tab_count_updates_live_during_preview(qtbot, spm_workfile):
    """03-features §5: the Issues tab's count badge updates live while
    typing an invalid draft, not only on commit."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    assert panel._secondary._buttons["issues"].text() == "Issues"

    panel._card._editor._edit.setText("not-a-number")
    panel._validate_draft()  # bypass the debounce timer directly

    assert panel._secondary._buttons["issues"].text() != "Issues"


def test_issues_tab_count_restores_on_escape(qtbot, spm_workfile):
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)

    panel._card._editor._edit.setText("not-a-number")
    panel._validate_draft()
    assert panel._secondary._buttons["issues"].text() != "Issues"

    panel._on_reset()

    assert panel._secondary._buttons["issues"].text() == "Issues"
