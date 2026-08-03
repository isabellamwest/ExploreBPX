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

from .chart_axes import fit_axis, setup_chart, setup_chart_view, style_axis

try:  # QtCharts is part of PySide6 but absent from some minimal builds.
    from PySide6.QtCharts import QChart, QChartView, QLineSeries, QValueAxis

    _CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the PySide6 build
    _CHARTS_AVAILABLE = False


def charts_available() -> bool:
    """Whether QtCharts could be imported in this build."""
    return _CHARTS_AVAILABLE


class MultiSeriesChart(QWidget):
    """A small multiple: several ``(x, y)`` curves sharing one axis pair."""

    def __init__(self, height: int = 100, parent: QWidget | None = None) -> None:
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
            style_axis(axis)
        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)

        self._view = QChartView(self._chart)
        setup_chart_view(self._view, height)
        layout.addWidget(self._view)

        self._empty = QLabel("No comparison data yet.")
        self._empty.setObjectName("Hint")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setFixedHeight(height)
        layout.addWidget(self._empty)

        self._series: dict[str, QLineSeries] = {}
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
    ) -> None:
        """Add, or replace, the curve for *series_id*.

        *points* must already be ``x``-sorted -- this widget draws exactly
        what it is given, the same contract ``TablePreview`` has.
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

    def _refresh(self) -> None:
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
        fit_axis(self._axis_y, min(ys), max(ys))

    def _show_empty(self, empty: bool) -> None:
        self._view.setVisible(not empty)
        self._empty.setVisible(empty)
