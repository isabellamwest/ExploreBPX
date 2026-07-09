"""Monochrome outline icons for the activity bar.

Icons are drawn as inline SVG (24x24 viewBox, 1.5px stroke, round caps/joins)
with a ``{color}`` placeholder for the stroke colour, so a single glyph can
be rendered in both the muted (unselected) and strong (selected) tones that
:func:`activity_icon` combines into one QIcon carrying both states -- Qt
then picks the right pixmap from a button's checked state with no repaint
logic of our own.
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

#: Unselected / selected stroke colours. The icon glyph never changes --
#: only its colour -- so severity/emphasis is always carried by tone, never
#: by shape (see the Validation icon: no tick, no warning triangle).
_MUTED = "#57606a"
_STRONG = "#1f2328"

#: Folder outline -- Workspace. Ink centred on (12, 12) alongside the other
#: two rail icons so the set reads as one optical family.
WORKSPACE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 7a1 1 0 0 1 1-1h4l2 2h7a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-13a1 1 0 0 1-1-1z"/>
</svg>
""".strip()

#: A root node connected to two children -- Editor's tree/hierarchy, not a
#: document glyph. Ink centred on (12, 12).
EDITOR = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="8.25" cy="6" r="1.75"/>
  <path d="M8.25 7.75V18"/>
  <path d="M8.25 11.5h5.25"/>
  <circle cx="15.75" cy="11.5" r="1.75"/>
  <path d="M8.25 18h5.25"/>
  <circle cx="15.75" cy="18" r="1.75"/>
</svg>
""".strip()

#: Clipboard with ruled lines -- Validation. Deliberately carries no tick,
#: cross or warning triangle: the glyph must assert neither pass nor fail,
#: only the badge (a plain, honest count) speaks to document state. Ink
#: centred on (12, 12).
VALIDATION = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5" y="6.25" width="14" height="13.5" rx="2"/>
  <rect x="9" y="4.25" width="6" height="3" rx="1"/>
  <path d="M8 10.5h8"/>
  <path d="M8 13.5h8"/>
  <path d="M8 16.5h5"/>
</svg>
""".strip()


def _device_pixel_ratio() -> float:
    """The primary screen's device-pixel-ratio, or 1.0 with no QApplication."""
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return screen.devicePixelRatio() if screen is not None else 1.0


def _render_pixmap(svg: str, color: str, size: int) -> QPixmap:
    """Render *svg* (with ``{color}`` substituted) into a transparent pixmap.

    Rendered at the primary screen's device-pixel-ratio and tagged with it
    so the icon stays crisp on HiDPI displays.
    """
    dpr = _device_pixel_ratio()
    pixel_size = max(1, round(size * dpr))
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpr)
    renderer = QSvgRenderer(QByteArray(svg.format(color=color).encode("utf-8")))
    painter = QPainter(pixmap)
    renderer.render(painter)
    painter.end()
    return pixmap


def tinted_icon(svg: str, color: str, size: int = 20) -> QIcon:
    """Render *svg* in a single flat *color* as a standalone QIcon."""
    return QIcon(_render_pixmap(svg, color, size))


def activity_icon(svg: str) -> QIcon:
    """Build one QIcon carrying both of an activity button's states.

    The unselected (``Off``) pixmap is muted; the selected (``On``) pixmap
    is the strong ink colour. Qt selects between them from the button's own
    checked state.
    """
    icon = QIcon()
    icon.addPixmap(_render_pixmap(svg, _MUTED, 20), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_render_pixmap(svg, _STRONG, 20), QIcon.Normal, QIcon.On)
    return icon
