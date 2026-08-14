"""The grid's two Enter layers made legible: step-down + the pending bar.

Two mechanisms keep the cell/grid Enter split from being a trap (see the
``grid`` module docstring):

* confirming a cell steps the selection down a row (``_GridView``), so
  spreadsheet-style repeated Enter walks the column instead of falling
  through to the grid layer and committing the document by accident;
* a dirty draft shows an "Unsaved changes" bar whose Apply/Discard buttons
  re-enter the exact keyboard paths. The *card* drives its visibility from
  ``is_dirty`` -- never the grid itself -- so an edit typed back to the
  original value hides it again.

Unit-level widget tests cover the bar's contract; driver tests prove the
step-down against the real delegate/editor pipeline, which only runs in a
shown window.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from explore_bpx.core.parameter_types import ParameterKind
from explore_bpx.core.tree_model import ParameterItem
from explore_bpx.ui_qt.cards.grid import MultiColumnGrid, NumericGrid
from explore_bpx.ui_qt.cards.registry import create_card

_RUN = ("Validation", "C/20 discharge")
_TIME = _RUN + ("Time [s]",)


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def _table_card(value):
    param = ParameterItem(
        label="My table",
        path=("Parameterisation", "User-defined", "My table"),
        kind=ParameterKind.TABLE,
        value=value,
    )
    return create_card(param, None)


def _series_card(value):
    param = ParameterItem(
        label="Time [s]",
        path=("Validation", "run", "Time [s]"),
        kind=ParameterKind.SERIES,
        value=value,
    )
    return create_card(param, None)


# ----------------------------------------------------------------------
# The bar itself: hidden until told, absent on a read-only grid
# ----------------------------------------------------------------------


def test_pending_bar_hidden_until_told():
    grid = NumericGrid(("x", "y"))
    assert grid._pending_bar.isHidden()
    grid.set_pending(True)
    assert not grid._pending_bar.isHidden()
    grid.set_pending(False)
    assert grid._pending_bar.isHidden()


def test_pending_bar_names_both_halves_of_the_contract():
    """The buttons carry their keys in the tooltip -- the bar exists to make
    the invisible keyboard contract readable."""
    grid = NumericGrid(("x", "y"))
    assert grid._pending_bar.apply_button.text() == "Apply"
    assert grid._pending_bar.discard_button.text() == "Discard"
    assert grid._pending_bar.apply_button.toolTip() == "Write these edits to the file (Enter)"
    assert grid._pending_bar.discard_button.toolTip() == "Revert to the file's value (Esc)"


def test_read_only_multicolumn_grid_builds_no_pending_bar():
    grid = MultiColumnGrid(("a", "b"), read_only=True)
    assert grid._pending_bar is None
    grid.set_pending(True)  # a safe no-op, exactly like the button row


# ----------------------------------------------------------------------
# Card-driven visibility: the bar mirrors is_dirty, not "was touched"
# ----------------------------------------------------------------------


def test_table_card_bar_tracks_real_dirtiness():
    card = _table_card({"x": [0.0, 1.0], "y": [1.0, 2.0]})
    grid = card._modes[0].body._grid
    assert grid._pending_bar.isHidden()

    grid._model.setData(grid._model.index(0, 1), "9", Qt.EditRole)
    assert card.is_dirty is True
    assert not grid._pending_bar.isHidden()

    # Typing the original value back means Enter would write nothing -- the
    # bar must not claim otherwise.
    grid._model.setData(grid._model.index(0, 1), "1", Qt.EditRole)
    assert card.is_dirty is False
    assert grid._pending_bar.isHidden()


def test_table_card_escape_hides_the_bar():
    card = _table_card({"x": [0.0, 1.0], "y": [1.0, 2.0]})
    grid = card._modes[0].body._grid
    grid._model.setData(grid._model.index(0, 1), "9", Qt.EditRole)
    assert not grid._pending_bar.isHidden()

    card._reset_draft()

    assert card.is_dirty is False
    assert grid._pending_bar.isHidden()


def test_apply_button_reenters_the_commit_path():
    card = _table_card({"x": [0.0, 1.0], "y": [1.0, 2.0]})
    grid = card._modes[0].body._grid
    fired = []
    card.commit_requested.connect(lambda: fired.append(1))

    grid._model.setData(grid._model.index(0, 1), "9", Qt.EditRole)
    grid._pending_bar.apply_button.click()

    assert fired == [1]  # exactly what Enter on the grid emits


def test_discard_button_reenters_the_escape_path():
    card = _table_card({"x": [0.0, 1.0], "y": [1.0, 2.0]})
    grid = card._modes[0].body._grid
    grid._model.setData(grid._model.index(0, 1), "9", Qt.EditRole)

    grid._pending_bar.discard_button.click()

    assert card.value() == {"x": [0.0, 1.0], "y": [1.0, 2.0]}
    assert card.is_dirty is False
    assert grid._pending_bar.isHidden()


def test_series_card_binds_the_bar_too():
    card = _series_card([0.0, 100.0])
    grid = card._grid
    assert grid._pending_bar.isHidden()

    grid._model.setData(grid._model.index(0, 0), "5", Qt.EditRole)

    assert card.is_dirty is True
    assert not grid._pending_bar.isHidden()


# ----------------------------------------------------------------------
# Cell-editor Enter steps down (real delegate pipeline, shown window)
# ----------------------------------------------------------------------


def test_cell_editor_enter_confirms_and_steps_down(app_driver, spm_with_validation_path):
    """Enter in an open cell editor confirms that cell and moves the selection
    one row down -- so "Enter, Enter" keeps walking the column instead of
    falling through to the grid layer and committing the document."""
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)
    view = d.experiment_card()._grid._view

    d.open_experiment_cell_editor("Time [s]", 0)
    d.press_in_experiment_cell_editor(Qt.Key_Return)

    assert d.experiment_cell_editor_open() is False
    assert view.currentIndex().row() == 1
    assert d.undo_enabled() is False  # nothing reached the document


def test_cell_editor_enter_on_last_row_stays_put(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)
    view = d.experiment_card()._grid._view
    last = view.model().rowCount() - 1

    d.open_experiment_cell_editor("Time [s]", last)
    d.press_in_experiment_cell_editor(Qt.Key_Return)

    assert d.experiment_cell_editor_open() is False
    assert view.currentIndex().row() == last


# ----------------------------------------------------------------------
# ExperimentCard: the bar mirrors the same per-column diff Enter commits
# ----------------------------------------------------------------------


def test_experiment_bar_shows_on_edit_and_discard_reverts(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)
    grid = d.experiment_card()._grid
    assert grid._pending_bar.isHidden()

    d.set_experiment_cell("Time [s]", 0, "999")
    assert not grid._pending_bar.isHidden()

    grid._pending_bar.discard_button.click()

    assert d.experiment_column_values("Time [s]") == [0, 100, 200]
    assert grid._pending_bar.isHidden()
    assert d.undo_enabled() is False


def test_experiment_apply_button_commits_the_dirty_columns(app_driver, spm_with_validation_path):
    d = app_driver
    d.open(spm_with_validation_path).go_to(_TIME)

    d.set_experiment_cell("Time [s]", 0, "999")
    d.experiment_card()._grid._pending_bar.apply_button.click()

    assert d.experiment_column_values("Time [s]") == [999, 100, 200]
    assert d.undo_enabled() is True
