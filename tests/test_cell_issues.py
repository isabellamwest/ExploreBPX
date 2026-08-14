"""``cell_issues`` mapping, and its rendering on ``NumericGrid``.

The pure mapping (validator location -> grid cell) is tested against the
exact ``loc`` shapes the real BPX validator emits for a bad series element and
a bad table point; the grid tests then confirm ``set_cell_issues`` paints
only what it was told, through the model's ``BackgroundRole``/``ToolTipRole``,
and never marks the card touched.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from ui_qt.cards.cell_issues import experiment_cells, series_cells, table_cells
from ui_qt.cards.grid import NumericGrid


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


@dataclass(frozen=True)
class _Issue:
    """A minimal stand-in for ``PydanticErrorDiagnostic``: just ``loc``/``message``."""

    loc: tuple[str, ...] = field(default_factory=tuple)
    message: str = ""


# ----------------------------------------------------------------------
# Pure mapping: series_cells
# ----------------------------------------------------------------------


def test_series_cells_maps_the_confirmed_loc_shape():
    issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", "1", "float"),
        message="Input should be a valid number, unable to parse string as a number",
    )
    assert series_cells([issue], "Time [s]") == {(1, 0): issue.message}


def test_series_cells_dedups_two_union_diagnostics_on_one_cell():
    """A float|int union reports twice for the same bad cell -- once per
    failed member -- with different messages; the tooltip must show both."""
    float_issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", "1", "float"),
        message="Input should be a valid number, unable to parse string as a number",
    )
    int_issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", "1", "int"),
        message="Input should be a valid integer, unable to parse string as an integer",
    )
    result = series_cells([float_issue, int_issue], "Time [s]")
    assert result == {(1, 0): f"{float_issue.message}\n{int_issue.message}"}


def test_series_cells_ignores_issue_with_no_loc():
    issue = _Issue(loc=(), message="Some model-level check failed")
    assert series_cells([issue], "Time [s]") == {}


def test_series_cells_ignores_non_digit_index_part():
    issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", "oops", "float"),
        message="should not matter",
    )
    assert series_cells([issue], "Time [s]") == {}


def test_series_cells_tolerates_a_non_string_index_part():
    """``loc`` parts arrive stringified today, but a bare ``int`` index part
    must be recognised, not raise ``AttributeError``."""
    issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", 1, "float"),
        message="Input should be a valid number",
    )
    assert series_cells([issue], "Time [s]") == {(1, 0): issue.message}


def test_series_cells_out_of_range_row_still_maps_the_index():
    """The pure mapping has no notion of grid size -- it reports exactly what
    the validator said; ignoring an out-of-range row is the grid's job."""
    issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", "7", "float"),
        message="Input should be a valid number",
    )
    assert series_cells([issue], "Time [s]") == {(7, 0): issue.message}


# ----------------------------------------------------------------------
# Pure mapping: table_cells
# ----------------------------------------------------------------------


def test_table_cells_maps_the_confirmed_loc_shape():
    issue = _Issue(
        loc=("Positive electrode", "OCP [V]", "InterpolatedTable", "x", "1"),
        message="Input should be a valid number",
    )
    assert table_cells([issue]) == {(1, 0): issue.message}


def test_table_cells_distinguishes_x_and_y_columns():
    x_issue = _Issue(
        loc=("Positive electrode", "OCP [V]", "InterpolatedTable", "x", "0"),
        message="bad x",
    )
    y_issue = _Issue(
        loc=("Positive electrode", "OCP [V]", "InterpolatedTable", "y", "2"),
        message="bad y",
    )
    result = table_cells([x_issue, y_issue])
    assert result == {(0, 0): "bad x", (2, 1): "bad y"}


# ----------------------------------------------------------------------
# Pure mapping: experiment_cells (ExperimentCard's N-named-column grid)
# ----------------------------------------------------------------------


def test_experiment_cells_maps_each_alias_to_its_own_column():
    time_issue = _Issue(
        loc=("Validation", "C/20 discharge", "Time [s]", "1", "float"),
        message="bad time",
    )
    voltage_issue = _Issue(
        loc=("Validation", "C/20 discharge", "Voltage [V]", "2", "float"),
        message="bad voltage",
    )
    aliases = ("Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]")
    result = experiment_cells([time_issue, voltage_issue], aliases)
    assert result == {(1, 0): "bad time", (2, 2): "bad voltage"}


def test_experiment_cells_only_uses_columns_actually_shown():
    """A run missing Temperature never offers it as a column; a diagnostic
    naming an alias not in *aliases* maps to nothing (there is no such
    column to tint)."""
    issue = _Issue(
        loc=("Validation", "run", "Temperature [K]", "0", "float"),
        message="bad",
    )
    result = experiment_cells([issue], ("Time [s]", "Current [A]", "Voltage [V]"))
    assert result == {}


def test_experiment_cells_dedups_a_union_pair_on_one_cell():
    float_issue = _Issue(
        loc=("Validation", "run", "Voltage [V]", "0", "float"),
        message="Input should be a valid number",
    )
    int_issue = _Issue(
        loc=("Validation", "run", "Voltage [V]", "0", "int"),
        message="Input should be a valid integer",
    )
    result = experiment_cells([float_issue, int_issue], ("Time [s]", "Voltage [V]"))
    assert result == {(0, 1): f"{float_issue.message}\n{int_issue.message}"}


# ----------------------------------------------------------------------
# Grid rendering: set_cell_issues
# ----------------------------------------------------------------------


def test_set_cell_issues_tints_only_the_blamed_cell():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0.0], [1.0], [2.0]])
    grid.set_cell_issues({(1, 0): "Input should be a valid number"})

    model = grid._model
    blamed = model.index(1, 0)
    other = model.index(0, 0)

    assert model.data(blamed, Qt.BackgroundRole) is not None
    assert model.data(blamed, Qt.ToolTipRole) == "Input should be a valid number"
    assert model.data(other, Qt.BackgroundRole) is None
    assert model.data(other, Qt.ToolTipRole) is None


def test_set_cell_issues_out_of_range_row_is_ignored_gracefully():
    """The validator blames row 7 of a 3-row grid: no crash, no tint."""
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0.0], [1.0], [2.0]])

    grid.set_cell_issues({(7, 0): "orphaned diagnostic"})

    for row in range(3):
        index = grid._model.index(row, 0)
        assert grid._model.data(index, Qt.BackgroundRole) is None


def test_set_cell_issues_clears_back_to_defaults():
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0.0], [1.0]])
    grid.set_cell_issues({(0, 0): "bad"})
    assert grid._model.data(grid._model.index(0, 0), Qt.BackgroundRole) is not None

    grid.set_cell_issues({})

    assert grid._model.data(grid._model.index(0, 0), Qt.BackgroundRole) is None
    assert grid._model.data(grid._model.index(0, 0), Qt.ToolTipRole) is None


def test_set_cell_issues_does_not_mark_the_card_touched():
    """Re-tinting from live validation is not an edit -- it must not fire
    ``changed``, or every validator refresh would dirty the card."""
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0.0], [1.0]])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.set_cell_issues({(0, 0): "bad"})

    assert fired == []


def test_set_cell_issues_is_a_noop_when_unchanged():
    """Setting the same issues again must not re-emit ``dataChanged`` -- a
    live-preview refresh reporting the same problem should not repaint."""
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0.0], [1.0]])
    grid.set_cell_issues({(0, 0): "bad"})

    seen = []
    grid._model.dataChanged.connect(lambda *args: seen.append(args))
    grid.set_cell_issues({(0, 0): "bad"})

    assert seen == []


def test_no_issues_set_renders_defaults():
    """If nothing was ever set, rendering is exactly what it always was."""
    grid = NumericGrid(("x", "y"))
    grid.set_values([[0.0, 1.0], [2.0, 3.0]])
    for row in range(2):
        for column in range(2):
            index = grid._model.index(row, column)
            assert grid._model.data(index, Qt.BackgroundRole) is None
            assert grid._model.data(index, Qt.ToolTipRole) is None


def test_insert_row_clears_stale_tints_immediately():
    """A row insert shifts every row below it, so a tint left in place would
    silently point at the wrong (shifted) cell until the validator
    re-answers. It must be gone the instant the row shifts, not on the next
    debounced re-validate."""
    grid = NumericGrid(("Time [s]",))
    grid.set_values([[0.0], [1.0], [2.0]])
    grid.set_cell_issues({(1, 0): "bad"})
    assert grid._model.data(grid._model.index(1, 0), Qt.BackgroundRole) is not None

    grid._view.setCurrentIndex(grid._model.index(0, 0))
    grid.insert_row()  # inserts at row 1, shifting the tinted row to row 2

    for row in range(grid.row_count):
        index = grid._model.index(row, 0)
        assert grid._model.data(index, Qt.BackgroundRole) is None
        assert grid._model.data(index, Qt.ToolTipRole) is None

    # A subsequent validator answer re-tints normally -- clearing is not a
    # one-way latch.
    grid.set_cell_issues({(2, 0): "still bad"})
    assert grid._model.data(grid._model.index(2, 0), Qt.BackgroundRole) is not None
