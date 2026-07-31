"""``TablePreview``: a live plot of the value a grid is editing.

For an ``InterpolatedTable`` the plotted line *is* the value -- the table
defines a function by linear interpolation between its points, so straight
segments through the points show exactly the function being typed. A mistyped
``y`` spikes the line immediately. This is a rendering of the input, not
analysis, which is why it lives in the editor.

For a one-column ``SERIES`` there is no independent x, so values are plotted
against row number -- a quick look at the column that catches gross outliers.
The meaningful view (value versus the sibling ``Time`` column) needs data this
card does not yet have, and is deferred.

**Import-guarded.** ``PySide6.QtCharts`` ships with PySide6 but a few minimal
builds omit it. If it cannot be imported the preview quietly disables itself
(``available`` is False) and the grid works exactly as before -- a plot is an
enhancement, never a dependency of editing.

**Only numeric points are plotted.** A cell holding ``oops`` or ``None`` has no
position on an axis; such rows are skipped, never coerced to zero. The grid and
the validator remain the source of truth for those; the plot just shows what
can be shown.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QLabel, QVBoxLayout, QWidget

from ..style import ACCENT
from .chart_axes import fit_axis, style_axis

try:  # QtCharts is part of PySide6 but absent from some minimal builds.
    from PySide6.QtCharts import (
        QChart,
        QChartView,
        QLineSeries,
        QScatterSeries,
        QValueAxis,
    )

    _CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the PySide6 build
    _CHARTS_AVAILABLE = False

_LINE = ACCENT


def charts_available() -> bool:
    """Whether QtCharts could be imported in this build."""
    return _CHARTS_AVAILABLE


class TablePreview(QWidget):
    """A compact live chart of a grid's numeric points.

    ``mode="xy"`` plots column 1 against column 0 (an interpolated table);
    ``mode="series"`` plots the single column against row number.
    """

    def __init__(self, mode: str = "xy", height: int = 140, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._mode = mode
        self.available = _CHARTS_AVAILABLE
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        if not _CHARTS_AVAILABLE:
            # No chart, no gap: the widget simply contributes nothing.
            self.setVisible(False)
            return

        self._chart = QChart()
        self._chart.legend().hide()
        self._chart.setBackgroundVisible(False)
        self._chart.setMargins(_zero_margins())

        self._line = QLineSeries()
        pen = QPen(QColor(_LINE))
        pen.setWidth(2)
        self._line.setPen(pen)
        self._dots = QScatterSeries()
        self._dots.setMarkerSize(7.0)
        self._dots.setColor(QColor(_LINE))
        self._dots.setBorderColor(QColor("#ffffff"))
        self._chart.addSeries(self._line)
        self._chart.addSeries(self._dots)

        self._axis_x = QValueAxis()
        self._axis_y = QValueAxis()
        for axis in (self._axis_x, self._axis_y):
            style_axis(axis)
        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)
        for series in (self._line, self._dots):
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_y)

        self._view = QChartView(self._chart)
        self._view.setRenderHint(QPainter.Antialiasing)
        # Drop QGraphicsView's native sunken frame: the chart sits inside a
        # card that already owns the border, matching the app's flat look.
        self._view.setFrameShape(QFrame.NoFrame)
        self._view.setFixedHeight(height)
        layout.addWidget(self._view)

        self._empty = QLabel("No numeric points to plot yet.")
        self._empty.setObjectName("Hint")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setFixedHeight(height)
        layout.addWidget(self._empty)
        self._show_empty(True)

    def set_axis_titles(self, x_title: str, y_title: str) -> None:
        if not self.available:
            return
        self._axis_x.setTitleText(x_title)
        self._axis_y.setTitleText(y_title)

    def update_rows(self, rows: list[list[object]]) -> None:
        """Replot from the grid's current rows. Non-numeric cells are skipped."""
        if not self.available:
            return
        points = self._points(rows)
        self._line.clear()
        self._dots.clear()
        if not points:
            self._show_empty(True)
            return
        self._show_empty(False)
        for x, y in points:
            self._line.append(x, y)
            self._dots.append(x, y)
        self._fit_axes(points)

    # ------------------------------------------------------------------
    def _points(self, rows: list[list[object]]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        if self._mode == "series":
            for index, row in enumerate(rows):
                y = _as_number(row[0]) if row else None
                if y is not None:
                    points.append((float(index), y))
        else:  # xy
            for row in rows:
                if len(row) < 2:
                    continue
                x, y = _as_number(row[0]), _as_number(row[1])
                if x is not None and y is not None:
                    points.append((x, y))
            points.sort(key=lambda p: p[0])  # a line reads left-to-right
        return points

    def _fit_axes(self, points: list[tuple[float, float]]) -> None:
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        fit_axis(self._axis_x, min(xs), max(xs))
        fit_axis(self._axis_y, min(ys), max(ys))

    def _show_empty(self, empty: bool) -> None:
        self._view.setVisible(not empty)
        self._empty.setVisible(empty)


def _as_number(value: object) -> float | None:
    """A plottable float, or ``None`` for a string/blank/bool cell."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _zero_margins():
    from PySide6.QtCore import QMargins

    return QMargins(0, 0, 0, 0)
