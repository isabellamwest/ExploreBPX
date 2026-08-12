"""chart_axes: conventions shared by TablePreview and MultiSeriesChart.

Two things live here that neither widget's own test file covers on its own:

- the y axis tick-count fix for the QtCharts "..." elision bug (measured on
  TablePreview at its compact height -- see ``chart_axes.Y_AXIS_TICK_COUNT``),
- the hover-readout hit-test, exercised as the pure function it is
  documented to be: plain points and geometry in, a hit or ``None`` out, no
  live chart required.

Each widget's own test file (``test_table_preview.py``,
``test_multi_series_chart.py``) covers the wiring specific to it (feeding
the cache from its own series, threading a display name, hiding a
legend-toggled curve).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from ui_qt.cards.chart_axes import (
    Y_AXIS_TICK_COUNT,
    ReadoutPoint,
    ReadoutSeries,
    charts_available,
    fit_axis,
    format_readout_number,
    nearest_readout_point,
    readout_tooltip_text,
)
from ui_qt.style import CHART_SERIES


@pytest.fixture(autouse=True)
def _qapp():
    from PySide6.QtWidgets import QApplication

    yield QApplication.instance() or QApplication([])


requires_charts = pytest.mark.skipif(
    not charts_available(), reason="QtCharts not available in this PySide6 build"
)


def _series(name, points, visible=True, colour="#1f6feb"):
    """*points*: an iterable of ``(x, y, pixel_x, pixel_y)``."""
    return ReadoutSeries(name, colour, tuple(points), visible)


# ----------------------------------------------------------------------
# nearest_readout_point: the pure hit-test
# ----------------------------------------------------------------------


def test_exact_hit_returns_the_point():
    series = [_series("Main", [(0.0, 1.0, 50.0, 60.0)])]

    hit = nearest_readout_point(series, 50.0, 60.0, 24.0)

    assert hit == ReadoutPoint("Main", "#1f6feb", 0.0, 1.0, 50.0, 60.0)


def test_miss_well_beyond_the_snap_radius_returns_none():
    series = [_series("Main", [(0.0, 1.0, 50.0, 60.0)])]

    assert nearest_readout_point(series, 200.0, 200.0, 24.0) is None


def test_snap_radius_is_inclusive_at_the_boundary_and_exclusive_past_it():
    series = [_series("Main", [(0.0, 0.0, 0.0, 0.0)])]

    assert nearest_readout_point(series, 24.0, 0.0, 24.0) is not None
    assert nearest_readout_point(series, 24.01, 0.0, 24.0) is None


def test_nearest_of_several_points_on_one_series_wins():
    series = [_series("Main", [(0.0, 0.0, 0.0, 0.0), (1.0, 1.0, 10.0, 10.0)])]

    hit = nearest_readout_point(series, 11.0, 11.0, 24.0)

    assert (hit.x, hit.y) == (1.0, 1.0)


def test_nearest_across_two_visible_series_wins():
    series = [
        _series("Far", [(0.0, 0.0, 0.0, 0.0)]),
        _series("Near", [(0.0, 0.0, 10.0, 10.0)]),
    ]

    hit = nearest_readout_point(series, 11.0, 11.0, 24.0)

    assert hit.series_name == "Near"


def test_hidden_series_is_never_hit_even_when_it_is_the_closest():
    series = [
        _series("Hidden", [(0.0, 0.0, 10.0, 10.0)], visible=False),
        _series("Visible", [(0.0, 0.0, 20.0, 20.0)], visible=True),
    ]

    hit = nearest_readout_point(series, 10.0, 10.0, 24.0)

    assert hit.series_name == "Visible"


def test_every_series_hidden_is_a_miss():
    series = [_series("Hidden", [(0.0, 0.0, 0.0, 0.0)], visible=False)]

    assert nearest_readout_point(series, 0.0, 0.0, 24.0) is None


def test_no_series_at_all_is_a_miss():
    assert nearest_readout_point([], 0.0, 0.0, 24.0) is None


def test_a_series_with_no_points_never_crashes():
    series = [_series("Empty", [])]

    assert nearest_readout_point(series, 0.0, 0.0, 24.0) is None


# ----------------------------------------------------------------------
# format_readout_number / readout_tooltip_text
# ----------------------------------------------------------------------


def test_format_readout_number_is_compact_and_trims_trailing_zeros():
    assert format_readout_number(50000) == "50000"
    assert format_readout_number(3.94) == "3.94"
    assert format_readout_number(0.1) == "0.1"


def test_format_readout_number_keeps_six_significant_figures():
    assert format_readout_number(1234567) == "1.23457e+06"


def test_tooltip_omits_the_series_name_for_a_single_visible_series():
    hit = ReadoutPoint("Chen2020", "#008300", 50000.0, 3.94, 1.0, 2.0)

    text = readout_tooltip_text(hit, "Time [s]", "Voltage [V]", show_series_name=False)

    assert text == "Time [s] 50000 · Voltage [V] 3.94"


def test_tooltip_leads_with_the_series_name_for_more_than_one_visible():
    hit = ReadoutPoint("Chen2020", "#008300", 50000.0, 3.94, 1.0, 2.0)

    text = readout_tooltip_text(hit, "Time [s]", "Voltage [V]", show_series_name=True)

    assert text == "Chen2020 · Time [s] 50000 · Voltage [V] 3.94"


def test_tooltip_falls_back_to_the_bare_axis_letters_without_titles():
    hit = ReadoutPoint("Main", "#1f6feb", 1.0, 2.0, 0.0, 0.0)

    text = readout_tooltip_text(hit, "", "", show_series_name=False)

    assert text == "x 1 · y 2"


def test_tooltip_never_contains_an_em_dash():
    hit = ReadoutPoint("Chen2020", "#008300", 50000.0, 3.94, 1.0, 2.0)

    text = readout_tooltip_text(hit, "Time [s]", "Voltage [V]", show_series_name=True)

    assert "\u2014" not in text


# ----------------------------------------------------------------------
# fit_axis: the y-axis tick-count fix
# ----------------------------------------------------------------------


class _FakeAxis:
    """A minimal double for what ``fit_axis`` needs -- enough to prove call
    order without a real Qt object, and independent of a live QtCharts
    build."""

    def __init__(self) -> None:
        self.calls: list[str] = []
        self.tick_count: int | None = None

    def setRange(self, low, high) -> None:  # noqa: N802 (Qt-style name)
        self.calls.append("setRange")

    def applyNiceNumbers(self) -> None:  # noqa: N802 (Qt-style name)
        self.calls.append("applyNiceNumbers")

    def setTickCount(self, count: int) -> None:  # noqa: N802 (Qt-style name)
        self.calls.append("setTickCount")
        self.tick_count = count


def test_fit_axis_without_an_override_never_touches_tick_count():
    axis = _FakeAxis()

    fit_axis(axis, 0.0, 1.0)

    assert "setTickCount" not in axis.calls


def test_fit_axis_with_an_override_sets_tick_count_after_nice_numbers():
    """Call order matters -- see the root-cause test below."""
    axis = _FakeAxis()

    fit_axis(axis, 0.0, 1.0, tick_count=Y_AXIS_TICK_COUNT)

    assert axis.calls == ["setRange", "applyNiceNumbers", "setTickCount"]
    assert axis.tick_count == Y_AXIS_TICK_COUNT


@requires_charts
def test_apply_nice_numbers_resets_a_tick_count_set_before_it():
    """Documents the real root cause of the y-axis "..." bug: QValueAxis's
    own applyNiceNumbers recomputes its preferred tick count on every call,
    silently discarding a setTickCount made before it. This is exactly why
    fit_axis's override applies *after* applyNiceNumbers rather than before.
    """
    from PySide6.QtCharts import QValueAxis

    axis = QValueAxis()
    axis.setTickCount(Y_AXIS_TICK_COUNT)

    fit_axis(axis, 0.09202, 2.02988)  # no override -- nice numbers runs unopposed

    assert axis.tickCount() != Y_AXIS_TICK_COUNT


# ----------------------------------------------------------------------
# ReadoutChartView: constructed directly, not through either widget
# ----------------------------------------------------------------------


def _build_view():
    """A minimal chart + axes + view, styled the same way both real widgets
    build one -- enough to exercise ReadoutChartView on its own."""
    from PySide6.QtCore import Qt
    from PySide6.QtCharts import QChart, QValueAxis

    from ui_qt.cards.chart_axes import ReadoutChartView, fit_axis

    chart = QChart()
    axis_x, axis_y = QValueAxis(), QValueAxis()
    chart.addAxis(axis_x, Qt.AlignBottom)
    chart.addAxis(axis_y, Qt.AlignLeft)
    fit_axis(axis_x, 0.0, 1.0)
    fit_axis(axis_y, 0.0, 1.0)
    view = ReadoutChartView(chart, axis_x, axis_y)
    view.resize(200, 140)
    view.show()
    return view, chart


@requires_charts
def test_readout_chart_view_shows_the_marker_on_a_hit():
    from PySide6.QtCore import QPoint, QPointF

    view, chart = _build_view()
    view.set_readout_series([("Main", "#1f6feb", [(0.5, 0.5)], True)])
    pixel = chart.mapToPosition(QPointF(0.5, 0.5))

    view._update_readout(pixel.x(), pixel.y(), QPoint(0, 0))

    assert view._marker.isVisible()


@requires_charts
def test_readout_chart_view_leave_event_hides_the_marker():
    from PySide6.QtCore import QEvent, QPoint, QPointF

    view, chart = _build_view()
    view.set_readout_series([("Main", "#1f6feb", [(0.5, 0.5)], True)])
    pixel = chart.mapToPosition(QPointF(0.5, 0.5))
    view._update_readout(pixel.x(), pixel.y(), QPoint(0, 0))
    assert view._marker.isVisible()

    view.leaveEvent(QEvent(QEvent.Leave))

    assert not view._marker.isVisible()


# ----------------------------------------------------------------------
# style.CHART_SERIES: one palette source (moved out of the compare dialog)
# ----------------------------------------------------------------------


def test_chart_series_palette_is_four_colours_distinct_from_reference_badges():
    from ui_qt.style import REFERENCE_BADGES

    assert len(CHART_SERIES) == 4
    assert set(CHART_SERIES).isdisjoint(REFERENCE_BADGES)


def test_database_examples_dialog_uses_the_shared_palette():
    from ui_qt.cards import database_examples_dialog

    assert database_examples_dialog._REFERENCE_COLORS is CHART_SERIES
