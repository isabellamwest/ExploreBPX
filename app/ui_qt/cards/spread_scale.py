"""SpreadScaleView: the ledger's 1-D picture of how far apart the values are.

The ledger rows above already state every value exactly; a column of numbers
cannot say whether two of them are neighbours or decades apart. This widget
says only that -- one axis, one mark per stated value, positions carrying the
whole message (design rule 4 of ``PLAN-multi-reference.md``).

Deliberately not a chart:

- **Every mark is a stated value.** No mean, no band, no target, no
  good/bad colouring. The axis ends are labelled with the lowest and highest
  values that actually appear (``SpreadScale.value_lo``/``value_hi``); the
  padding that keeps those marks off the edges never surfaces as a number.
- **It never decides anything.** ``core.spread`` computes the geometry,
  including the log/linear choice, and this paints it. The chosen axis is
  always named on screen, so a log switch is never silent.
- **Read-only.** Hovering a mark names the references sharing it and their
  exact value. There is no click-to-pull: Pull lives on the ledger row above,
  where the value it writes is spelled out in full.

Painted rather than built from child widgets: a dot per pin per value is a
handful of primitives, and a `QWidget` per mark would be a rebuild on every
comparison refresh for something that cannot be clicked.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPoint, QRect, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from core.compare import ValueGroup
from core.parameter_types import ParameterKind
from core.spread import SpreadScale, build_spread, numeric
from core.values import format_value

from .. import style, typography
from ..reference_identity import ReferencePin

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
#: Clearance the axis-kind word needs from either end label before it is
#: dropped to a tooltip rather than drawn into one of them.
_KIND_CLEARANCE = 10


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
        return int(round(_SIDE_INSET + position * span))

    def resizeEvent(self, event) -> None:  # noqa: N802 (Qt override)
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

    def paintEvent(self, event) -> None:  # noqa: N802 (Qt override)
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

        for tick, x, base in self._placements():
            self._paint_tick(painter, tick, x, base, axis_y)
        if scale.main_position is not None:
            # Darker and taller, and the only mark crossing the axis.
            x = self._x_for(scale.main_position)
            painter.setPen(QPen(QColor(style.DEFAULT_TEXT), 2))
            painter.drawLine(x, axis_y - _STEM - 3, x, axis_y + _MAIN_OVERSHOOT)

        self._paint_labels(painter, QFontMetrics(font), axis_y)
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

    def _paint_labels(self, painter: QPainter, metrics: QFontMetrics, axis_y: int) -> None:
        scale = self._scale
        top = axis_y + _MAIN_OVERSHOOT + _LABEL_GAP
        height = metrics.height()
        painter.setPen(QColor(style.MUTED))

        lo, hi = format_value(scale.value_lo), format_value(scale.value_hi)
        painter.drawText(QRect(0, top, self.width(), height), Qt.AlignLeft, lo)
        painter.drawText(QRect(0, top, self.width(), height), Qt.AlignRight, hi)

        # The axis kind is named whenever there is room for it plainly; when
        # the two values fill the row it retreats to the tooltip rather than
        # colliding with a number. "linear scale", not a bare "linear": the
        # extra word is what makes the strip say what it is, so it needs no
        # caption row of its own.
        caption = f"{self.axis_kind()} scale"
        needed = (
            metrics.horizontalAdvance(lo)
            + metrics.horizontalAdvance(hi)
            + metrics.horizontalAdvance(caption)
            + 2 * _KIND_CLEARANCE
        )
        crowded = needed > self.width()
        if not crowded:
            # Lighter than the end labels: those are values a file states,
            # this is only how the axis is drawn, and the two must not read
            # as the same class of thing.
            painter.setPen(QColor(style.GHOST_TEXT))
            painter.drawText(QRect(0, top, self.width(), height), Qt.AlignHCenter, caption)
        wanted = caption if crowded else ""
        if self.toolTip() != wanted:
            self.setToolTip(wanted)

    # ── reading ─────────────────────────────────────────────────────────

    def axis_kind(self) -> str:
        """"log" or "linear" -- named on screen so the switch is never
        silent."""
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
        shows the widget-level tooltip -- the axis-kind fallback set by
        :meth:`_paint_labels` when the row is too narrow to name it.
        """
        if event.type() == QEvent.ToolTip and self._scale is not None:
            text = self.tooltip_at(event.pos().x())
            if text:
                QToolTip.showText(event.globalPos(), text, self)
                return True
        return super().event(event)
