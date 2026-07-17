"""MultiSeriesChart: several named curves overlaid on one pair of axes."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.cards.multi_series_chart import MultiSeriesChart


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


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
