"""MultiSeriesChart: several named curves overlaid on one pair of axes."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from explore_bpx.ui_qt.cards.multi_series_chart import MultiSeriesChart


@pytest.fixture(autouse=True)
def _qapp():
    return QApplication.instance() or QApplication([])


def test_a_series_with_zero_points_does_not_crash():
    """A live draft column can be added with nothing typed yet -- the chart
    must tolerate an empty series rather than crash computing an axis range
    over zero points (regression: ``min()``/``max()`` on an empty sequence)."""
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("you", [], "#1f6feb", 3.0)  # must not raise


def test_one_empty_series_beside_one_real_series_ranges_on_the_real_points():
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("you", [], "#1f6feb", 3.0)
    chart.set_series("ref", [(0.0, 1.0), (1.0, 3.0)], "#008300")

    assert chart._axis_x.min() <= 0.0
    assert chart._axis_x.max() >= 1.0


def test_removing_the_last_series_shows_the_empty_state_again():
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("ref", [(0.0, 1.0)], "#008300")
    assert chart._empty.isHidden()

    chart.remove_series("ref")
    assert not chart._empty.isHidden()


def test_y_axis_tick_count_matches_the_shared_constant():
    """Same fix TablePreview needs, applied here too for consistency between
    the app's two chart widgets (chart_axes.Y_AXIS_TICK_COUNT) -- this
    widget's own 180px height wasn't observed to elide, but both share one
    fit_axis call so neither drifts from the other."""
    from explore_bpx.ui_qt.cards.chart_axes import Y_AXIS_TICK_COUNT

    chart = MultiSeriesChart(height=180)
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("ref", [(0.0, 1.0), (1.0, 5.0)], "#008300")

    assert chart._axis_y.tickCount() == Y_AXIS_TICK_COUNT


# ----------------------------------------------------------------------
# Hover readout: the cache MultiSeriesChart feeds ReadoutChartView
# ----------------------------------------------------------------------


def test_readout_cache_defaults_a_series_name_to_its_id():
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("you", [(0.0, 1.0)], "#1f6feb", 3.0)

    assert chart._view._series == [("you", "#1f6feb", ((0.0, 1.0),), True)]


def test_readout_cache_uses_an_explicit_display_name_when_given():
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("about_energy/nmc::run", [(0.0, 4.1)], "#008300", name="NMC pouch cell · C/20 discharge")

    names = [name for name, *_rest in chart._view._series]
    assert names == ["NMC pouch cell · C/20 discharge"]


def test_readout_cache_drops_a_removed_series():
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("you", [(0.0, 1.0)], "#1f6feb")
    chart.set_series("ref", [(0.0, 2.0)], "#008300")

    chart.remove_series("ref")

    ids = [name for name, *_rest in chart._view._series]
    assert ids == ["you"]


def test_readout_cache_every_series_is_visible_no_hide_affordance_here():
    chart = MultiSeriesChart()
    if not chart.available:
        pytest.skip("QtCharts unavailable in this build")

    chart.set_series("you", [(0.0, 1.0)], "#1f6feb")

    assert all(visible for *_rest, visible in chart._view._series)
