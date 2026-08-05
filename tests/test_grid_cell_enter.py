"""Enter inside a grid cell editor belongs to the cell, not to the document.

Qt's item delegate does not consume Return: it queues the cell's
commit-and-close and returns False, so the key travels on to the view --
where the card's event filter sits. That filter used to read it as the
grid-level "commit the draft" Enter, so confirming a single cell wrote the
whole half-finished table to the document (empty rows landing as ``null``),
and the queued cell write then arrived at a card that had already been
rebuilt, losing the character just typed.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

_DIFFUSIVITY = ("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]")


def _stored(window):
    return window._state.active.document.raw["Parameterisation"]["Negative electrode"][
        "Diffusivity [m2.s-1]"
    ]


@pytest.fixture
def two_row_draft(app_driver, spm_workfile):
    """A diffusivity table with row 0 filled and row 1 empty, all uncommitted."""
    d = app_driver
    d.open(spm_workfile).go_to(_DIFFUSIVITY)
    d.select_mode("InterpolatedTable")
    d.add_grid_row().add_grid_row()
    d.set_grid_cell(0, 0, "0.1").set_grid_cell(0, 1, "5e-14")
    return d


def test_cell_enter_does_not_reach_the_document(two_row_draft, main_window):
    d = two_row_draft
    before = _stored(main_window)

    d.open_grid_cell_editor(1, 0)
    d.press_in_cell_editor(Qt.Key_Return)

    assert _stored(main_window) == before, "a cell-level Enter committed the draft"
    assert main_window._state.active.dirty is False


def test_cell_enter_keeps_the_typed_value(two_row_draft):
    d = two_row_draft

    d.open_grid_cell_editor(1, 0)  # the driver types "1" to open the editor
    d.press_in_cell_editor(Qt.Key_Return)

    assert d.grid_values()[1][0] == 1, "the confirmed cell value was dropped"


def test_cell_enter_steps_down_a_row(two_row_draft):
    d = two_row_draft
    d.add_grid_row()

    d.open_grid_cell_editor(0, 0)
    d.press_in_cell_editor(Qt.Key_Return)

    assert d._grid().focus_widget().currentIndex().row() == 1


def test_grid_enter_with_no_editor_open_still_commits(two_row_draft, main_window):
    d = two_row_draft
    before = _stored(main_window)

    d.commit_grid()

    assert _stored(main_window) != before
    assert main_window._state.active.dirty is True


def test_save_flushes_a_still_open_cell_editors_typed_text(two_row_draft, main_window):
    """Save must not silently drop a cell edit that was never confirmed.

    Applying the pending draft on Save has to reach into an open cell editor
    the same way the grid's own Enter does (``_GridView.commit_active_editor``),
    or the typed character never leaves the editor widget at all.
    """
    d = two_row_draft
    d.open_grid_cell_editor(1, 0)  # types "1"; the editor stays open

    assert main_window._save() is True

    assert _stored(main_window)["x"][1] == 1
    assert main_window._inspector.has_pending_draft() is False
    assert main_window._state.active.dirty is False
