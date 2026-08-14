"""The floating "command palette" card the app's popups share.

The name popup, add-parameter popup and search popup are frameless
translucent top-levels whose visible chrome is a rounded, shadowed card.
The three used to hand-build identical shadows and margins; this helper is
the single copy. Visuals (border, radius, background) stay in ``style.py``
under each card's objectName -- this module only assembles the widgets.
"""

from __future__ import annotations

from PySide6.QtGui import QColor
from PySide6.QtWidgets import QFrame, QGraphicsDropShadowEffect, QVBoxLayout, QWidget

#: Outer margin reserved around the card so its drop shadow has room to
#: paint inside the translucent top-level window.
SHADOW_MARGIN = 16

#: The card's own interior inset. Named so height/width math outside this
#: module (the search popup's fit-to-rows sizing) can sum real margins
#: instead of restating an 8 that would silently drift.
CARD_MARGIN = 8


def floating_card(popup: QWidget, object_name: str, width: int | None = None) -> tuple[QFrame, QVBoxLayout]:
    """Build *popup*'s shadowed card and return ``(card, card_layout)``.

    Installs the card as *popup*'s sole child inside the shadow margin; the
    caller adds its own content to ``card_layout``.
    """
    card = QFrame()
    card.setObjectName(object_name)
    if width is not None:
        card.setFixedWidth(width)
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(CARD_MARGIN, CARD_MARGIN, CARD_MARGIN, CARD_MARGIN)
    card_layout.setSpacing(6)

    shadow = QGraphicsDropShadowEffect(popup)
    shadow.setBlurRadius(24)
    shadow.setColor(QColor(15, 23, 42, 60))
    shadow.setOffset(0, 5)
    card.setGraphicsEffect(shadow)

    outer = QVBoxLayout(popup)
    outer.setContentsMargins(SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN, SHADOW_MARGIN)
    outer.addWidget(card)
    return card, card_layout
