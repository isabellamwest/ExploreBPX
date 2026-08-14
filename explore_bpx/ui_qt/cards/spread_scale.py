"""SpreadScaleView: the ledger's 1-D picture of how far apart the values are.

The ledger rows above already state every value exactly; a column of numbers
cannot say whether two of them are neighbours or decades apart. This widget
says only that -- one axis, one mark per stated value, positions carrying the
whole message.

Deliberately not a chart:

- **Every mark is a stated value.** No mean, no band, no target, no
  good/bad colouring. A *mark* -- a pin's dot, the main document's own
  marker -- is never anything but a value some file actually states.
- **The axis has real divisions, not just two end labels.** Small tick marks
  plus labels (``SpreadScale.divisions``): round linear steps, or decade
  marks on a log axis, the way any conventional chart's axis is graduated.
  A division is axis furniture, not a mark -- its value need not be one any
  file states. This is a 2026-08-12 supersession of the stricter reading
  this docstring used to carry (every number on the axis a stated one, no
  exceptions); see ``core.spread``'s module docstring for the full note.
  The true stated extremes (``SpreadScale.value_lo``/``value_hi``) are still
  on the model, just no longer painted as the axis's end text -- a mark's
  own tooltip, and the ledger rows directly above, still give the exact
  number.
- **It never decides anything.** ``core.spread`` computes the geometry,
  including the log/linear choice and the divisions, and this only paints
  it. Neither kind spells its name out in words any more: a log axis's
  decade-style labels (1, 10, 100, ...) read as logarithmic on their own,
  and a linear axis now simply looks like every other numeric axis.
- **Read-only.** Hovering a mark names the references sharing it and their
  exact value. There is no click-to-pull: Pull lives on the ledger row above,
  where the value it writes is spelled out in full.

Painted rather than built from child widgets: a dot per pin per value is a
handful of primitives, and a `QWidget` per mark would be a rebuild on every
comparison refresh for something that cannot be clicked.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from explore_bpx.core.parameter_types import ParameterKind
from explore_bpx.core.spread import SpreadScale, build_spread, numeric
from explore_bpx.core.values import format_value
from explore_bpx.ui_qt import style, typography

if TYPE_CHECKING:
    from explore_bpx.core.compare import ValueGroup
    from explore_bpx.ui_qt.reference_identity import ReferencePin

#: The only kinds that get a scale. Read off the kind the rest of the app
#: already classified this parameter as -- never a fresh look at the value,
#: which is how two surfaces start disagreeing about what a number is.
SPREAD_KINDS = (ParameterKind.SCALAR, ParameterKind.INTEGER)


def scale_for(
    main_value: object,
    groups: tuple[ValueGroup, ...],
    pin_count: int,
    kind: ParameterKind | None,
) -> SpreadScale | None:
    """The scale for one parameter, or ``None`` when its kind gets none.

    The per-reference values are laid out **by pin index**, with a
    placeholder for any pin that lacks the key or whose value is not a
    number, so a tick's ``indices`` are pin indices the caller can colour
    directly. ``core.spread`` ignores the placeholders.
    """
    if kind not in SPREAD_KINDS:
        return None
    values = [math.nan] * pin_count
    for group in groups:
        number = numeric(group.value)
        if number is None:
            continue
        for index in group.indices:
            values[index] = number
    return build_spread(numeric(main_value), values)


#: Identity dot per pin at a value, and the gap between stacked ones.
_DOT = 7
_DOT_GAP = 2
#: Axis line to the bottom of the lowest dot.
_STEM = 6
#: How far the main marker crosses *below* the axis -- what makes it read as
#: the anchor the references are spread around rather than one more of them.
_MAIN_OVERSHOOT = 4
_TOP_PAD = 2
_LABEL_GAP = 4
#: Horizontal room reserved at each end so an outermost dot is never clipped.
_SIDE_INSET = _DOT
#: How near the pointer must be, in x, to claim a mark's tooltip.
_HIT_RADIUS = 9
#: How far a division's tick crosses *below* the axis -- shorter than
#: ``_MAIN_OVERSHOOT`` so a division always reads as the quieter of the two
#: things crossing the line.
_DIVISION_TICK = 3
#: Least horizontal gap two division labels must keep before they count as
#: colliding.
_LABEL_MIN_GAP = 6


class SpreadScaleView(QWidget):
    """One axis under the ledger rows; hidden whenever it would say nothing."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SpreadScale")
        self._scale: SpreadScale | None = None
        self._pins: list[ReferencePin] = []
        self._main_text = ""
        # Takes the width it is given (up to the cap ``set_scale`` applies):
        # the axis is a picture whose only content is distance, so resolution
        # is the one thing it gains from room.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.hide()

    def set_scale(
        self,
        scale: SpreadScale | None,
        pins: list[ReferencePin],
        *,
        main_text: str = "",
        width: int | None = None,
    ) -> None:
        """Show *scale*, or hide when it is ``None`` or not ``visible``.

        *main_text* is the main document's value as the card itself formats
        it -- the widget never re-renders a stored value in its own dialect.
        *width* caps the axis to the same measure as the value boxes above,
        so the picture sits exactly under the column it describes instead of
        stretching across a wide pane.
        """
        self._scale = scale if scale is not None and scale.visible else None
        self._pins = pins
        self._main_text = main_text
        if self._scale is None:
            self.hide()
            return
        self.setMaximumWidth(width if width is not None else 16777215)
        self.setFixedHeight(self._natural_height())
        self.update()
        self.show()

    @property
    def is_active(self) -> bool:
        """Whether a scale worth painting is loaded -- what the ledger shows
        or hides the whole indented strip by."""
        return self._scale is not None

    # ── geometry ────────────────────────────────────────────────────────

    def _placements(self) -> list[tuple[object, int, int]]:
        """Each tick with its painted ``x`` and the stack level its lowest
        dot sits on, in position order.

        Values that share a tick stack in pin order, as the design says.
        Values that merely land *near* each other stack too: at 280px, two
        stated values a thousandth of the span apart are one dot hiding
        another, and a hidden mark is the one thing this widget must never
        produce. Only the level moves -- ``x`` stays exactly where the value
        is, and the stem drawn down to the axis says where that is.
        """
        placed: list[tuple[object, int, int]] = []
        tops: list[tuple[int, int]] = []
        for tick in self._scale.ticks:
            x = self._x_for(tick.position)
            base = 0
            for other_x, other_top in tops:
                if abs(other_x - x) < _DOT + 1:
                    base = max(base, other_top + 1)
            placed.append((tick, x, base))
            tops.append((x, base + len(tick.indices) - 1))
        return placed

    def _stack_height(self) -> int:
        levels = [base + len(tick.indices) for tick, _x, base in self._placements()]
        deepest = max(levels, default=1)
        return deepest * _DOT + (deepest - 1) * _DOT_GAP

    def _axis_y(self) -> int:
        return _TOP_PAD + self._stack_height() + _STEM

    def _natural_height(self) -> int:
        metrics = QFontMetrics(typography.ui_font(typography.MICRO))
        return self._axis_y() + _MAIN_OVERSHOOT + _LABEL_GAP + metrics.height()

    def _x_for(self, position: float) -> int:
        span = max(self.width() - 2 * _SIDE_INSET, 1)
        return round(_SIDE_INSET + position * span)

    def resizeEvent(self, event) -> None:
        """Re-reserve height: how many dots collide depends on how wide the
        axis ended up, so the strip cannot know its height until it has one.

        Converges rather than oscillates -- a narrower axis can only stack
        more, never less, so a scrollbar appearing settles on the taller
        height instead of flipping back.
        """
        super().resizeEvent(event)
        if self._scale is not None:
            self.setFixedHeight(self._natural_height())

    # ── painting ────────────────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        scale = self._scale
        if scale is None:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        font = typography.ui_font(typography.MICRO)
        painter.setFont(font)
        axis_y = self._axis_y()

        painter.setPen(QPen(QColor(style.BORDER_STRONG), 1))
        painter.drawLine(_SIDE_INSET, axis_y, self.width() - _SIDE_INSET, axis_y)

        # Division ticks paint first, under everything: a mark (dot, main
        # marker) at the same x always reads as the more important thing at
        # that column.
        for division in scale.divisions:
            self._paint_division_tick(painter, division, axis_y)
        for tick, x, base in self._placements():
            self._paint_tick(painter, tick, x, base, axis_y)
        if scale.main_position is not None:
            # Darker and taller, and the only mark crossing the axis.
            x = self._x_for(scale.main_position)
            painter.setPen(QPen(QColor(style.DEFAULT_TEXT), 2))
            painter.drawLine(x, axis_y - _STEM - 3, x, axis_y + _MAIN_OVERSHOOT)

        self._paint_division_labels(painter, QFontMetrics(font), axis_y)
        painter.end()

    def _paint_tick(self, painter: QPainter, tick, x: int, base: int, axis_y: int) -> None:
        centre = axis_y - _STEM - _DOT // 2 - base * (_DOT + _DOT_GAP)
        # The stem reaches all the way up to whichever level the tick was
        # pushed to: a raised dot with no stem would be a mark floating free
        # of the value it stands for.
        painter.setPen(QPen(QColor(style.BORDER_STRONG), 1))
        painter.drawLine(x, axis_y - 1, x, centre)
        painter.setPen(Qt.NoPen)
        for index in tick.indices:
            painter.setBrush(QColor(self._pins[index].colour))
            painter.drawEllipse(QPoint(x, centre), _DOT // 2, _DOT // 2)
            centre -= _DOT + _DOT_GAP

    def _paint_division_tick(self, painter: QPainter, division, axis_y: int) -> None:
        """A short tick crossing *below* the axis at one division -- the
        same downward side the main marker overshoots to, but shorter, so a
        division always reads as the quieter of the two."""
        x = self._x_for(division.position)
        painter.setPen(QPen(QColor(style.BORDER_STRONG), 1))
        painter.drawLine(x, axis_y, x, axis_y + _DIVISION_TICK)

    def _paint_division_labels(self, painter: QPainter, metrics: QFontMetrics, axis_y: int) -> None:
        """One label per division, each centred under its own tick -- unless
        the axis is too narrow to fit them all, in which case
        :meth:`_visible_divisions` has already thinned the set. Ticks are
        never thinned, only the text beneath them: see ``paintEvent``.
        """
        top = axis_y + _MAIN_OVERSHOOT + _LABEL_GAP
        height = metrics.height()
        # Matches ``chart_axes.py``'s ``setLabelsColor(MUTED)`` -- the same
        # tier every other axis label in the app reads at.
        painter.setPen(QColor(style.MUTED))
        for division in self._visible_divisions(metrics):
            x = self._x_for(division.position)
            width = metrics.horizontalAdvance(division.label)
            # Centred on x, but never pushed past the widget's own edges --
            # a division near a padded end otherwise overhangs it.
            left = max(0, min(x - width // 2, self.width() - width))
            painter.drawText(QRect(left, top, width, height), Qt.AlignHCenter, division.label)

    def _visible_divisions(self, metrics: QFontMetrics) -> list:
        """The subset of ``scale.divisions`` whose labels fit without
        colliding, doubling the stride (every 2nd, then every 4th, ...)
        until what remains clears -- which a single label always does.
        """
        divisions = list(self._scale.divisions)
        stride = 1
        while self._labels_collide(divisions[::stride], metrics):
            stride *= 2
        return divisions[::stride]

    def _labels_collide(self, divisions: list, metrics: QFontMetrics) -> bool:
        if len(divisions) < 2:
            return False
        edges = [
            (
                self._x_for(division.position) - metrics.horizontalAdvance(division.label) / 2,
                self._x_for(division.position) + metrics.horizontalAdvance(division.label) / 2,
            )
            for division in divisions
        ]
        # Divisions arrive in ascending position order (``core.spread``
        # sorts them, the same invariant ``ticks`` keeps), so adjacent
        # pairs in this list are adjacent on the axis too.
        return any(edges[i][1] + _LABEL_MIN_GAP > edges[i + 1][0] for i in range(len(edges) - 1))

    # ── reading ─────────────────────────────────────────────────────────

    def axis_kind(self) -> str:
        """ "log" or "linear" -- the axis's own read of which kind it chose.

        Until 2026-08-12 this was painted as a caption; now a log axis's
        decade-style division labels imply it without spelling it out, so
        nothing paints this word any more. It remains for callers that want
        the fact itself rather than a rendering of it (tests, mainly).
        """
        return "log" if self._scale is not None and self._scale.log else "linear"

    def tooltip_at(self, x: int) -> str:
        """The mark within :data:`_HIT_RADIUS` of *x*, as "names · value".

        Nearest wins; the main marker breaks a tie, since it is the mark
        drawn on top. Empty when the pointer is over bare axis.
        """
        if self._scale is None:
            return ""
        best: tuple[int, str] | None = None
        for tick in self._scale.ticks:
            distance = abs(self._x_for(tick.position) - x)
            names = ", ".join(self._pins[index].name for index in tick.indices)
            if distance <= _HIT_RADIUS and (best is None or distance < best[0]):
                best = (distance, f"{names} · {format_value(tick.value)}")
        if self._scale.main_position is not None:
            distance = abs(self._x_for(self._scale.main_position) - x)
            if distance <= _HIT_RADIUS and (best is None or distance <= best[0]):
                best = (distance, f"Main file · {self._main_text}")
        return "" if best is None else best[1]

    def event(self, event) -> bool:
        """Per-mark tooltips: one widget, so the text is chosen by position
        rather than by a child widget per mark.

        Off a mark this falls through to the base implementation, which
        shows nothing: the widget carries no tooltip of its own now that the
        axis-kind caption is gone (2026-08-12) -- only a mark has anything
        to say on hover.
        """
        if event.type() == QEvent.ToolTip and self._scale is not None:
            text = self.tooltip_at(event.pos().x())
            if text:
                QToolTip.showText(event.globalPos(), text, self)
                return True
        return super().event(event)
