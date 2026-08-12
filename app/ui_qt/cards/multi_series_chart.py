"""``MultiSeriesChart``: several named curves overlaid on one pair of axes.

Sibling to :class:`.table_preview.TablePreview` and built the same way -- an
import-guarded QtCharts widget that quietly disables itself
(``available`` False) if ``PySide6.QtCharts`` is absent, so a chart is always
an enhancement, never a dependency.

Unlike ``TablePreview`` (exactly one series, the grid being edited), this
widget draws an arbitrary set of named curves, added and removed by a stable
``series_id``. It owns no colour or ordering policy -- the caller (the
database-examples dialog) decides which colour each id gets and keeps its own
legend; this widget only draws whatever it is told, the same division of
responsibility ``TablePreview`` has with the grid it previews.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .chart_axes import (
    CHART_HEIGHT_CEILING,
    fit_axis,
    setup_chart,
    setup_chart_view,
    style_axis,
    tick_count_for_height,
)

try:  # QtCharts is part of PySide6 but absent from some minimal builds.
    from PySide6.QtCharts import QChart, QLineSeries, QValueAxis

    # Only defined in chart_axes when QtCharts itself imported cleanly there
    # too (same guard, same process) -- see ReadoutChartView's own docstring.
    from .chart_axes import ReadoutChartView

    _CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the PySide6 build
    _CHARTS_AVAILABLE = False


def charts_available() -> bool:
    """Whether QtCharts could be imported in this build."""
    return _CHARTS_AVAILABLE


class MultiSeriesChart(QWidget):
    """A small multiple: several ``(x, y)`` curves sharing one axis pair."""

    def __init__(
        self,
        height: int = 100,
        ceiling: int = CHART_HEIGHT_CEILING,
        parent: QWidget | None = None,
    ) -> None:
        """*ceiling* caps how tall the chart may grow as its column widens
        (see ``chart_axes.setup_chart_view``); the database-examples Compare
        dialog passes a lower one since three of these stack in one dialog.
        """
        super().__init__(parent)
        self.available = _CHARTS_AVAILABLE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not _CHARTS_AVAILABLE:
            self.setVisible(False)
            return

        self._chart = QChart()
        setup_chart(self._chart)

        self._axis_x = QValueAxis()
        self._axis_y = QValueAxis()
        for axis in (self._axis_x, self._axis_y):
            style_axis(axis, self.font())
        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)

        self._view = ReadoutChartView(self._chart, self._axis_x, self._axis_y)
        setup_chart_view(self._view, height, ceiling=ceiling)
        layout.addWidget(self._view)

        self._empty = QLabel("No comparison data yet.")
        self._empty.setObjectName("Hint")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True)
        self._empty.setFixedHeight(height)
        layout.addWidget(self._empty)

        self._series: dict[str, QLineSeries] = {}
        #: ``series_id -> (name, colour, points)`` -- the same data
        #: ``set_series`` was already given, kept for the hover view's cache
        #: (see ``_sync_readout_series``) so a mouse move never re-copies
        #: points from the live ``QLineSeries`` objects above.
        self._series_meta: dict[str, tuple[str, str, tuple[tuple[float, float], ...]]] = {}
        self._show_empty(True)

    def set_axis_titles(self, x_title: str, y_title: str) -> None:
        if not self.available:
            return
        self._axis_x.setTitleText(x_title)
        self._axis_y.setTitleText(y_title)

    def set_empty_text(self, text: str) -> None:
        """Replace the default empty-state caption -- a caller stacking
        several of these panels names each panel's own missing array, so an
        empty panel never reads as "no comparison at all"."""
        if not self.available:
            return
        self._empty.setText(text)

    def set_series(
        self,
        series_id: str,
        points: list[tuple[float, float]],
        color: str,
        width: float = 2.0,
        name: str | None = None,
    ) -> None:
        """Add, or replace, the curve for *series_id*.

        *points* must already be ``x``-sorted -- this widget draws exactly
        what it is given, the same contract ``TablePreview`` has. *name* is
        the hover readout's own label for this curve (e.g. the run's display
        title); it defaults to *series_id* itself, which is readable enough
        for callers that never pass one (the existing tests).
        """
        if not self.available:
            return
        self._remove(series_id)
        line = QLineSeries()
        pen = QPen(QColor(color))
        pen.setWidthF(width)
        pen.setCapStyle(Qt.RoundCap)
        line.setPen(pen)
        for x, y in points:
            line.append(x, y)
        self._chart.addSeries(line)
        line.attachAxis(self._axis_x)
        line.attachAxis(self._axis_y)
        self._series[series_id] = line
        self._series_meta[series_id] = (name or series_id, color, tuple(points))
        self._refresh()

    def remove_series(self, series_id: str) -> None:
        if not self.available:
            return
        self._remove(series_id)
        self._refresh()

    def clear(self) -> None:
        if not self.available:
            return
        for series_id in list(self._series):
            self._remove(series_id)
        self._refresh()

    # ------------------------------------------------------------------
    def _remove(self, series_id: str) -> None:
        line = self._series.pop(series_id, None)
        if line is not None:
            self._chart.removeSeries(line)
        self._series_meta.pop(series_id, None)

    def _sync_readout_series(self) -> None:
        """Feed the hover view's cache from ``_series_meta`` -- called on
        every add/remove, never on a mouse move (see
        ``ReadoutChartView.set_readout_series``). Every curve here is always
        visible: this widget has no legend-toggle to hide one."""
        self._view.set_readout_series(
            [(name, colour, points, True) for name, colour, points in self._series_meta.values()]
        )

    def _refresh(self) -> None:
        self._sync_readout_series()
        # "Empty" means no *points* across every series, not merely "no
        # series" -- a series can legitimately be added with zero points
        # (e.g. a live draft column with no values typed yet), and min()/
        # max() below would otherwise raise on an empty sequence.
        points = [(p.x(), p.y()) for line in self._series.values() for p in line.points()]
        empty = not points
        self._show_empty(empty)
        if empty:
            return
        xs = [x for x, _ in points]
        ys = [y for _, y in points]
        fit_axis(self._axis_x, min(xs), max(xs))
        fit_axis(
            self._axis_y, min(ys), max(ys), tick_count=tick_count_for_height(self._view.height())
        )

    def _show_empty(self, empty: bool) -> None:
        self._view.setVisible(not empty)
        self._empty.setVisible(empty)
