"""Page scaffold for the Inspector's cards: a full-bleed tinted header band,
then a content column on the same fixed gutter.

Every card that fills the Inspector's editing pane composes these two pieces
so the pane reads as one designed page whichever card is showing: the header
band carries identity (title row, rename row, description) on the app's
neutral section wash -- the same tinted-band language as the Workspace
page's sections and the parameter list's header, with no hairline (the wash
edge is the boundary) -- and the content column carries the work surface
(editor, reference section) on the white page below. Both builders return
``(container, layout)`` so callers add their own widgets; the margins and
spacing live here, once, instead of per card.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

from ui_qt import style

#: The single horizontal gutter every page block shares -- the page rung of
#: the shared spacing scale, not a width of this module's own.
GUTTER = style.SPACING_LG


def page_header() -> tuple[QFrame, QVBoxLayout]:
    """The header band: styled ``CardPageHeader`` (neutral wash, no rule)."""
    frame = QFrame()
    frame.setObjectName("CardPageHeader")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(GUTTER, 12, GUTTER, 12)
    layout.setSpacing(4)
    return frame, layout


def page_content() -> tuple[QWidget, QVBoxLayout]:
    """The content column below the header, on the same gutter.

    Capped at ``style.PAGE_MEASURE`` rather than the narrower
    ``style.CONTENT_MEASURE``: a card's editor is a chart, a grid or a
    ledger of keyed values, not running prose, so the reading measure
    starved it the same way it once starved the Workspace page (see
    ``PAGE_MEASURE``'s own comment) -- a 528px-wide chart with hundreds of
    idle pixels beside it. The cap only bounds the maximum, so the column
    still shrinks on a narrow pane. Left unset on the widget itself, the
    containing ``QVBoxLayout`` hugs the capped column against its left edge
    (the same side ``GUTTER`` already indents from), so no explicit
    alignment call is needed here.
    """
    body = QWidget()
    body.setMaximumWidth(style.PAGE_MEASURE)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(GUTTER, 12, GUTTER, GUTTER)
    layout.setSpacing(style.SPACING_MD)
    return body, layout
