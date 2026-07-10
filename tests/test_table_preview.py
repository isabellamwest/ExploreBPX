"""TablePreview: the live plot of the value a grid is editing.

The preview is an enhancement, never a dependency of editing: it must plot only
what can be plotted (numeric points), skip non-numeric cells rather than coerce
them, and disable itself cleanly if QtCharts is unavailable. These tests pin
that contract, plus the wiring that keeps the plot in step with the grid in
``SeriesCard`` and the interpolated-table body.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from ui_qt.cards.registry import create_card
from ui_qt.cards.table_preview import TablePreview, charts_available


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


requires_charts = pytest.mark.skipif(
    not charts_available(), reason="QtCharts not available in this PySide6 build"
)


# ----------------------------------------------------------------------
# TablePreview: what it plots, and what it refuses to
# ----------------------------------------------------------------------


@requires_charts
def test_xy_mode_plots_column1_against_column0():
    preview = TablePreview(mode="xy")
    preview.update_rows([[0, 1.0], [1, 2.0], [2, 1.5]])
    assert preview._line.count() == 3
    assert preview._dots.count() == 3


@requires_charts
def test_xy_points_are_sorted_left_to_right():
    """A line reads along x, so out-of-order rows plot in x order."""
    preview = TablePreview(mode="xy")
    preview.update_rows([[2, 20.0], [0, 0.0], [1, 10.0]])
    xs = [preview._line.at(i).x() for i in range(preview._line.count())]
    assert xs == [0.0, 1.0, 2.0]


@requires_charts
def test_series_mode_plots_value_against_row_number():
    preview = TablePreview(mode="series")
    preview.update_rows([[10.0], [12.0], [11.0]])
    points = [(preview._line.at(i).x(), preview._line.at(i).y()) for i in range(3)]
    assert points == [(0.0, 10.0), (1.0, 12.0), (2.0, 11.0)]


@requires_charts
def test_non_numeric_cells_are_skipped_never_coerced():
    """A cell holding a string or blank has no axis position; it is skipped,
    not plotted as zero."""
    preview = TablePreview(mode="xy")
    preview.update_rows([[0, 1.0], ["oops", 2.0], [1, None], [2, 3.0]])
    xs = [preview._line.at(i).x() for i in range(preview._line.count())]
    assert xs == [0.0, 2.0]  # only the two fully-numeric rows


@requires_charts
def test_bool_cells_are_not_plotted():
    """A bool is not a data point (it round-trips as text elsewhere)."""
    preview = TablePreview(mode="series")
    preview.update_rows([[True], [1.0], [False]])
    assert preview._line.count() == 1


@requires_charts
def test_empty_or_all_bad_rows_show_the_empty_state():
    # isVisibleTo (not isVisible) reports intended visibility even though the
    # unshown offscreen widget reports isVisible() == False for everything.
    preview = TablePreview(mode="xy")
    preview.update_rows([])
    assert preview._empty.isVisibleTo(preview)
    assert not preview._view.isVisibleTo(preview)

    preview.update_rows([["a", "b"], [None, None]])
    assert preview._empty.isVisibleTo(preview)

    # ... and a real point flips back to the chart.
    preview.update_rows([[0, 1.0], [1, 2.0]])
    assert preview._view.isVisibleTo(preview)
    assert not preview._empty.isVisibleTo(preview)


@requires_charts
def test_a_single_point_still_gets_a_sane_axis_range():
    """All-equal coordinates must not collapse the axis to a zero-width range."""
    preview = TablePreview(mode="xy")
    preview.update_rows([[5.0, 5.0]])
    assert preview._axis_x.min() < preview._axis_x.max()
    assert preview._axis_y.min() < preview._axis_y.max()


def test_preview_disables_cleanly_when_charts_absent(monkeypatch):
    """Simulate a build without QtCharts: the widget contributes nothing and
    every method is a safe no-op, so the grid still works."""
    import ui_qt.cards.table_preview as tp

    monkeypatch.setattr(tp, "_CHARTS_AVAILABLE", False)
    preview = tp.TablePreview(mode="xy")
    assert preview.available is False
    assert preview.isVisible() is False
    # No chart objects were built; these must not raise.
    preview.set_axis_titles("x", "y")
    preview.update_rows([[0, 1], [1, 2]])


# ----------------------------------------------------------------------
# Wiring: the plot tracks the grid live
# ----------------------------------------------------------------------


def _series_card(value):
    param = ParameterItem(
        label="Voltage [V]",
        path=("Validation", "run", "Voltage [V]"),
        kind=ParameterKind.SERIES,
        value=value,
    )
    return create_card(param, None)


@requires_charts
def test_series_card_seeds_the_preview_from_its_value():
    card = _series_card([4.1, 4.0, 3.9])
    assert card._preview._line.count() == 3


@requires_charts
def test_series_card_preview_updates_when_a_cell_changes():
    card = _series_card([4.1, 4.0, 3.9])
    card._grid._model.setData(card._grid._model.index(1, 0), "2.0", Qt.EditRole)
    ys = [card._preview._line.at(i).y() for i in range(card._preview._line.count())]
    assert 2.0 in ys


@requires_charts
def test_series_card_preview_follows_add_and_remove_row():
    card = _series_card([4.1, 4.0])
    card._grid.insert_row()
    card._grid._model.setData(card._grid._model.index(2, 0), "3.5", Qt.EditRole)
    assert card._preview._line.count() == 3
    card._grid.remove_row()
    assert card._preview._line.count() == 2


@requires_charts
def test_interpolated_table_body_preview_tracks_the_grid():
    param = ParameterItem(
        label="OCP [V]",
        path=("Parameterisation", "Negative electrode", "OCP [V]"),
        kind=ParameterKind.FUNCTION,
        value={"x": [0.0, 1.0], "y": [1.7, 0.1]},
    )
    card = create_card(param, None)
    body = card._modes[2].body  # InterpolatedTable
    assert body._preview._line.count() == 2
    body._grid._model.setData(body._grid._model.index(0, 1), "1.9", Qt.EditRole)
    ys = [body._preview._line.at(i).y() for i in range(body._preview._line.count())]
    assert 1.9 in ys


@requires_charts
def test_seeding_the_preview_does_not_mark_the_card_dirty():
    """Building the card wires the preview from the seed; that must not count
    as user interaction."""
    card = _series_card([4.1, 4.0, 3.9])
    assert card.is_dirty is False
