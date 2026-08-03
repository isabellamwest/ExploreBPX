"""Page scaffold for the Inspector's cards: a full-bleed header block closed
by a hairline rule, then a content column on the same fixed gutter.

Every card that fills the Inspector's editing pane composes these two pieces
so the pane reads as one designed page whichever card is showing: the header
frame carries identity (title row, rename row, description), the content
column carries the work surface (editor, reference section). Both builders
return ``(container, layout)`` so callers add their own widgets; the margins
and spacing live here, once, instead of per card.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QVBoxLayout, QWidget

#: The single horizontal gutter every page block shares.
GUTTER = 16


def page_header() -> tuple[QFrame, QVBoxLayout]:
    """The header block: styled ``CardPageHeader`` (hairline rule below)."""
    frame = QFrame()
    frame.setObjectName("CardPageHeader")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(GUTTER, 12, GUTTER, 10)
    layout.setSpacing(4)
    return frame, layout


def page_content() -> tuple[QWidget, QVBoxLayout]:
    """The content column below the header, on the same gutter."""
    body = QWidget()
    layout = QVBoxLayout(body)
    layout.setContentsMargins(GUTTER, 12, GUTTER, GUTTER)
    layout.setSpacing(10)
    return body, layout
