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


def test_model_popup_pick_switches_model_and_completes_structure(qtbot, spm_workfile):
    """The full model-switch gesture: open the Model dropdown, pick DFN. No
    Enter. The commit lands as one ChangeModel -- value plus the empty
    required sections -- and a single undo reverts all of it."""
    state, panel = _panel_on(qtbot, spm_workfile, _MODEL)
    session = state.active
    combo = panel._card._editor._combo

    combo.showPopup()
    index = combo.findText("DFN")
    combo.setCurrentIndex(index)
    combo.activated.emit(index)
    combo.hidePopup()  # a real pick closes the popup; leaving it open crashes teardown

    raw = session.document.raw
    assert raw["Header"]["Model"] == "DFN"
    assert raw["Parameterisation"]["Electrolyte"] == {}
    assert raw["Parameterisation"]["Separator"] == {}

    session.undo()
    raw = session.document.raw
    assert raw["Header"]["Model"] == "SPM"
    assert "Electrolyte" not in raw["Parameterisation"]


def test_expanding_a_grid_reclaims_the_secondary_workspace_space(
    qtbot, spm_with_validation_path
):
    """When a grid takes over the pane, the secondary workspace must collapse
    to its tab strip and *give its space back* -- not merely hide its content
    and leave a dead band (the splitter has to be resized, since lowering the
    max height alone does not make it redistribute)."""
    time_path = ("Validation", "C/20 discharge", "Time [s]")
    state, panel = _panel_on(qtbot, spm_with_validation_path, time_path)
    panel.resize(460, 720)
    panel.show()
    qtbot.waitExposed(panel)

    # Open the drawer so it holds a real slice of the splitter, then expand.
    panel._secondary.open("issues")
    qtbot.wait(1)
    assert panel._splitter.sizes()[1] > panel._secondary.tab_strip_height()

    panel._card._editor._grid._toggle_expanded()
    qtbot.wait(1)

    strip = panel._secondary.tab_strip_height()
    assert not panel._secondary.is_expanded
    assert panel._splitter.sizes()[1] <= strip  # space reclaimed, no dead band
    # Collapsing the grid restores the drawer to what the user last wanted.
    panel._card._editor._grid._toggle_expanded()
    qtbot.wait(1)
    assert panel._splitter.sizes()[1] > strip


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


def test_switching_content_leaves_no_ghost_placeholder(qtbot, spm_workfile):
    """``_clear_content`` must reparent old widgets out of the content pane
    immediately, not merely take them from the layout: ``deleteLater`` only
    reaps when the event loop unwinds, so a widget still parented to
    ``_content`` keeps painting a ghost over the live card. Regression for the
    tripled "Select an object..." placeholder stacked behind the card."""
    from PySide6.QtWidgets import QLabel

    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)

    # Placeholder -> card -> placeholder -> card: every switch must clear.
    panel.show_placeholder()
    panel.show_parameter(state.active.selected_parameter())
    panel.show_placeholder()

    stale = [
        label
        for label in panel._content.findChildren(QLabel)
        if "Select an object" in label.text()
    ]
    assert len(stale) == 1, f"expected one placeholder, found {len(stale)}"


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


# ---------------------------------------------------------------------------
# commit_blocked_reason: a draft with no representation is refused
#
# These stub the card's ``commit_blocked_reason`` rather than driving a real
# Raw JSON body, deliberately. ``RawJsonBody.value()`` falls back to its seed
# while the text is unparseable, so its blocked draft always *equals* the
# original and the ``is_dirty`` check alone would stop the commit -- the guard
# never gets to decide. Stubbing produces the state the guard actually exists
# for: blocked **and** different from the committed value. That is the state
# Phase 4c's MaterialMapBody reaches with duplicate map keys.
# ---------------------------------------------------------------------------


def test_a_blocked_draft_is_never_committed_even_when_dirty(qtbot, spm_workfile):
    """The commit gate, isolated. Without it a draft with no representation
    would be written to the document."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    session = state.active
    assert session.document.raw["Parameterisation"]["Cell"][_CAPACITY[-1]] == 5

    card = panel._card
    card._editor._edit.setText("999.0")          # a genuinely dirty draft
    assert card.is_dirty is True
    card.commit_blocked_reason = lambda: "Not valid JSON: stubbed"

    panel._on_commit()

    assert session.document.raw["Parameterisation"]["Cell"][_CAPACITY[-1]] == 5
    assert session.can_undo is False


def test_a_blocked_draft_holds_the_badge_instead_of_previewing_its_value(
    qtbot, spm_workfile
):
    """While a draft has no representation there is nothing to validate. The
    badge must hold, not report on a value the editor is not showing."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    card = panel._card
    panel._render_issues([], False)
    assert card._badge.text() == "Valid"

    card._editor._edit.setText("not-a-number")   # would preview as Invalid
    card.commit_blocked_reason = lambda: "Not valid JSON: stubbed"

    panel._validate_draft()

    assert card._badge.text() == "Valid"         # held, not re-validated
