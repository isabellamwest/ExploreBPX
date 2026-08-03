"""Shared chart conventions for the app's two QtCharts widgets.

``TablePreview`` and ``MultiSeriesChart`` are independent, import-guarded
widgets that must still look identical and judge numbers the same way, so
their shared chart/view/axis setup and numeric-cell filtering live here
instead of being duplicated in both. QtCharts-free itself, so both widgets
can share it without weakening their own import guards.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QMargins
from PySide6.QtGui import QBrush, QColor, QFont, QPainter
from PySide6.QtWidgets import QFrame

from ..style import CHART_GRID, MUTED


def as_plot_number(value: object) -> float | None:
    """A plottable float, or ``None`` for a string/blank/bool/non-finite cell.

    The single definition of "what may be plotted": a cell holding ``oops``
    or ``None`` has no position on an axis, and a non-finite ``nan``/``inf``
    (which the lenient parser lets through as a float) would desync the axis
    fit from the drawn line -- QtCharts refuses the point anyway. Skipped,
    never coerced: the grid and the validator remain the only places a bad
    cell is ever flagged.
    """
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)) and math.isfinite(value):
        return float(value)
    return None


def setup_chart(chart) -> None:
    """The app's ``QChart`` baseline: no built-in legend (each widget's host
    already labels the data -- the grid header, or the dialog's removable
    chips), no background, no margins."""
    chart.legend().setVisible(False)
    chart.setBackgroundVisible(False)
    chart.setMargins(QMargins(0, 0, 0, 0))


def setup_chart_view(view, height: int) -> None:
    """The app's ``QChartView`` baseline: antialiased, fixed-height, and
    without QGraphicsView's native sunken frame -- the chart sits inside a
    card that already owns the border, matching the app's flat look."""
    view.setRenderHint(QPainter.Antialiasing)
    view.setFrameShape(QFrame.NoFrame)
    view.setFixedHeight(height)


def style_axis(axis) -> None:
    """Apply the app's axis look to a ``QValueAxis``.

    Tick labels and titles use the app's small-label vocabulary (11px, muted
    grey -- the same treatment as ``QLabel#Hint`` and the Source page's field
    labels) instead of QtCharts' own defaults, so chart text reads as part of
    the surrounding card. ``%g`` keeps tick labels compact for both the tiny
    magnitudes BPX tables hold (diffusivities near 1e-14) and plain ranges.
    """
    axis.setGridLineColor(QColor(CHART_GRID))
    axis.setLabelsColor(QColor(MUTED))
    labels_font = QFont()
    labels_font.setPixelSize(11)
    axis.setLabelsFont(labels_font)
    title_font = QFont()
    title_font.setPixelSize(11)
    title_font.setWeight(QFont.DemiBold)
    axis.setTitleFont(title_font)
    axis.setTitleBrush(QBrush(QColor(MUTED)))
    axis.setLabelFormat("%g")


def fit_axis(axis, low: float, high: float) -> None:
    """Set *axis* to the data range, snapped outward to round tick values.

    ``applyNiceNumbers`` provides the headroom: it rounds both ends out to
    the tick grid. Padding *before* the snap backfires -- a percentage pad
    below a 0-anchored time axis gets rounded a full tick interval further
    down, wasting a band of the plot on empty space. Coincident points (a
    single row, or a constant series) have no span to snap, so they get an
    explicit pad first.
    """
    if low == high:
        pad = abs(low) * 0.1 or 1.0
        low, high = low - pad, high + pad
    axis.setRange(low, high)
    axis.applyNiceNumbers()
