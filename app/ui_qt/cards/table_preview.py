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

**Only numeric points are plotted.** Non-numeric, blank or non-finite cells
are skipped rather than coerced (``chart_axes.as_plot_number``) -- the grid
and the validator remain the source of truth for those; the plot just shows
what can be shown.

**Reference overlay.** ``set_reference_rows`` (``mode="xy"`` only) draws a
docked reference's own table as a second series -- a dashed reference-purple
line, no scatter markers of its own, so it never competes with the draft's
solid accent line + dots. A small legend appears above the chart only while
an overlay is present. Independent of ``update_rows``: the main draft can
keep changing while the overlay stays put until ``set_reference_rows`` is
called again (or with ``None``, to clear it).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ..style import ACCENT, MUTED, REFERENCE
from .chart_axes import (
    as_plot_number,
    fit_axis,
    setup_chart,
    setup_chart_view,
    style_axis,
)

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

        #: The main draft's own points, and a docked reference's overlay
        #: points -- kept separate so either can be replotted without
        #: disturbing the other (see ``update_rows``/``set_reference_rows``).
        self._main_points: list[tuple[float, float]] = []
        self._ref_points: list[tuple[float, float]] = []

        self._legend = _legend_row()
        self._legend.hide()
        layout.addWidget(self._legend)

        self._chart = QChart()
        setup_chart(self._chart)

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

        # The reference overlay: a dashed purple line only, no markers of its
        # own -- it reads as "the other file's curve", not a second set of
        # editable points.
        self._ref_line = QLineSeries()
        ref_pen = QPen(QColor(REFERENCE))
        ref_pen.setWidthF(1.9)
        ref_pen.setStyle(Qt.DashLine)
        self._ref_line.setPen(ref_pen)
        self._chart.addSeries(self._ref_line)

        self._axis_x = QValueAxis()
        self._axis_y = QValueAxis()
        for axis in (self._axis_x, self._axis_y):
            style_axis(axis)
        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)
        for series in (self._line, self._dots, self._ref_line):
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_y)

        self._view = QChartView(self._chart)
        setup_chart_view(self._view, height)
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
        """Replot the main draft from the grid's current rows.

        Non-numeric cells are skipped. Never touches the reference overlay --
        set independently by :meth:`set_reference_rows` -- so the draft can
        keep changing while a docked reference's curve stays put.
        """
        if not self.available:
            return
        self._main_points = self._points(rows)
        self._redraw()

    def set_reference_rows(self, rows: list[list[object]] | None) -> None:
        """Overlay *rows* -- a differing reference table's own ``(x, y)``
        pairs -- as the dashed purple series, or clear it with ``None``.

        Shows/hides the small legend alongside: present only while an
        overlay is actually drawn, since the plain solid line already speaks
        for itself with nothing to distinguish it from.
        """
        if not self.available:
            return
        self._ref_points = self._points(rows) if rows else []
        self._legend.setVisible(bool(self._ref_points))
        self._redraw()

    def _redraw(self) -> None:
        self._line.clear()
        self._dots.clear()
        for x, y in self._main_points:
            self._line.append(x, y)
            self._dots.append(x, y)
        self._ref_line.clear()
        for x, y in self._ref_points:
            self._ref_line.append(x, y)
        all_points = self._main_points + self._ref_points
        if not all_points:
            self._show_empty(True)
            return
        self._show_empty(False)
        self._fit_axes(all_points)

    # ------------------------------------------------------------------
    def _points(self, rows: list[list[object]]) -> list[tuple[float, float]]:
        points: list[tuple[float, float]] = []
        if self._mode == "series":
            for index, row in enumerate(rows):
                y = as_plot_number(row[0]) if row else None
                if y is not None:
                    points.append((float(index), y))
        else:  # xy
            for row in rows:
                if len(row) < 2:
                    continue
                x, y = as_plot_number(row[0]), as_plot_number(row[1])
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


# ----------------------------------------------------------------------
# reference-overlay legend
# ----------------------------------------------------------------------


def _legend_row() -> QWidget:
    """"Main"/"Reference" swatches shown above the chart while an overlay is
    present -- plain labels, no circled marks (the app's dot-language rules
    ban those), just the same solid-vs-dashed distinction the two lines
    themselves draw."""
    row = QWidget()
    row.setObjectName("ChartLegend")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 0, 0, 4)
    layout.setSpacing(4)
    layout.addWidget(_legend_swatch(_LINE, dashed=False))
    layout.addWidget(_legend_label("Main"))
    layout.addSpacing(10)
    layout.addWidget(_legend_swatch(REFERENCE, dashed=True))
    layout.addWidget(_legend_label("Reference"))
    layout.addStretch(1)
    return row


def _legend_swatch(color: str, *, dashed: bool) -> QLabel:
    swatch = QLabel()
    swatch.setFixedSize(14, 10)
    border_style = "dashed" if dashed else "solid"
    swatch.setStyleSheet(f"border-top: 2px {border_style} {color}; margin-top: 4px;")
    return swatch


def _legend_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED}; font-size: 11px;")
    return label
