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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.parameter_metadata import ParameterMetadata

from .dismissal import OutsideDismissFilter
from .latex import latex_pixmap

#: (heading, ParameterMetadata field name) for the quick-glance facts, in
#: display order. A field that resolves empty/``None`` is simply omitted.
#: The long-form documentation deliberately does NOT render here — it is
#: multi-paragraph prose and lives in the Inspector's Documentation tab; the
#: popover stays a glance.
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
        self.setFixedWidth(300)
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
        if metadata.symbol:
            self._layout.addWidget(QLabel("Symbol", objectName="Heading"))
            self._layout.addWidget(_symbol_label(metadata.symbol))
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
            hint = QLabel("Full description in the Documentation tab.")
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
                widget.deleteLater()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Escape:
            self.hide()
            return
        super().keyPressEvent(event)


def _symbol_label(latex: str) -> QLabel:
    """A label showing *latex* as rendered maths, or as source text if the
    renderer is unavailable — the information is never silently dropped."""
    label = QLabel()
    pixmap = latex_pixmap(latex)
    if pixmap is not None:
        label.setPixmap(pixmap)
    else:
        label.setTextFormat(Qt.PlainText)
        label.setText(latex)
    label.setToolTip(latex)
    return label
