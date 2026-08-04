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

from .. import style

#: The single horizontal gutter every page block shares.
GUTTER = 16


def page_header() -> tuple[QFrame, QVBoxLayout]:
    """The header band: styled ``CardPageHeader`` (neutral wash, no rule)."""
    frame = QFrame()
    frame.setObjectName("CardPageHeader")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(GUTTER, 12, GUTTER, 10)
    layout.setSpacing(4)
    return frame, layout


def page_content() -> tuple[QWidget, QVBoxLayout]:
    """The content column below the header, on the same gutter.

    Capped at ``style.CONTENT_MEASURE`` so a card's fields/prose stay a
    readable width rather than stretching edge-to-edge with a wide pane;
    the cap only bounds the maximum, so the column still shrinks on a
    narrow pane. Left unset on the widget itself, the containing
    ``QVBoxLayout`` hugs the capped column against its left edge (the same
    side ``GUTTER`` already indents from), so no explicit alignment call is
    needed here.
    """
    body = QWidget()
    body.setMaximumWidth(style.CONTENT_MEASURE)
    layout = QVBoxLayout(body)
    layout.setContentsMargins(GUTTER, 12, GUTTER, GUTTER)
    layout.setSpacing(10)
    return body, layout
