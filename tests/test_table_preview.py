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
from ui_qt.cards.chart_axes import Y_AXIS_TICK_COUNT
from ui_qt.cards.registry import create_card
from ui_qt.cards.table_preview import ReferenceCurve, TablePreview, charts_available
from ui_qt.style import ACCENT


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
def test_non_finite_cells_are_skipped_and_axes_fit_the_rest():
    """A typed ``nan`` or ``inf`` reaches the grid as a float, but QtCharts
    refuses such points -- passing them to the axis fit anyway would desync the
    visible range from the line actually drawn."""
    preview = TablePreview(mode="xy")
    preview.update_rows([[1, 2.0], [float("nan"), 5.0], [2, float("inf")], [3, 4.0]])
    assert preview._line.count() == 2  # only the two finite rows
    assert preview._axis_y.min() <= 2.0
    assert preview._axis_y.max() >= 4.0

    # All rows non-finite is "nothing to plot", not a broken chart.
    preview.update_rows([[float("nan"), float("inf")]])
    assert preview._empty.isVisibleTo(preview)


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


# ----------------------------------------------------------------------
# Y axis tick count: the QtCharts "..." elision regression
# ----------------------------------------------------------------------


@requires_charts
def test_y_axis_tick_count_is_forced_to_the_shared_constant():
    """QtCharts silently elides every y tick label to "..." at this widget's
    compact height once applyNiceNumbers picks its own (commonly 4-6) tick
    count -- proven visually against chen2020's own OCP table (0.09-2.03 V).
    Forcing a low, fixed count after every fit is what keeps numerals on
    screen (chart_axes.Y_AXIS_TICK_COUNT); the x axis is untouched."""
    preview = TablePreview(mode="xy")
    preview.update_rows([[0.005, 2.02988], [0.5, 1.0], [0.995, 0.09202]])

    assert preview._axis_y.tickCount() == Y_AXIS_TICK_COUNT


# ----------------------------------------------------------------------
# Hover readout: the cache TablePreview feeds ReadoutChartView
# ----------------------------------------------------------------------


@requires_charts
def test_readout_cache_names_the_main_series_and_keeps_it_visible():
    preview = TablePreview(mode="xy")
    preview.update_rows([[0.0, 1.0], [1.0, 2.0]])

    names = [(name, colour, visible) for name, colour, _points, visible in preview._view._series]

    assert names == [("Main", ACCENT, True)]


@requires_charts
def test_readout_cache_carries_a_reference_curves_own_name_and_colour():
    preview = TablePreview(mode="xy")
    preview.update_rows([[0.0, 1.0]])
    curve = ReferenceCurve("A", "#008300", "Chen2020 · C/20 discharge", [[0.0, 0.9]])

    preview.set_reference_curves([curve])

    cache = {name: (colour, visible) for name, colour, _points, visible in preview._view._series}
    assert cache["Chen2020 · C/20 discharge"] == ("#008300", True)


@requires_charts
def test_hiding_a_reference_curve_marks_it_not_visible_in_the_readout_cache():
    """A legend-hidden curve must stop being a hover target immediately, not
    only after the next redraw."""
    preview = TablePreview(mode="xy")
    preview.update_rows([[0.0, 1.0]])
    curve = ReferenceCurve("A", "#008300", "Chen2020", [[0.0, 0.9]])
    preview.set_reference_curves([curve])

    preview._on_curve_toggled(0, False)

    cache = {name: visible for name, _colour, _points, visible in preview._view._series}
    assert cache["Chen2020"] is False
    assert cache["Main"] is True


# ----------------------------------------------------------------------
# TableBody's y axis unit -- threaded from the parameter, not hardcoded
# ----------------------------------------------------------------------


def _function_card(unit: str, value: object):
    param = ParameterItem(
        label=f"OCP [{unit}]" if unit else "OCP",
        path=("Parameterisation", "Negative electrode", "OCP"),
        kind=ParameterKind.FUNCTION,
        value=value,
        unit=unit,
    )
    return create_card(param, None)


def _table_card(unit: str, value: object):
    param = ParameterItem(
        label=f"Custom curve [{unit}]" if unit else "Custom curve",
        path=("Parameterisation", "User-defined", "Custom curve"),
        kind=ParameterKind.TABLE,
        value=value,
        unit=unit,
    )
    return create_card(param, None)


@requires_charts
def test_function_card_table_mode_titles_y_with_the_parameters_unit():
    card = _function_card("V", {"x": [0.0, 1.0], "y": [1.7, 0.1]})
    body = card._modes[2].body  # InterpolatedTable

    assert body._preview._axis_y.titleText() == "y [V]"
    assert body._preview._axis_x.titleText() == "x"


@requires_charts
def test_function_card_table_mode_y_title_has_no_unit_when_none_is_declared():
    card = _function_card("", {"x": [0.0, 1.0], "y": [1.7, 0.1]})
    body = card._modes[2].body

    assert body._preview._axis_y.titleText() == "y"


@requires_charts
def test_table_card_titles_y_with_the_parameters_unit():
    card = _table_card("Ohm", {"x": [0.0, 1.0], "y": [2.0, 3.0]})

    assert card._table_body._preview._axis_y.titleText() == "y [Ohm]"
    assert card._table_body._preview._axis_x.titleText() == "x"
