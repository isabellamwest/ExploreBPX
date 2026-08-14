"""Parameter information popover: the ( i ) contextual documentation surface.

Anchored to a :class:`~ui_qt.cards.parameter_card.ParameterCard`'s info
button. Follows the frameless ``Qt.FramelessWindowHint | Qt.Tool`` window-flag
pattern established by :class:`ui_qt.search.SearchPopup`. Unlike
``SearchPopup`` -- which stays non-activating because the owning
``SearchBar`` keeps focus and handles all keyboard input itself -- this
popover takes keyboard focus so it can dismiss itself on Escape directly; the
card's ( i ) button owns the open/close toggle.
"""

from __future__ import annotations

import html
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .dismissal import OutsideDismissFilter
from .latex import symbol_label

if TYPE_CHECKING:
    from core.parameter_metadata import ParameterMetadata

#: Same width as name_popup's card -- both are frameless anchored popups.
_CARD_WIDTH = 300

#: (heading, ParameterMetadata field name) for the quick-glance facts, in
#: display order. A field that resolves empty/``None`` is simply omitted.
#: The long-form documentation deliberately does NOT render here - it is
#: multi-paragraph prose and lives in the Inspector's Documentation section;
#: the popover stays a glance.
_SECTIONS: tuple[tuple[str, str], ...] = (
    ("Physical meaning", "physical_meaning"),
    ("Units", "units"),
    ("Accepted types", "accepted_types"),
)


class ParameterInfoPopover(QWidget):
    """Frameless popup rendering only the populated ``ParameterMetadata`` fields."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ParameterInfoPopover")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(_CARD_WIDTH)
        self._layout = QVBoxLayout(self)
        #: The ( i ) anchor button is deliberately not registered as "inside"
        #: here -- clicking it while the popover is open must close-and-swallow
        #: (reading as a toggle) rather than reopen; see the card's own
        #: click-to-toggle handler.
        self._dismiss_filter = OutsideDismissFilter(self)

    def show_metadata(self, metadata: ParameterMetadata) -> None:
        """Rebuild the popover's contents from *metadata*, omitting empty fields.

        Text labels are forced to plain text: metadata prose comes from the
        replaceable dataset file and the schema, and Qt's AutoText heuristic
        would silently reinterpret content containing ``<`` as HTML. Only the
        link label deliberately uses rich text, with an escaped href.
        """
        self._clear()
        if metadata.is_custom:
            # A parameter the BPX standard does not define: say so plainly
            # rather than showing an empty popover. The validator, elsewhere,
            # judges whether it is *legal* here -- this only states provenance.
            self._layout.addWidget(QLabel("Custom parameter", objectName="Heading"))
            note = QLabel("Not defined by the BPX schema - no standard documentation.")
            note.setTextFormat(Qt.PlainText)
            note.setWordWrap(True)
            self._layout.addWidget(note)
        if metadata.symbol:
            self._layout.addWidget(QLabel("Symbol", objectName="Heading"))
            self._layout.addWidget(symbol_label(metadata.symbol))
        for heading, field_name in _SECTIONS:
            value = getattr(metadata, field_name)
            if not value:
                continue
            self._layout.addWidget(QLabel(heading, objectName="Heading"))
            body = QLabel(str(value))
            body.setTextFormat(Qt.PlainText)
            body.setWordWrap(True)
            self._layout.addWidget(body)
        if metadata.specification_link:
            href = html.escape(metadata.specification_link, quote=True)
            link = QLabel(f'<a href="{href}">BattINFO ontology entry</a>')
            link.setOpenExternalLinks(True)
            link.setToolTip(metadata.specification_link)
            self._layout.addWidget(link)
        if metadata.documentation:
            hint = QLabel("Full description in the Documentation section.")
            hint.setObjectName("Hint")
            hint.setWordWrap(True)
            self._layout.addWidget(hint)

    def open_below(self, anchor: QWidget) -> None:
        """Show the popover under *anchor*, extending left, and take keyboard focus.

        Right edges are aligned so the popover grows leftward from the anchor.
        The ( i ) button sits at the right edge of the Inspector card, so
        extending rightward would run the popover off-screen when the app is
        full-screen; aligning right edges keeps it within the content area.
        """
        self.adjustSize()
        bottom_right = anchor.mapToGlobal(anchor.rect().bottomRight())
        x = bottom_right.x() - self.width()
        y = bottom_right.y()
        screen = anchor.screen()
        if screen is not None:
            available = screen.availableGeometry()
            x = max(available.left(), min(x, available.right() - self.width()))
            y = max(available.top(), min(y, available.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self._dismiss_filter.install()
        self.setFocus(Qt.PopupFocusReason)

    def _clear(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Reparent out *now*: deleteLater only reaps when the event
                # loop unwinds, and a widget merely taken from the layout
                # stays a visible child painting over its replacement (the
                # Inspector ghost-placeholder bug, same class).
                #
                # hide() before setParent(None) -- see InspectorPanel
                # ._clear_content: reparenting a widget that is queued to be
                # shown but not yet visible lets the pending show land on it
                # once it is parentless, flashing a stray top-level window.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)
