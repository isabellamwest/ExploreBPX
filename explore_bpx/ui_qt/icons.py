"""Monochrome outline icons for the activity bar.

Icons are drawn as inline SVG (24x24 viewBox, 1.5px stroke, round caps/joins)
with a ``{color}`` placeholder for the stroke colour, so a single glyph can
be rendered in both the muted (unselected) and strong (selected) tones that
:func:`activity_icon` combines into one QIcon carrying both states -- Qt
then picks the right pixmap from a button's checked state with no repaint
logic of our own.
"""

from __future__ import annotations

import base64
from functools import lru_cache

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QFontMetrics, QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from explore_bpx.ui_qt import style, typography

#: Unselected / selected stroke colours. The icon glyph never changes --
#: only its colour -- so severity/emphasis is always carried by tone, never
#: by shape (see the Diagnostics icon: no tick, no warning triangle).
_MUTED = style.MUTED
_STRONG = style.DEFAULT_TEXT

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

#: Clipboard with ruled lines -- Diagnostics. Deliberately carries no tick,
#: cross or warning triangle: the glyph must assert neither pass nor fail,
#: only the badge (a plain, honest count) speaks to document state. Ink
#: centred on (12, 12).
DIAGNOSTICS = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <rect x="5" y="6.25" width="14" height="13.5" rx="2"/>
  <rect x="9" y="4.25" width="6" height="3" rx="1"/>
  <path d="M8 10.5h8"/>
  <path d="M8 13.5h8"/>
  <path d="M8 16.5h5"/>
</svg>
""".strip()


#: Code brackets ``</>`` -- Source: the document's raw JSON. Ink centred on
#: (12, 12) alongside the other rail icons.
SOURCE = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M8 8l-4 4 4 4"/>
  <path d="M16 8l4 4-4 4"/>
  <path d="M13.25 6.75l-2.5 10.5"/>
</svg>
""".strip()


#: Folder outline -- a section/object row in the search results (same
#: container metaphor as the Workspace rail icon, drawn as its own constant
#: so the rail identity can evolve without silently restyling result rows).
SECTION = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 7a1 1 0 0 1 1-1h4l2 2h7a1 1 0 0 1 1 1v8a1 1 0 0 1-1 1h-13a1 1 0 0 1-1-1z"/>
</svg>
""".strip()

#: Two slider rails with offset knobs ("tune") -- a parameter row in the
#: search results: an adjustable value, deliberately kind-agnostic (kind
#: vocabulary belongs to the editor's cards, not a navigation list).
PARAMETER = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M4.5 8.5h3"/>
  <circle cx="9.5" cy="8.5" r="2"/>
  <path d="M11.5 8.5h8"/>
  <path d="M4.5 15.5h8"/>
  <circle cx="14.5" cy="15.5" r="2"/>
  <path d="M16.5 15.5h3"/>
</svg>
""".strip()

#: Pencil over a baseline -- the card-header "rename name & unit" button on a
#: User-defined parameter. Drawn in the same outline family as the rail icons
#: (24x24, 1.5px stroke, round caps) so it reads as one of ours, not a stray
#: glyph -- which is exactly what the bare "✎" QPushButton text it replaces
#: looked like.
PENCIL = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
  <path d="M12 20h8"/>
  <path d="M16 4.5a1.9 1.9 0 0 1 2.7 2.7L7.6 18.3l-3.6 0.9 0.9-3.6z"/>
</svg>
""".strip()


#: The app's one status-dot family:
#: a filled circle (error/warning), a hollow ring (a task not yet started),
#: and a half-filled circle (a task started but not yet given a value).
#: Sized so every mark reads as the same "8px mark in a 13px box" as the
#: delegate-painted severity dot (``ui_qt.parameter_row.paint_severity_dot``)
#: -- at the family's usual render size of 13 (:func:`html_img`'s default),
#: the circle occupies 15 of the 24 viewBox units, i.e. 15/24 * 13 ≈ 8px.
#: Unlike the outline family above, colour here is a fill/stroke on a
#: circle, not the ``{color}`` stroke of a line glyph -- these three are
#: never combined with that family in one place.
DOT = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="7.5" fill="{color}"/>
</svg>
""".strip()

#: Hollow ring -- same 15/24 outer diameter as :data:`DOT`, so a task's
#: "nothing committed yet" mark reads the same size as an issue's dot.
RING = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none"
     stroke="{color}" stroke-width="3">
  <circle cx="12" cy="12" r="6"/>
</svg>
""".strip()

#: Half-filled circle -- the same ring as :data:`RING` with its left half
#: additionally filled solid, for a task that is "committed, but null".
HALF = """
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">
  <circle cx="12" cy="12" r="6" fill="none" stroke="{color}" stroke-width="3"/>
  <path d="M12 4.5a7.5 7.5 0 0 0 0 15z" fill="{color}"/>
</svg>
""".strip()


def _device_pixel_ratio() -> float:
    """The primary screen's device-pixel-ratio, or 1.0 with no QApplication."""
    app = QGuiApplication.instance()
    screen = app.primaryScreen() if app is not None else None
    return screen.devicePixelRatio() if screen is not None else 1.0


def _render_pixmap(svg: str, color: str, size: int, *, lift: int = 0) -> QPixmap:
    """Render *svg* (with ``{color}`` substituted) into a transparent pixmap.

    Rendered at the primary screen's device-pixel-ratio and tagged with it
    so the icon stays crisp on HiDPI displays. *lift* shifts the ink up by
    that many logical pixels within the (unchanged) canvas -- see
    :func:`_default_inline_lift`; every glyph carries enough viewBox padding
    that a small lift never clips.
    """
    dpr = _device_pixel_ratio()
    pixel_size = max(1, round(size * dpr))
    pixmap = QPixmap(pixel_size, pixel_size)
    pixmap.fill(Qt.transparent)
    pixmap.setDevicePixelRatio(dpr)
    renderer = QSvgRenderer(QByteArray(svg.format(color=color).encode("utf-8")))
    painter = QPainter(pixmap)
    # Always render into an explicit logical-coordinate rect: the no-argument
    # render() targets the painter's device-pixel viewport, which the DPR
    # scale then doubles -- on HiDPI screens the glyph paints oversized and
    # clipped to its top-left quadrant.
    renderer.render(painter, QRectF(0, -lift, size, size))
    painter.end()
    return pixmap


_HTML_IMG_CACHE: dict[tuple[str, str, int, int], str] = {}


@lru_cache(maxsize=1)
def _default_inline_lift() -> int:
    """The derived default ink lift (rounded logical px) for :func:`html_img`.

    Qt's rich text centres an inline image's *box* on the x-height midline
    (``vertical-align: middle``), but these glyphs all sit beside
    Capitalised/digit-led label text whose optical midline is the *cap*
    midline -- half a cap height above the baseline, against half an
    x-height. The correction is the gap between those two halves,
    ``(capHeight - xHeight) / 2``, of the font that text is actually set in
    -- the app's BODY UI font, since that is the rung every card header and
    list row beside these glyphs uses. A function, not a module constant:
    building a ``QFontMetrics`` needs a live ``QGuiApplication``, which need
    not exist yet when this module is imported; ``lru_cache`` means it is
    still computed once. Compare :func:`~ui_qt.parameter_row.
    cap_midline_mark_top`, the same correction for a mark painted directly
    against a known text rect rather than embedded in a rich-text flow.
    """
    metrics = QFontMetrics(typography.ui_font(typography.BODY))
    return round((metrics.capHeight() - metrics.xHeight()) / 2)


def html_img(svg: str, *, color: str = _MUTED, size: int = 13, lift: int | None = None) -> str:
    """An ``<img>`` rich-text fragment embedding *svg* as a data-URI PNG.

    For rows painted through ``QTextDocument`` (``ParameterRowDelegate``),
    which cannot draw QIcons: the pixmap is rendered at the screen's
    device-pixel-ratio and scaled back to *size* by explicit width/height
    attributes, so glyphs stay crisp on HiDPI displays. Cached per
    (svg, color, size, lift) because callers rebuild rows on every
    keystroke; a DPR change mid-session (rare) keeps serving the first
    rendering.

    *lift* defaults to :func:`_default_inline_lift`, derived from the app's
    BODY UI font; pass an explicit value only for a call site whose
    adjacent text is genuinely set at a different rung or face.
    """
    if lift is None:
        lift = _default_inline_lift()
    key = (svg, color, size, lift)
    cached = _HTML_IMG_CACHE.get(key)
    if cached is not None:
        return cached
    pixmap = _render_pixmap(svg, color, size, lift=lift)
    buffer = QBuffer()
    buffer.open(QIODevice.WriteOnly)
    pixmap.save(buffer, "PNG")
    encoded = base64.b64encode(bytes(buffer.data())).decode("ascii")
    fragment = (
        f'<img src="data:image/png;base64,{encoded}" width="{size}" height="{size}" style="vertical-align: middle;">'
    )
    _HTML_IMG_CACHE[key] = fragment
    return fragment


def dot_pixmap(color: str, size: int = 13) -> QPixmap:
    """The app's standard filled dot as a bare pixmap, for surfaces that
    take a ``QPixmap`` directly (e.g. a table item's ``DecorationRole``)
    rather than rich text or a painter. Same :data:`DOT` glyph and default
    13px box as every other dot in the app, so a series swatch in a table
    reads as the same mark as the swatch beside a chart."""
    return _render_pixmap(DOT, color, size)


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


def hover_icon(svg: str, size: int = 16) -> QIcon:
    """Build one QIcon that darkens when the pointer is over it.

    Muted at rest, strong ink under the pointer (Qt paints the ``Active``
    pixmap while a widget is hovered) -- the same tone jump as
    :func:`activity_icon`'s selected state. It lets a flat, box-less icon
    button still signal "live" on hover with no border or fill of its own.
    """
    icon = QIcon()
    icon.addPixmap(_render_pixmap(svg, _MUTED, size), QIcon.Normal, QIcon.Off)
    icon.addPixmap(_render_pixmap(svg, _STRONG, size), QIcon.Active, QIcon.Off)
    return icon
