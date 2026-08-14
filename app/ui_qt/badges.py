"""Shared count-badge geometry, colour and painting (unified badge system).

Before this module the app had three independent count-badge implementations
(the activity-bar icon overlay, the diagnostics rail/fold-header pill, the
diagnostics group-box header ``QLabel``) at three different sizes, each
re-deriving its own severity colours. This module is the one place that owns:

* the pill geometry (:data:`HEIGHT`, :data:`RADIUS`, :data:`FONT_PIXEL_SIZE`,
  :data:`MIN_WIDTH`, :data:`H_PADDING`) -- identical everywhere a badge is
  drawn, regardless of finish;
* the severity -> colour mapping in each of the two finishes a badge can be
  painted in (:func:`badge_colors`):

  - "tint" (the default): a pale severity-tinted background with matching
    text -- lists, rails, fold headers, group-box headers;
  - "solid": the plain severity colour with white text -- the activity-bar
    icon overlay, which needs to read clearly against varying icon art.

Callers still own their own *positioning* (the activity bar clamps its badge
inside the icon's corner; the diagnostics rail stacks several right to
left) -- only the shape, colour and pixel-painting are shared here.
"""

from __future__ import annotations

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter
from PySide6.QtWidgets import QLabel, QPushButton

from . import style, typography

#: Pill geometry -- one shape for every count badge in the app.
HEIGHT = 15
RADIUS = HEIGHT // 2
FONT_PIXEL_SIZE = typography.MICRO
MIN_WIDTH = HEIGHT
H_PADDING = 5

#: Severity -> (background, foreground) for the tint finish. ``None`` is the
#: neutral "outstanding" tier: outstanding is not an error.
_TINT_COLORS: dict[str | None, tuple[str, str]] = {
    "error": (style.ERROR_TINT, style.ERROR),
    "warning": (style.WARNING_TINT, style.WARNING),
    None: (style.NEUTRAL_TINT, style.MUTED),
}

#: Severity -> (background, foreground) for the solid finish (white text).
_SOLID_COLORS: dict[str | None, tuple[str, str]] = {
    "error": (style.ERROR, "#ffffff"),
    "warning": (style.WARNING, "#ffffff"),
    None: (style.MUTED, "#ffffff"),
}


def badge_colors(severity: str | None, *, solid: bool = False) -> tuple[str, str]:
    """(background, foreground) for *severity* ("error"/"warning"/None) in
    the requested finish -- tint by default, solid for the activity-bar icon
    overlay. An unrecognised severity falls back to the neutral/muted tier,
    same as the old per-call-site ``dict.get(..., style.MUTED)`` idiom."""
    table = _SOLID_COLORS if solid else _TINT_COLORS
    return table.get(severity, table[None])


def badge_font() -> QFont:
    """The pill's font: the UI face at :data:`FONT_PIXEL_SIZE`, semibold.

    Built from :func:`typography.ui_font` rather than a bare ``QFont()`` so a
    painted badge carries the same family as the label variant beside it --
    this module used to disagree with itself, painting at Qt's bold (700)
    while its QLabel variant asked the stylesheet for 600.
    """
    return typography.ui_font(FONT_PIXEL_SIZE, weight=typography.SEMIBOLD)


def badge_width(text: str) -> int:
    """The pill width *text* needs at the shared geometry -- never narrower
    than :data:`MIN_WIDTH`, so a single digit stays a circle, not an oval."""
    metrics = QFontMetrics(badge_font())
    return max(MIN_WIDTH, metrics.horizontalAdvance(text) + 2 * H_PADDING)


def paint_badge(painter: QPainter, rect: QRect, text: str, bg: str, fg: str) -> QRect:
    """Paint one pill filling *rect* exactly (already sized/positioned by the
    caller, e.g. via :func:`badge_width` and :data:`HEIGHT`) -- returns
    *rect* unchanged, so a caller stacking several badges can chain off it."""
    painter.save()
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(bg))
    painter.drawRoundedRect(rect, RADIUS, RADIUS)
    painter.setFont(badge_font())
    painter.setPen(QColor(fg))
    painter.drawText(rect, Qt.AlignCenter, text)
    painter.restore()
    return rect


def make_badge_label(text: str, bg: str, fg: str) -> QLabel:
    """A native ``QLabel`` pill -- the one badge call site that lives in a
    layout rather than a custom paint routine (the group-box header)."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignCenter)
    label.setFixedHeight(HEIGHT)
    label.setMinimumWidth(MIN_WIDTH)
    label.setStyleSheet(
        f"background:{bg}; color:{fg}; border-radius:{RADIUS}px; "
        f"padding:0 {H_PADDING}px; {typography.size_qss(FONT_PIXEL_SIZE)} "
        f"{typography.semibold_qss()}"
    )
    return label


#: A reference badge's diameter. Deliberately one size everywhere -- the
#: Workspace row, the strip chip, the card ledger cluster -- so a reference's
#: mark is the same object wherever it appears rather than a family of
#: near-identical discs the eye has to reconcile. Wider than
#: :data:`HEIGHT` because it carries two letters, not a count.
REFERENCE_BADGE_SIZE = 18


def _reference_badge_qss(colour: str, *, filled: bool) -> str:
    """The disc's look in either state. Filled means "this reference is on
    screen right now"; hollow keeps the same circle, letters and colour but
    drops the fill, so an inactive badge is legibly the same reference rather
    than a different mark. No cross, no strike, no tick -- the app's dot
    language bans those."""
    fill = colour if filled else "transparent"
    text = "#ffffff" if filled else colour
    return (
        f"background:{fill}; color:{text}; border:1px solid {colour}; "
        f"border-radius:{REFERENCE_BADGE_SIZE // 2}px; "
        f"{typography.size_qss(FONT_PIXEL_SIZE)} {typography.semibold_qss()}"
    )


def make_reference_badge(letters: str, colour: str, tooltip: str = "") -> QLabel:
    """A pinned reference's identity disc: its two letters in white on its
    pin-order *colour* (see :mod:`ui_qt.reference_identity`).

    A circle, not a pill: the letters are fixed at two, so a padded
    variable-width shape would only make four badges in a row ragged. The
    letters are the identity of last resort -- colour alone must never be the
    only thing telling two references apart -- so they are never elided, and
    *tooltip* (normally the full display name) is what a badge shown without
    its name relies on.
    """
    label = QLabel(letters)
    label.setAlignment(Qt.AlignCenter)
    label.setFixedSize(REFERENCE_BADGE_SIZE, REFERENCE_BADGE_SIZE)
    label.setStyleSheet(_reference_badge_qss(colour, filled=True))
    if tooltip:
        label.setToolTip(tooltip)
    return label


class ReferenceBadgeButton(QPushButton):
    """The same disc as a checkable control: the chart legend's curve toggle
    and the reference grid's selector.

    One grammar for both -- **filled means present on screen**. In the legend
    that is "this curve is drawn"; in the grid selector, "these are the
    numbers you are reading". A caller wanting exclusive selection drives the
    checked states itself; this widget only reports clicks.

    A class rather than a factory plus a closure: the restyle-on-toggle slot
    has to be a bound method of this very QObject, which PySide holds weakly.
    A lambda capturing the button would be a pure-Python cycle that only the
    cyclic GC could break -- the collector this app must never rely on to
    free widgets.
    """

    def __init__(self, letters: str, colour: str, tooltip: str = "", *, checked: bool = True) -> None:
        super().__init__(letters)
        self._colour = colour
        self.setObjectName("ReferenceBadgeButton")
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(REFERENCE_BADGE_SIZE, REFERENCE_BADGE_SIZE)
        self.setFlat(True)
        if tooltip:
            self.setToolTip(tooltip)
        self.toggled.connect(self._restyle)
        self.setChecked(checked)
        self._restyle()

    def _restyle(self) -> None:
        self.setStyleSheet(_reference_badge_qss(self._colour, filled=self.isChecked()))
