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

**Reference overlay.** ``set_reference_curves`` (``mode="xy"`` only) draws
one line per pinned reference that has this key, each in its own badge
colour, thinner than the draft's own solid accent line + dots so none of
them competes with it. A legend appears above the chart only while an
overlay is present: a "Main" swatch, then one badge per curve. Clicking a
badge toggles its curve; hovering one gives that reference's name, domain
and point count.

**No extrapolation, ever.** Each curve is drawn from that reference's own
points and stops at its own domain edge -- points are never merged across
references and no curve is extended to meet another's range. A curve that
ends early simply ends; its legend badge's tooltip says where.

Independent of ``update_rows``: the main draft can keep changing while the
overlay stays put until ``set_reference_curves`` is called again (or with an
empty list, to clear it).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui_qt import badges, typography
from ui_qt.style import ACCENT, MUTED

from .chart_axes import (
    as_plot_number,
    fit_axis,
    setup_chart,
    setup_chart_view,
    style_axis,
    tick_count_for_height,
)

try:  # QtCharts is part of PySide6 but absent from some minimal builds.
    from PySide6.QtCharts import (
        QChart,
        QLineSeries,
        QScatterSeries,
        QValueAxis,
    )

    # Only defined in chart_axes when QtCharts itself imported cleanly there
    # too (same guard, same process) -- see ReadoutChartView's own docstring.
    from .chart_axes import ReadoutChartView

    _CHARTS_AVAILABLE = True
except ImportError:  # pragma: no cover - depends on the PySide6 build
    _CHARTS_AVAILABLE = False

_LINE = ACCENT

#: Reference curves are drawn thinner than the draft's own 2px line: the
#: value being edited stays the loudest thing on the chart however many
#: references are overlaid on it.
_REF_LINE_WIDTH = 1.6

#: Above this many main-series points, the draft dots read as a fat,
#: cluttered band rather than individual points (a 98-point OCP table drew
#: 98 overlapping 7px circles on top of its own line) -- past the
#: threshold the line alone carries the shape; the hover readout
#: (``ReadoutChartView``) still gives any single point's value on demand.
_MAX_SCATTER_POINTS = 48


def charts_available() -> bool:
    """Whether QtCharts could be imported in this build."""
    return _CHARTS_AVAILABLE


@dataclass(frozen=True)
class ReferenceCurve:
    """One pinned reference's overlay: its badge identity and its own rows.

    Deliberately not a ``ReferencePin`` -- the chart paints badges and
    labels, and has no business knowing about comparisons or snapshots. The
    card that owns both does the translation.
    """

    letters: str
    colour: str
    name: str
    rows: list[list[object]] = field(default_factory=list)


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

        #: The main draft's own points, and one point list per overlaid
        #: reference curve -- kept separate so either can be replotted
        #: without disturbing the other (see ``update_rows`` /
        #: ``set_reference_curves``).
        self._main_points: list[tuple[float, float]] = []
        self._curves: list[ReferenceCurve] = []
        self._curve_points: list[list[tuple[float, float]]] = []
        #: Per-curve visibility, driven by the legend badges. A hidden curve
        #: keeps its place in the list (and its badge) -- it is switched off,
        #: not removed.
        self._curve_shown: list[bool] = []
        self._ref_series: list[QLineSeries] = []

        self._legend = _LegendRow()
        self._legend.curve_toggled.connect(self._on_curve_toggled)
        self._legend.hide()
        layout.addWidget(self._legend)

        self._chart = QChart()
        setup_chart(self._chart)

        self._line = QLineSeries()
        pen = QPen(QColor(_LINE))
        pen.setWidth(2)
        self._line.setPen(pen)
        self._dots = QScatterSeries()
        self._dots.setMarkerSize(6.0)
        self._dots.setColor(QColor(_LINE))
        self._dots.setBorderColor(QColor("#ffffff"))
        self._chart.addSeries(self._line)
        self._chart.addSeries(self._dots)

        self._axis_x = QValueAxis()
        self._axis_y = QValueAxis()
        for axis in (self._axis_x, self._axis_y):
            style_axis(axis, self.font())
        self._chart.addAxis(self._axis_x, Qt.AlignBottom)
        self._chart.addAxis(self._axis_y, Qt.AlignLeft)
        for series in (self._line, self._dots):
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_y)

        self._view = ReadoutChartView(self._chart, self._axis_x, self._axis_y)
        setup_chart_view(self._view, height)
        layout.addWidget(self._view)

        self._empty = QLabel("No numeric points to plot yet.")
        self._empty.setObjectName("Hint")
        self._empty.setAlignment(Qt.AlignCenter)
        self._empty.setWordWrap(True)
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

    def set_reference_curves(self, curves: list[ReferenceCurve]) -> None:
        """Overlay one line per pinned reference that has this key, each in
        its own badge colour. An empty list clears the overlay.

        Shows/hides the legend alongside: present only while an overlay is
        actually drawn, since the plain solid line speaks for itself with
        nothing to distinguish it from. Rebuilds the series wholesale --
        badge identity comes from pin order, so a removed reference must not
        leave a curve behind wearing a colour that has moved on.
        """
        if not self.available:
            return
        self._curves = list(curves)
        self._curve_points = [self._points(curve.rows) for curve in self._curves]
        self._curve_shown = [True] * len(self._curves)
        self._rebuild_reference_series()
        self._legend.set_curves(
            [(curve, _domain_text(points)) for curve, points in zip(self._curves, self._curve_points, strict=False)]
        )
        self._legend.setVisible(bool(self._curves))
        self._redraw()

    def _rebuild_reference_series(self) -> None:
        """One ``QLineSeries`` per curve, in badge colour. Torn down and
        rebuilt rather than reused: the count changes with the pin list."""
        for series in self._ref_series:
            self._chart.removeSeries(series)
        self._ref_series = []
        for curve in self._curves:
            series = QLineSeries()
            pen = QPen(QColor(curve.colour))
            pen.setWidthF(_REF_LINE_WIDTH)
            series.setPen(pen)
            self._chart.addSeries(series)
            series.attachAxis(self._axis_x)
            series.attachAxis(self._axis_y)
            self._ref_series.append(series)

    def _on_curve_toggled(self, index: int, shown: bool) -> None:
        """A legend badge was clicked. Hiding a curve leaves the axes alone:
        the plot must not jump under the cursor as curves are switched off
        to read one of them."""
        if 0 <= index < len(self._curve_shown):
            self._curve_shown[index] = shown
            self._ref_series[index].setVisible(shown)
            # Visibility alone (no content change) still gates hover
            # hit-testing: a just-hidden curve must stop being hit at once.
            self._sync_readout_series()

    def _redraw(self) -> None:
        self._line.clear()
        self._dots.clear()
        # Dense data: line only (see _MAX_SCATTER_POINTS) -- the series
        # stays empty and hidden rather than populated-but-invisible, so it
        # costs nothing to keep around for the sparse case that follows.
        show_dots = len(self._main_points) <= _MAX_SCATTER_POINTS
        self._dots.setVisible(show_dots)
        for x, y in self._main_points:
            self._line.append(x, y)
            if show_dots:
                self._dots.append(x, y)
        for series, points, shown in zip(self._ref_series, self._curve_points, self._curve_shown, strict=False):
            series.clear()
            # Each curve holds only its own reference's points, so it stops
            # at that reference's own domain edge: nothing here extends or
            # merges a curve to meet another's range.
            for x, y in points:
                series.append(x, y)
            series.setVisible(shown)
        self._sync_readout_series()
        all_points = self._main_points + [point for points in self._curve_points for point in points]
        if not all_points:
            self._show_empty(True)
            return
        self._show_empty(False)
        self._fit_axes(all_points)

    def _sync_readout_series(self) -> None:
        """Feed the hover view's cache from the current draft + overlay --
        called on every content change and every legend toggle, never on a
        mouse move (see ``ReadoutChartView.set_readout_series``)."""
        series = [("Main", _LINE, self._main_points, True)]
        for curve, points, shown in zip(self._curves, self._curve_points, self._curve_shown, strict=False):
            series.append((curve.name, curve.colour, points, shown))
        self._view.set_readout_series(series)

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
        fit_axis(self._axis_y, min(ys), max(ys), tick_count=tick_count_for_height(self._view.height()))

    def _show_empty(self, empty: bool) -> None:
        self._view.setVisible(not empty)
        self._empty.setVisible(empty)


# ----------------------------------------------------------------------
# reference-overlay legend
# ----------------------------------------------------------------------


def _domain_text(points: list[tuple[float, float]]) -> str:
    """ "domain 0 – 0.8 · 41 points" -- the plain facts about one curve's own
    extent, for its legend badge's tooltip. This is where a curve that stops
    early says so; the chart itself carries no inline annotation."""
    if not points:
        return "no numeric points"
    xs = [x for x, _y in points]
    count = len(points)
    plural = "point" if count == 1 else "points"
    return f"domain {_number(min(xs))} – {_number(max(xs))} · {count} {plural}"


def _number(value: float) -> str:
    """A short, honest rendering of an axis bound -- trailing zeros trimmed,
    never rounded to fewer significant figures than the value has."""
    return f"{value:g}"


class _LegendRow(QWidget):
    """ "Main" swatch, then one badge per overlaid reference curve.

    The badges *are* the controls: clicking one toggles its curve, hovering
    one gives that reference's name, domain and point count. Legend-row
    controls rather than picking on the chart canvas -- a 140px-high plot
    with four curves crossing has no reliable hit target, and a badge is the
    same mark the reference wears everywhere else.
    """

    #: (curve index, now shown).
    curve_toggled = Signal(int, bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ChartLegend")
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 4)
        self._layout.setSpacing(4)
        self._layout.addWidget(_legend_swatch(_LINE))
        self._layout.addWidget(_legend_label("Main"))
        self._layout.addSpacing(10)
        self._buttons: list[badges.ReferenceBadgeButton] = []
        self._layout.addStretch(1)

    def set_curves(self, curves: list[tuple[ReferenceCurve, str]]) -> None:
        """Rebuild the badges from *curves*, each paired with its domain
        text."""
        for button in self._buttons:
            self._layout.removeWidget(button)
            button.setParent(None)
            button.deleteLater()
        self._buttons = []
        for _index, (curve, domain) in enumerate(curves):
            button = badges.ReferenceBadgeButton(curve.letters, curve.colour, f"{curve.name} · {domain}")
            button.toggled.connect(self._on_toggled)
            self._buttons.append(button)
            # Before the trailing stretch, after the "Main" swatch pair.
            self._layout.insertWidget(self._layout.count() - 1, button)

    def _on_toggled(self, shown: bool) -> None:
        button = self.sender()
        if button in self._buttons:
            self.curve_toggled.emit(self._buttons.index(button), shown)


def _legend_swatch(color: str) -> QLabel:
    swatch = QLabel()
    swatch.setFixedSize(14, 10)
    swatch.setStyleSheet(f"border-top: 2px solid {color}; margin-top: 4px;")
    return swatch


def _legend_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {MUTED}; {typography.size_qss(typography.META)}")
    return label
