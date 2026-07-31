"""Shared axis cosmetics for the app's two QtCharts widgets.

``TablePreview`` and ``MultiSeriesChart`` are deliberately independent,
import-guarded widgets, but their axes must not drift apart -- they once used
two different "muted" greys for the same tick-label role. This module is
QtCharts-free (it only sets fonts, colours and label format on whatever axis
it is handed), so both widgets share it without weakening their own import
guards.
"""

from __future__ import annotations

from PySide6.QtGui import QBrush, QColor, QFont

from ..style import CHART_GRID, MUTED


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
