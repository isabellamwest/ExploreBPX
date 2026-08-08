"""Tests for InspectorPanel's commit-only-when-dirty guard and the live
Issues-tab count during preview (docs/architecture.md "Editing
Architecture" / "Inspector pane").
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

from core.bpx_gateway import CheckReach
from state.app_state import AppState
from state.document_session import ParameterPreview
from ui_qt.inspector import InspectorPanel
from ui_qt.style import not_checked_tooltip

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


def test_a_long_grid_takes_the_pages_leftover_height(qtbot, spm_with_validation_path):
    """A grid with more rows than its compact window shows takes the page's
    stretch, so it grows into the pane instead of scrolling eight rows at a
    time above a slab of white. A short one leaves the white tail alone, and
    either way the Issues/Documentation sections stay where they are."""
    time_path = ("Validation", "C/20 discharge", "Time [s]")
    state, panel = _panel_on(qtbot, spm_with_validation_path, time_path)
    panel.resize(460, 900)
    panel.show()
    qtbot.waitExposed(panel)

    grid = panel._card.growable_grid()
    # Three rows: nothing to grow into, so the page keeps its white tail.
    assert grid.wants_fill is False
    assert panel._content_layout.stretch(0) == 0
    assert panel._content_layout.stretch(panel._tail_index) == 1
    compact = grid._view.height()

    # A long array claims the leftover instead, and the sections stay put.
    grid.set_values([[float(i)] for i in range(200)])
    qtbot.wait(50)

    assert grid.wants_fill is True
    assert panel._content_layout.stretch(0) == 1
    assert panel._content_layout.stretch(panel._tail_index) == 0
    assert grid._view.height() > compact
    assert panel._docs_section.isVisibleTo(panel)


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


def test_issues_section_appears_live_during_preview(qtbot, spm_workfile):
    """The Issues section updates live while typing an invalid draft, not
    only on commit: it appears with the previewed issue's row and count."""
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    assert not panel._issues_section.isVisibleTo(panel)

    panel._card._editor._edit.setText("not-a-number")
    panel._validate_draft()  # bypass the debounce timer directly

    assert panel._issues_section.isVisibleTo(panel)
    assert panel._issues_count.text() != "0"
    assert panel._issues_view._list.count() > 0


def test_issues_section_restores_on_escape(qtbot, spm_workfile):
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)

    panel._card._editor._edit.setText("not-a-number")
    panel._validate_draft()
    assert panel._issues_section.isVisibleTo(panel)

    panel._on_reset()

    assert not panel._issues_section.isVisibleTo(panel)
    assert panel._issues_view._list.count() == 0


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
    panel._render_issues([], False, CheckReach.COMPLETE)
    assert card._badge.text() == "Valid"

    card._editor._edit.setText("not-a-number")   # would preview as Invalid
    card.commit_blocked_reason = lambda: "Not valid JSON: stubbed"

    panel._validate_draft()

    assert card._badge.text() == "Valid"         # held, not re-validated


def test_live_preview_not_checked_hover_names_the_previews_own_abort(
    qtbot, spm_workfile
):
    """The draft badge and its hover must describe the same validation run.

    A draft can change where bpx's staged run stops (most starkly, a value
    that kills the run outright: reach ``NOT_RUN``). The badge follows the
    preview's reach, so the "Not checked" hover must explain the *preview's*
    abort -- not the last committed run's, which here completed and would
    leave the badge unexplained (an empty hover).
    """
    state, panel = _panel_on(qtbot, spm_workfile, _CAPACITY)
    card = panel._card
    assert state.active.document.validation_reach is CheckReach.COMPLETE

    card._editor._edit.setText("999.0")          # representable draft
    state.active.preview_parameter = lambda path, value: ParameterPreview(
        issues=[], validation_reach=CheckReach.NOT_RUN
    )

    panel._validate_draft()

    assert card._badge.text() == "Not checked"
    assert card._badge.toolTip() == not_checked_tooltip(CheckReach.NOT_RUN)
    assert card._badge.toolTip() != ""


def test_empty_state_names_the_section_when_only_a_section_is_selected(qtbot, spm_workfile):
    """Selecting a section *is* selecting an object, so the generic prompt
    contradicted what the user had just done. The empty state names the
    section and asks for the one thing actually missing."""
    from PySide6.QtWidgets import QLabel

    state = AppState()
    state.open(spm_workfile)
    state.active.select(_CAPACITY[:-1])

    panel = InspectorPanel(state)
    qtbot.addWidget(panel)
    panel.show_placeholder()

    label = panel._content.findChild(QLabel, "InspectorPlaceholder")
    assert label.text() == "Select a parameter from Cell to inspect + edit it."


def test_empty_state_stays_generic_with_nothing_selected(qtbot, spm_workfile):
    from PySide6.QtWidgets import QLabel

    state = AppState()
    state.open(spm_workfile)

    panel = InspectorPanel(state)
    qtbot.addWidget(panel)
    panel.show_placeholder()

    label = panel._content.findChild(QLabel, "InspectorPlaceholder")
    assert label.text().startswith("Select an object")


def test_empty_state_never_asks_for_a_parameter_a_section_does_not_have(qtbot):
    """Every section of a freshly created document is empty, so "select a
    parameter from Cell" asked for something impossible. Point at the move
    that exists instead."""
    from PySide6.QtWidgets import QLabel

    state = AppState()
    state.new_document("DFN")
    state.active.select(("Parameterisation", "Cell"))

    panel = InspectorPanel(state)
    qtbot.addWidget(panel)
    panel.show_placeholder()

    label = panel._content.findChild(QLabel, "InspectorPlaceholder")
    assert label.text() == "Cell has no parameters yet. Add one from the list."
