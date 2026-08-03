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
from PySide6.QtWidgets import QLabel

from . import style

#: Pill geometry -- one shape for every count badge in the app.
HEIGHT = 15
RADIUS = HEIGHT // 2
FONT_PIXEL_SIZE = 10
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
    font = QFont()
    font.setPixelSize(FONT_PIXEL_SIZE)
    font.setBold(True)
    return font


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
        f"padding:0 {H_PADDING}px; font-size:{FONT_PIXEL_SIZE}px; font-weight:600;"
    )
    return label
