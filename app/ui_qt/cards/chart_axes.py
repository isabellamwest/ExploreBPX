"""Shared chart conventions for the app's two QtCharts widgets.

``TablePreview`` and ``MultiSeriesChart`` are independent, import-guarded
widgets that must still look identical and judge numbers the same way, so
their shared chart/view/axis setup, numeric-cell filtering and hover-readout
hit-testing live here instead of being duplicated in both.

Importable with or without QtCharts: everything except
:class:`ReadoutChartView` is plain Qt/duck-typed, and that one class is
itself guarded behind its own ``try/except`` (mirroring each widget's own
guard) so this module never breaks a widget's graceful no-QtCharts
degradation just by being imported.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QMargins, QPointF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QFrame, QGraphicsEllipseItem, QToolTip

from ui_qt import typography
from ui_qt.style import BORDER, CHART_GRID, MUTED

if TYPE_CHECKING:
    from collections.abc import Sequence

try:  # Mirrors each chart widget's own QtCharts import guard -- see above.
    from PySide6.QtCharts import QChartView

    _CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the PySide6 build
    _CHARTS_AVAILABLE = False


def charts_available() -> bool:
    """Whether QtCharts could be imported in this build -- the same guard
    ``table_preview``/``multi_series_chart`` each expose for their own flag,
    mirrored here for :class:`ReadoutChartView`."""
    return _CHARTS_AVAILABLE


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


def series_pairs(x_values: Sequence[object] | None, y_values: Sequence[object] | None) -> list[tuple[float, float]]:
    """Numeric ``(x, y)`` pairs from two raw columns, paired index by index
    up to the shorter column, x-sorted, with non-plottable cells dropped
    (:func:`as_plot_number`) -- the one pairing contract every chart fed
    from raw Validation arrays uses (the compare dialog and the experiment
    card's preview band alike). Never a judgement: the grid and the
    validator remain the only places a bad cell is flagged."""
    pairs = []
    for x, y in zip(x_values or [], y_values or [], strict=False):
        px, py = as_plot_number(x), as_plot_number(y)
        if px is not None and py is not None:
            pairs.append((px, py))
    pairs.sort(key=lambda point: point[0])
    return pairs


def setup_chart(chart) -> None:
    """The app's ``QChart`` baseline: no built-in legend (each widget's host
    already labels the data -- the grid header, or the dialog's removable
    chips), no background, no margins, and a hairline box around the plot
    area.

    The box is the classic framed scientific plot: a single ``BORDER``
    rectangle enclosing exactly the data region, drawn by the chart itself
    (transparent plot-area brush, pen only). The axes' own edge lines are
    switched off in :func:`style_axis` so the frame is drawn once, not
    doubled along the left and bottom edges.
    """
    chart.legend().setVisible(False)
    chart.setBackgroundVisible(False)
    chart.setMargins(QMargins(0, 0, 0, 0))
    chart.setPlotAreaBackgroundBrush(QBrush(Qt.NoBrush))
    chart.setPlotAreaBackgroundPen(QPen(QColor(BORDER), 1))
    chart.setPlotAreaBackgroundVisible(True)


#: The tallest a responsive chart view may grow (see ``setup_chart_view``)
#: absent a caller-supplied *ceiling*. Chosen so the Inspector's now-960px
#: page measure (``style.PAGE_MEASURE``, minus ``cards/page.py``'s gutters --
#: 928px of actual content width) renders a chart around this tall, instead
#: of the old flat 140/180px band that left ~500px of dead space beside it.
CHART_HEIGHT_CEILING = 280

#: Height grows slower than width, so a wide chart does not become a
#: near-square block. Picked so the *old* fixed heights read as this rule's
#: own floor rather than an arbitrary slope: at the pre-fix 528px content
#: width this lands within a pixel of TablePreview's old 140px band; at the
#: 928px Inspector content width it reaches :data:`CHART_HEIGHT_CEILING`.
_HEIGHT_WIDTH_RATIO = 3.2


def responsive_chart_height(width: int, floor: int, ceiling: int) -> int:
    """The chart height for a view *width* pixels wide: ``round(width /
    3.2)``, clamped to never drop below *floor* (the shortest the caller
    judged legible for a compact card) or rise above *ceiling*. Pure, so the
    clamping arithmetic is unit-testable without a live chart -- see
    ``ReadoutChartView`` for where this actually drives a widget's height."""
    return min(ceiling, max(floor, round(width / _HEIGHT_WIDTH_RATIO)))


def setup_chart_view(view, height: int, *, ceiling: int = CHART_HEIGHT_CEILING) -> None:
    """The app's ``QChartView`` baseline: antialiased, without
    QGraphicsView's native sunken frame (the chart sits inside a card that
    already owns the border, matching the app's flat look), and a *width-
    responsive* height rather than one flat value.

    *height* is the floor -- the shortest the chart may ever be, the same
    number every caller already passed in when this was a flat
    ``setFixedHeight`` (140 for ``TablePreview``, 180 for
    ``MultiSeriesChart``). *ceiling* caps how tall it may grow as its
    containing column widens, defaulting to :data:`CHART_HEIGHT_CEILING`;
    the database-examples Compare dialog passes a lower one so its three
    stacked charts cannot outgrow the dialog. Recomputed on every resize
    (``ReadoutChartView.resizeEvent``) from the view's own current width --
    see :func:`responsive_chart_height` for the formula, and
    :func:`tick_count_for_height` for how the y axis' tick count follows the
    same height.
    """
    view.setRenderHint(QPainter.Antialiasing)
    view.setFrameShape(QFrame.NoFrame)
    view.set_height_range(height, ceiling)


def style_axis(axis, widget_font: QFont) -> None:
    """Apply the app's axis look to a ``QValueAxis``.

    Tick labels and titles use the app's small-label vocabulary (11px, muted
    grey -- the same treatment as ``QLabel#Hint`` and the Source page's field
    labels) instead of QtCharts' own defaults, so chart text reads as part of
    the surrounding card. ``%g`` keeps tick labels compact for both the tiny
    magnitudes BPX tables hold (diffusivities near 1e-14) and plain ranges.

    *widget_font* is the owning widget's font -- a bare ``QFont()`` takes the
    *application* default rather than the widget's, so axis fonts built from
    it could silently drift from the rest of the UI.

    The axis' own edge line is off: the plot area's hairline frame (see
    :func:`setup_chart`) already draws all four edges, and a second, darker
    QtCharts default line under two of them read as a smudge. Grid lines are
    set visible explicitly -- they are the frame's interior and the reason a
    value can be traced to a tick without a ruler.
    """
    axis.setLineVisible(False)
    axis.setGridLineVisible(True)
    axis.setGridLineColor(QColor(CHART_GRID))
    axis.setLabelsColor(QColor(MUTED))
    labels_font = typography.sized(widget_font, typography.META)
    axis.setLabelsFont(labels_font)
    title_font = typography.semibold(typography.sized(widget_font, typography.META))
    axis.setTitleFont(title_font)
    axis.setTitleBrush(QBrush(QColor(MUTED)))
    axis.setLabelFormat("%g")


#: The y axis's tick count, forced after ``applyNiceNumbers`` on every fit
#: (see ``fit_axis``). QtCharts' own default (``applyNiceNumbers`` picks
#: whatever count it judges "nice" for the range, commonly 4-6) crowds tick
#: labels closely enough at a compact chart height that QtCharts silently
#: elides *every* one of them to "..." rather than letting any overlap --
#: measured on ``TablePreview`` at its 140px height: tick marks and
#: gridlines still draw, but not one numeral does, which reads as "no
#: labels" rather than "elided".
#:
#: Three (the axis ends plus one midpoint) rather than four: this override
#: runs *after* nice-numbers has already picked its own round bounds (see
#: ``fit_axis``), so raising the count only re-subdivides that same range --
#: halving it (3 ticks) overwhelmingly lands on another round number, while
#: thirding it (4 ticks) does not. Measured against every bundled example
#: run's Voltage/Current/Temperature range plus chen2020's own OCP table (21
#: real ranges): 3 ticks read clean on all 21; 4 ticks produced a repeating
#: decimal (e.g. "3.16667") on 16 of them. The x axis is untouched -- its
#: labels run along the chart's full width, never tight enough to collide.
Y_AXIS_TICK_COUNT = 3

#: One step up from :data:`Y_AXIS_TICK_COUNT`, for a chart tall enough to
#: give the extra label room -- see :func:`tick_count_for_height`.
#:
#: Deliberately not 4. The comment above explains *why* 3 (halving a nice
#: span) reads clean while 4 (thirding it) does not; the same reasoning
#: makes 5 (quartering it -- two clean halvings) the next safe count, not
#: the next integer. Re-measured with that hypothesis in mind, against the
#: same 21 ranges plus every bundled example run's Voltage/Current (15
#: ranges in total): tick_count=4 produced a repeating decimal on 12 of 15;
#: tick_count=5 produced not one -- matching tick_count=3's own zero. A
#: taller chart still earns real extra resolution, it just skips straight
#: past the one count that was never going to be clean.
TALL_Y_AXIS_TICK_COUNT = 5

#: The chart height, in pixels, above which :func:`tick_count_for_height`
#: switches from :data:`Y_AXIS_TICK_COUNT` to :data:`TALL_Y_AXIS_TICK_COUNT`.
_TALL_CHART_HEIGHT = 180


def tick_count_for_height(height: int) -> int:
    """The y-axis tick count for a chart *height* pixels tall (see
    :func:`setup_chart_view`): :data:`Y_AXIS_TICK_COUNT` at or below
    :data:`_TALL_CHART_HEIGHT` (unchanged from the fixed-height original --
    this is the height that measurement was made at),
    :data:`TALL_Y_AXIS_TICK_COUNT` above it. Never the count in between --
    see that constant's own comment for why 4 is skipped outright rather
    than merely deferred to a still-taller tier."""
    return TALL_Y_AXIS_TICK_COUNT if height > _TALL_CHART_HEIGHT else Y_AXIS_TICK_COUNT


def fit_axis(axis, low: float, high: float, *, tick_count: int | None = None) -> None:
    """Set *axis* to the data range, snapped outward to round tick values.

    ``applyNiceNumbers`` provides the headroom: it rounds both ends out to
    the tick grid. Padding *before* the snap backfires -- a percentage pad
    below a 0-anchored time axis gets rounded a full tick interval further
    down, wasting a band of the plot on empty space. Coincident points (a
    single row, or a constant series) have no span to snap, so they get an
    explicit pad first.

    *tick_count*, when given, is applied *after* ``applyNiceNumbers`` --
    measured, not assumed: ``applyNiceNumbers`` recomputes its own preferred
    tick count every time it runs, silently discarding any ``setTickCount``
    call made before it. Passed by the y axis call only (see
    :data:`Y_AXIS_TICK_COUNT`); the x axis keeps whatever count
    ``applyNiceNumbers`` itself chose.
    """
    if low == high:
        pad = abs(low) * 0.1 or 1.0
        low, high = low - pad, high + pad
    axis.setRange(low, high)
    axis.applyNiceNumbers()
    if tick_count is not None:
        axis.setTickCount(tick_count)


# ---------------------------------------------------------------------------
# Hover readout: nearest-point hit-testing, shared by both chart widgets.
# ---------------------------------------------------------------------------

#: How close the cursor must land to a sample point, in pixel space (via
#: ``QChart.mapToPosition``), to count as a hover hit. Loose enough to
#: forgive an imprecise hover, tight enough that two nearby points never
#: fight over the cursor.
READOUT_SNAP_RADIUS = 24.0

#: The hover marker's diameter -- the same ``QScatterSeries`` marker size
#: ``TablePreview``'s own draft dots use for a sparse series, so a snapped
#: point reads as the same mark, not a new visual language.
READOUT_MARKER_SIZE = 6.0


@dataclass(frozen=True)
class ReadoutPoint:
    """One hover hit: which series, and the sample point in both spaces."""

    series_name: str
    colour: str
    x: float
    y: float
    pixel_x: float
    pixel_y: float


@dataclass(frozen=True)
class ReadoutSeries:
    """One series' identity, visibility and points (already pixel-mapped),
    for a single hit-test call.

    ``visible=False`` for a legend-hidden reference curve -- carried through
    rather than simply left out of the list, so "a hidden curve is never
    hit" is a fact the hit-test function itself can be pinned against.
    """

    name: str
    colour: str
    #: ``(x, y, pixel_x, pixel_y)`` per point -- the data value alongside
    #: where it currently renders, so a hit reports both without a second
    #: lookup.
    points: tuple[tuple[float, float, float, float], ...]
    visible: bool = True


def nearest_readout_point(
    series: Sequence[ReadoutSeries], cursor_x: float, cursor_y: float, radius: float
) -> ReadoutPoint | None:
    """The closest sample point to (*cursor_x*, *cursor_y*) in pixel space,
    among every *visible* series, within *radius* pixels -- or ``None`` on a
    miss.

    Pure: every input is already plain numbers, with points pre-mapped to
    pixel space by the caller, so this needs no live chart or QtCharts
    series and is trivially unit-testable headless. Compares squared
    distance (no ``sqrt`` needed against a squared radius); a tie keeps
    whichever series was listed first.
    """
    best: ReadoutPoint | None = None
    best_dist2 = radius * radius
    for entry in series:
        if not entry.visible:
            continue
        for x, y, pixel_x, pixel_y in entry.points:
            dist2 = (pixel_x - cursor_x) ** 2 + (pixel_y - cursor_y) ** 2
            if dist2 <= best_dist2:
                best_dist2 = dist2
                best = ReadoutPoint(entry.name, entry.colour, x, y, pixel_x, pixel_y)
    return best


def format_readout_number(value: float) -> str:
    """Compact, display-only rendering of one hover-readout coordinate: six
    significant figures, trailing zeros trimmed -- the same compactness
    ``style_axis``'s ``%g`` tick labels use, just sized for a hovered
    value's own precision rather than a rounded tick boundary."""
    return f"{value:.6g}"


def readout_tooltip_text(hit: ReadoutPoint, x_title: str, y_title: str, *, show_series_name: bool) -> str:
    """ "Chen2020 · Time [s] 50000 · Voltage [V] 3.94" -- the app's " · "
    separator throughout, never an em dash.

    *x_title*/*y_title* fall back to the bare axis letter when no title was
    set. *show_series_name* is the caller's own call (more than one series
    currently visible) -- this function only formats, it never counts.
    """
    x_text = f"{x_title or 'x'} {format_readout_number(hit.x)}"
    y_text = f"{y_title or 'y'} {format_readout_number(hit.y)}"
    parts = [hit.series_name, x_text, y_text] if show_series_name else [x_text, y_text]
    return " · ".join(parts)


def _to_pixel(chart, x: float, y: float) -> tuple[float, float]:
    point = chart.mapToPosition(QPointF(x, y))
    return point.x(), point.y()


if _CHARTS_AVAILABLE:

    class ReadoutChartView(QChartView):
        """A ``QChartView`` that shows the nearest sample point's coordinates
        as a hover readout: a ``QToolTip`` plus a small marker dot, whenever
        the cursor lands within :data:`READOUT_SNAP_RADIUS` pixels of a
        visible series' point. Both disappear on a miss or when the cursor
        leaves the chart.

        Series content is supplied separately (:meth:`set_readout_series`)
        as plain data, never read from the live ``QLineSeries`` /
        ``QScatterSeries`` on a mouse move -- that cache is what keeps
        hovering cheap over a several-hundred-point reference run.
        """

        def __init__(self, chart, axis_x, axis_y, parent=None) -> None:
            super().__init__(chart, parent)
            self._axis_x = axis_x
            self._axis_y = axis_y
            #: ``(name, colour, points, visible)`` per series -- data only,
            #: not yet mapped to pixel space (see :meth:`_update_readout`).
            self._series: list[tuple[str, str, tuple[tuple[float, float], ...], bool]] = []
            self.setMouseTracking(True)
            # Parented to the chart itself (a QGraphicsWidget already in the
            # view's scene), so its coordinates match mapToPosition's own
            # "position on the chart" space with no separate scene offset to
            # account for.
            self._marker = QGraphicsEllipseItem(chart)
            half = READOUT_MARKER_SIZE / 2
            self._marker.setRect(-half, -half, READOUT_MARKER_SIZE, READOUT_MARKER_SIZE)
            self._marker.setPen(QPen(QColor("#ffffff"), 1.5))
            self._marker.setZValue(1000)
            self._marker.hide()
            #: Width-responsive height range (see :func:`setup_chart_view`).
            #: ``None`` until :meth:`set_height_range` is called -- a view
            #: built and resized directly, as this class's own tests do,
            #: keeps whatever height its caller sets and this class never
            #: touches it.
            self._height_floor: int | None = None
            self._height_ceiling: int = CHART_HEIGHT_CEILING
            #: Re-entrancy guard: ``setFixedHeight`` below fires this same
            #: view's own ``resizeEvent`` (any geometry change does, not only
            #: a parent-layout-driven one), which must not itself recompute
            #: and fight the height just being applied.
            self._adjusting_height = False

        def set_readout_series(
            self,
            series: Sequence[tuple[str, str, Sequence[tuple[float, float]], bool]],
        ) -> None:
            """Replace the cached per-series data used for hover hit-testing.

            Call whenever a series' content *or* visibility changes -- a
            mouse move only ever reads this cache (see the class docstring).
            """
            self._series = [(name, colour, tuple(points), visible) for name, colour, points, visible in series]

        def set_height_range(self, floor: int, ceiling: int) -> None:
            """Turn on width-responsive height (see
            :func:`setup_chart_view`): never shorter than *floor*, never
            taller than *ceiling*.

            Starts pinned to *floor* rather than computed from the view's
            current width: a freshly constructed, not-yet-laid-out widget's
            width is Qt's own un-managed default (measured: 640px), not the
            real space a parent layout will eventually give it, so reading
            it here would size the chart from an accident of construction
            order rather than its actual home. It grows on the first
            genuine resize once a parent layout assigns real width (see
            :meth:`resizeEvent`).
            """
            self._height_floor = floor
            self._height_ceiling = ceiling
            self._adjusting_height = True
            self.setFixedHeight(floor)
            self._adjusting_height = False

        def resizeEvent(self, event) -> None:
            super().resizeEvent(event)
            if self._adjusting_height:
                return
            self._apply_responsive_height(event.size().width())

        def _apply_responsive_height(self, width: int) -> None:
            if self._height_floor is None:
                return
            target = responsive_chart_height(width, self._height_floor, self._height_ceiling)
            if target == self.height():
                return
            self._adjusting_height = True
            self.setFixedHeight(target)
            self._adjusting_height = False
            # The y axis' own tick count tracks the same height (see
            # tick_count_for_height) so a resize alone -- no new data --
            # still re-subdivides an already-fitted range correctly. Safe
            # without re-running applyNiceNumbers: fit_axis's own docstring
            # notes that only applyNiceNumbers discards a tick count set
            # after it, and nothing here calls it again.
            self._axis_y.setTickCount(tick_count_for_height(target))

        def mouseMoveEvent(self, event) -> None:
            super().mouseMoveEvent(event)
            pos = event.position()
            self._update_readout(pos.x(), pos.y(), event.globalPosition().toPoint())

        def leaveEvent(self, event) -> None:
            super().leaveEvent(event)
            self._hide_readout()

        def _update_readout(self, cursor_x: float, cursor_y: float, global_pos) -> None:
            chart = self.chart()
            mapped = [
                ReadoutSeries(
                    name,
                    colour,
                    tuple((x, y, *_to_pixel(chart, x, y)) for x, y in points),
                    visible,
                )
                for name, colour, points, visible in self._series
            ]
            hit = nearest_readout_point(mapped, cursor_x, cursor_y, READOUT_SNAP_RADIUS)
            if hit is None:
                self._hide_readout()
                return
            visible_count = sum(1 for *_rest, visible in self._series if visible)
            text = readout_tooltip_text(
                hit,
                self._axis_x.titleText(),
                self._axis_y.titleText(),
                show_series_name=visible_count > 1,
            )
            self._marker.setBrush(QBrush(QColor(hit.colour)))
            self._marker.setPos(hit.pixel_x, hit.pixel_y)
            self._marker.show()
            QToolTip.showText(global_pos, text, self)

        def _hide_readout(self) -> None:
            self._marker.hide()
            QToolTip.hideText()
