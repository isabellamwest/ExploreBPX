"""``MultiColumnGrid``: N independently-lengthed, all-editable columns.

Phase 0 of the multi-column-editable grid: a pure widget-layer capability,
not yet wired into any card. Each column maps to one BPX array, so a length
mismatch between columns is the ordinary case -- never padded, truncated, or
equalised (see ``_MultiColumnGridModel``'s docstring in ``ui_qt.cards.grid``).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui_qt.cards.grid import MultiColumnGrid
from ui_qt.cards.paste_dialog import PastePreviewResult


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


# ----------------------------------------------------------------------
# Independent column lengths
# ----------------------------------------------------------------------


def test_columns_hold_independent_lengths_with_no_padding():
    grid = MultiColumnGrid(("Time [s]", "Current [A]"))
    grid.set_column_values(0, [0.0, 1.0])
    grid.set_column_values(1, [10.0, 11.0, 12.0, 13.0])

    assert grid.column_length(0) == 2
    assert grid.column_length(1) == 4
    assert grid.column_values(0) == [0.0, 1.0]  # never padded to match column 1
    assert grid.column_values(1) == [10.0, 11.0, 12.0, 13.0]
    assert grid._model.rowCount() == 4  # the longest column


def test_row_count_is_zero_for_two_empty_columns():
    grid = MultiColumnGrid(("x", "y"))
    assert grid._model.rowCount() == 0
    assert grid.column_length(0) == 0
    assert grid.column_length(1) == 0


# ----------------------------------------------------------------------
# No invented padding: cells beyond a column's own end
# ----------------------------------------------------------------------


def test_cell_one_past_the_end_is_blank_but_editable_append_position():
    grid = MultiColumnGrid(("Time [s]", "Current [A]"))
    grid.set_column_values(0, [0.0, 1.0])
    grid.set_column_values(1, [10.0, 11.0, 12.0, 13.0])
    model = grid._model

    append_cell = model.index(2, 0)  # column 0's own end (length 2)
    assert model.data(append_cell, Qt.DisplayRole) == ""
    assert model.flags(append_cell) & Qt.ItemIsEditable
    assert model.flags(append_cell) & Qt.ItemIsSelectable


def test_cell_further_beyond_the_end_is_a_pure_phantom_cell():
    grid = MultiColumnGrid(("Time [s]", "Current [A]"))
    grid.set_column_values(0, [0.0, 1.0])
    grid.set_column_values(1, [10.0, 11.0, 12.0, 13.0])
    model = grid._model

    deep_phantom = model.index(3, 0)  # two past column 0's own end
    assert model.data(deep_phantom, Qt.DisplayRole) == ""
    assert not model.flags(deep_phantom) & Qt.ItemIsEditable
    assert not model.flags(deep_phantom) & Qt.ItemIsSelectable
    assert model.setData(deep_phantom, "9.9", Qt.EditRole) is False
    assert grid.column_values(0) == [0.0, 1.0]  # never invented


def test_beyond_end_cells_read_visually_muted():
    """Consistent with how the grid marks non-values today (see
    _GridModel's context-column muting): a foreground role distinguishes
    a "no value here" cell from a real one."""
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0, 2.0])
    model = grid._model

    assert model.data(model.index(0, 0), Qt.ForegroundRole) is None  # a real value
    assert model.data(model.index(1, 0), Qt.ForegroundRole) is not None  # no value here


# ----------------------------------------------------------------------
# Append-at-end extends only that column
# ----------------------------------------------------------------------


def test_typing_at_the_append_cell_extends_only_that_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0, 2.0, 3.0])
    model = grid._model

    assert model.setData(model.index(1, 0), "2.0", Qt.EditRole) is True

    assert grid.column_values(0) == [1.0, 2.0]  # extended
    assert grid.column_values(1) == [1.0, 2.0, 3.0]  # untouched


def test_becoming_the_longest_column_is_not_reachable_by_typing():
    """``model.index()`` bounds-checks against the *current* rowCount, so a
    tied-for-longest column has no valid index one past its own end: there
    is no rendered row to type into yet. Growing past every sibling needs
    the "+" button (``insert_cell``), exactly like ``NumericGrid``'s sole
    editable column always has."""
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0])

    assert not grid._model.index(1, 0).isValid()


def test_append_fires_changed():
    """Column 1 is already longer than column 0's append position, so
    typing there catches column 0 up to it."""
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0, 2.0, 3.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid._model.setData(grid._model.index(1, 0), "2.0", Qt.EditRole)

    assert grid.column_values(0) == [1.0, 2.0]
    assert grid._model.rowCount() == 3  # unchanged: column 1 was already longer
    assert fired == [1]


def test_typing_nothing_at_the_append_cell_invents_no_row():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    assert grid._model.setData(grid._model.index(1, 0), "", Qt.EditRole) is False

    assert grid.column_values(0) == [1.0]
    assert fired == []


def test_seeding_via_set_column_values_does_not_emit_changed():
    grid = MultiColumnGrid(("x", "y"))
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.set_column_values(0, [1.0, 2.0])
    grid.set_column_values(1, [3.0, 4.0])

    assert fired == []


# ----------------------------------------------------------------------
# Per-column insert/remove
# ----------------------------------------------------------------------


def test_insert_cell_applies_only_to_the_focused_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0, 2.0, 3.0])
    grid.set_column_values(1, [10.0, 20.0, 30.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid._view.setCurrentIndex(grid._model.index(1, 0))  # row 1, column 0
    grid.insert_cell()

    assert grid.column_values(0) == [1.0, 2.0, None, 3.0]
    assert grid.column_values(1) == [10.0, 20.0, 30.0]  # untouched
    assert fired == [1]


def test_remove_cell_applies_only_to_the_focused_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0, 2.0, 3.0])
    grid.set_column_values(1, [10.0, 20.0, 30.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid._view.setCurrentIndex(grid._model.index(0, 1))  # row 0, column 1
    grid.remove_cell()

    assert grid.column_values(1) == [20.0, 30.0]
    assert grid.column_values(0) == [1.0, 2.0, 3.0]  # untouched
    assert fired == [1]


def test_insert_cell_with_no_selection_defaults_to_the_first_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0])
    assert not grid._view.currentIndex().isValid()

    grid.insert_cell()

    assert grid.column_values(0) == [1.0, None]
    assert grid.column_values(1) == [1.0]


def test_remove_cell_is_a_noop_on_an_empty_column():
    grid = MultiColumnGrid(("x", "y"))
    grid._view.setCurrentIndex(grid._model.index(0, 0))
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.remove_cell()  # column 0 is empty: nothing to remove

    assert grid.column_values(0) == []
    assert fired == []


def test_insert_cell_clamped_to_the_focused_column_own_length():
    """A current cell sitting past column 0's own end (in its "no value
    here" region) must never create a cell beyond that end."""
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0, 2.0, 3.0])

    grid._view.setCurrentIndex(grid._model.index(2, 0))  # column 0's deep phantom region
    grid.insert_cell()

    assert grid.column_values(0) == [1.0, None]  # landed at column 0's own end


# ----------------------------------------------------------------------
# rows()/set_rows() round trip -- per-column API
# ----------------------------------------------------------------------


def test_column_values_round_trips_ragged_data():
    grid = MultiColumnGrid(("a", "b", "c"))
    grid.set_column_values(0, [1, 2, 3])
    grid.set_column_values(1, [])
    grid.set_column_values(2, [4.5])

    assert grid.column_values(0) == [1, 2, 3]
    assert grid.column_values(1) == []
    assert grid.column_values(2) == [4.5]


def test_non_numeric_cells_survive_verbatim():
    """A mistyped cell keeps the raw string; the validator, not the grid,
    judges it."""
    grid = MultiColumnGrid(("a", "b"))
    grid.set_column_values(0, ["oops", 2])

    assert grid.column_values(0) == ["oops", 2]


# ----------------------------------------------------------------------
# Issue tinting
# ----------------------------------------------------------------------


def test_set_cell_issues_tints_only_the_blamed_cell():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0, 2.0])
    grid.set_column_values(1, [3.0, 4.0])

    grid.set_cell_issues({(1, 0): "bad value"})
    model = grid._model

    assert model.data(model.index(1, 0), Qt.BackgroundRole) is not None
    assert model.data(model.index(1, 0), Qt.ToolTipRole) == "bad value"
    assert model.data(model.index(0, 0), Qt.BackgroundRole) is None
    assert model.data(model.index(0, 1), Qt.BackgroundRole) is None


def test_set_cell_issues_clears_back_to_defaults():
    grid = MultiColumnGrid(("x",))
    grid.set_column_values(0, [1.0])
    grid.set_cell_issues({(0, 0): "bad"})
    assert grid._model.data(grid._model.index(0, 0), Qt.BackgroundRole) is not None

    grid.set_cell_issues({})

    assert grid._model.data(grid._model.index(0, 0), Qt.BackgroundRole) is None


def test_set_cell_issues_does_not_mark_the_card_touched():
    grid = MultiColumnGrid(("x",))
    grid.set_column_values(0, [1.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.set_cell_issues({(0, 0): "bad"})

    assert fired == []


def test_set_cell_issues_is_a_noop_when_unchanged():
    grid = MultiColumnGrid(("x",))
    grid.set_column_values(0, [1.0])
    grid.set_cell_issues({(0, 0): "bad"})

    seen = []
    grid._model.dataChanged.connect(lambda *args: seen.append(args))
    grid.set_cell_issues({(0, 0): "bad"})

    assert seen == []


# ----------------------------------------------------------------------
# Read-only flag
# ----------------------------------------------------------------------


def test_read_only_grid_has_no_add_remove_buttons():
    grid = MultiColumnGrid(("x", "y"), read_only=True)
    assert grid._add_button is None
    assert grid._remove_button is None


def test_read_only_grid_blocks_cell_edits():
    grid = MultiColumnGrid(("x", "y"), read_only=True)
    grid.set_column_values(0, [1.0, 2.0])
    model = grid._model

    assert not model.flags(model.index(0, 0)) & Qt.ItemIsEditable
    assert model.flags(model.index(0, 0)) & Qt.ItemIsSelectable
    assert model.setData(model.index(0, 0), "9.9", Qt.EditRole) is False
    assert grid.column_values(0) == [1.0, 2.0]


def test_read_only_grid_blocks_insert_and_remove():
    grid = MultiColumnGrid(("x", "y"), read_only=True)
    grid.set_column_values(0, [1.0, 2.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.insert_cell()
    grid.remove_cell()

    assert grid.column_values(0) == [1.0, 2.0]  # unchanged
    assert fired == []


def test_read_only_grid_can_still_be_seeded():
    """Read-only gates user edits, not programmatic display refresh."""
    grid = MultiColumnGrid(("x", "y"), read_only=True)

    grid.set_column_values(0, [1.0, 2.0, 3.0])

    assert grid.column_values(0) == [1.0, 2.0, 3.0]


# ----------------------------------------------------------------------
# focus_column: initial current-cell placement (ExperimentCard's D1a)
# ----------------------------------------------------------------------


def test_focus_column_lands_on_the_named_columns_first_cell():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [2.0])

    grid.focus_column(1)

    index = grid._view.currentIndex()
    assert (index.row(), index.column()) == (0, 1)


def test_focus_column_is_a_noop_for_an_empty_grid():
    grid = MultiColumnGrid(("x", "y"))

    grid.focus_column(0)  # no rows exist yet -- nothing to land on

    assert not grid._view.currentIndex().isValid()


def test_focus_column_is_a_noop_for_an_out_of_range_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])

    grid.focus_column(5)

    assert not grid._view.currentIndex().isValid()


# ----------------------------------------------------------------------
# add_toolbar_widget: appending an extra affordance into the +/− row
# ----------------------------------------------------------------------


def test_add_toolbar_widget_places_it_before_the_trailing_stretch():
    from PySide6.QtWidgets import QLabel

    grid = MultiColumnGrid(("x",))
    extra = QLabel("extra")

    grid.add_toolbar_widget(extra)

    assert grid._buttons.itemAt(grid._buttons.count() - 2).widget() is extra


def test_add_toolbar_widget_is_a_noop_when_read_only():
    from PySide6.QtWidgets import QLabel

    grid = MultiColumnGrid(("x",), read_only=True)

    grid.add_toolbar_widget(QLabel("extra"))  # must not raise: no button row exists


# ----------------------------------------------------------------------
# Per-column clipboard paste (D7)
# ----------------------------------------------------------------------


def test_apply_paste_replace_writes_only_the_named_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0, 2.0])
    grid.set_column_values(1, [10.0, 20.0])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.apply_paste(0, [5.0, 6.0, 7.0], PastePreviewResult.REPLACE)

    assert grid.column_values(0) == [5.0, 6.0, 7.0]
    assert grid.column_values(1) == [10.0, 20.0]  # untouched
    assert fired == [1]


def test_apply_paste_append_extends_the_named_column():
    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(1, [1.0, 2.0])

    grid.apply_paste(1, [3.0, 4.0], PastePreviewResult.APPEND)

    assert grid.column_values(1) == [1.0, 2.0, 3.0, 4.0]


def test_apply_paste_keeps_non_numeric_cells_verbatim():
    grid = MultiColumnGrid(("x",))

    grid.apply_paste(0, ["oops", 1.0], PastePreviewResult.REPLACE)

    assert grid.column_values(0) == ["oops", 1.0]


def test_paste_targets_the_focused_column(monkeypatch):
    """``paste()`` reads the clipboard and previews into whichever column
    currently holds the current-cell ring -- confirmed via a stubbed dialog
    so the (modal) preview never blocks."""
    import ui_qt.cards.grid as grid_module

    class _StubClipboard:
        def text(self):
            return "5\n6\n"

    monkeypatch.setattr(
        grid_module.QApplication, "clipboard", staticmethod(lambda: _StubClipboard())
    )

    class _StubDialog:
        def __init__(self, parsed, headers, parent=None):
            self.choice = PastePreviewResult.REPLACE
            self._parsed = parsed

        def exec(self):
            pass

    monkeypatch.setattr(grid_module, "PastePreviewDialog", _StubDialog)

    grid = MultiColumnGrid(("x", "y"))
    grid.set_column_values(0, [1.0])
    grid.set_column_values(1, [1.0])
    grid.focus_column(1)

    grid.paste()

    assert grid.column_values(1) == [5, 6]
    assert grid.column_values(0) == [1.0]  # untouched


def test_grid_has_paste_action_in_its_context_menu():
    grid = MultiColumnGrid(("x", "y"))
    actions = [a.text() for a in grid._view.actions()]
    assert actions == ["Paste", "Add cell", "Remove cell"]


def test_read_only_grid_has_no_context_menu_actions():
    grid = MultiColumnGrid(("x", "y"), read_only=True)
    assert grid._view.actions() == []


def test_paste_is_a_noop_when_read_only(monkeypatch):
    import ui_qt.cards.grid as grid_module

    class _StubClipboard:
        def text(self):
            return "5\n"

    monkeypatch.setattr(
        grid_module.QApplication, "clipboard", staticmethod(lambda: _StubClipboard())
    )
    grid = MultiColumnGrid(("x",), read_only=True)

    grid.paste()  # must not raise, and must not open a dialog

    assert grid.column_values(0) == []
