"""Documentation section body: long-form technical descriptions inside the
Inspector's resident Documentation section.

Renders the ordered (heading, prose) sections that
:func:`core.parameter_metadata.resolve_parameter_metadata` resolves from the
technical-descriptions dataset, plus the parameter's symbol as rendered maths
and a provenance footer. The view is deliberately *data-shaped*: it renders
whatever headings the dataset provides, in dataset order, so a revised
dataset file changes the app's documentation without any code change.

The ( i ) popover stays the quick glance; this section is where
multi-paragraph prose (physical correspondence, model sensitivity,
measurement methods) can be read properly - it persists beside the editor
instead of dismissing on the first outside click. Unlike the old tab it owns
no scroll area: it lives inside the Inspector's scrolling page and hugs its
own content. A parameter without dataset content shows one quiet
"no description" line, so an expanded section always explains itself; the
"nothing selected" state has no placeholder here because the Inspector hides
the whole section instead.

Data contract mirrors :class:`~ui_qt.issues_view.IssuesView`:
  - ``show_metadata(metadata)`` is the sole inbound data path; ``None``
    clears the view entirely.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from core.parameter_metadata import ParameterMetadata

from . import typography
from .latex import latex_pixmap

_MSG_NO_DOCS = "No technical description is available for this parameter."


class DocumentationView(QWidget):
    """Shows the selected parameter's technical description."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DocumentationView")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)

    def show_metadata(self, metadata: ParameterMetadata | None) -> None:
        """Render *metadata*'s documentation, or the "no description" line.

        A parameter without dataset content (user-defined, or simply not in
        the source document) gets the quiet placeholder line rather than a
        blank body, so an expanded section always communicates its state.
        ``None`` (no parameter shown) clears the view -- the Inspector hides
        the whole section in that state.
        """
        self._clear()
        if metadata is None:
            return
        if not metadata.documentation and not metadata.symbol:
            placeholder = QLabel(_MSG_NO_DOCS)
            placeholder.setObjectName("DocumentationPlaceholder")
            placeholder.setWordWrap(True)
            self._layout.addWidget(placeholder)
            return

        # Prose comes from the replaceable dataset file, so every text label is
        # forced to plain text: Qt's AutoText heuristic would otherwise
        # silently reinterpret a future revision containing '<' or '&...;' as
        # broken HTML -- exactly the silent-loss failure the loader's
        # raise-on-malformed policy exists to prevent.
        if metadata.symbol:
            row = QLabel()
            pixmap = latex_pixmap(metadata.symbol, size=typography.BODY)
            if pixmap is not None:
                row.setPixmap(pixmap)
            else:
                row.setTextFormat(Qt.PlainText)
                row.setText(metadata.symbol)
            row.setToolTip(metadata.symbol)
            self._layout.addWidget(row)

        for heading, prose in metadata.documentation:
            title = QLabel(heading, objectName="Heading")
            title.setTextFormat(Qt.PlainText)
            title.setWordWrap(True)
            self._layout.addWidget(title)
            body = QLabel(prose)
            body.setTextFormat(Qt.PlainText)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._layout.addWidget(body)

        if metadata.specification_link:
            href = html.escape(metadata.specification_link, quote=True)
            link = QLabel(f'<a href="{href}">BattINFO ontology entry</a>')
            link.setOpenExternalLinks(True)
            link.setToolTip(metadata.specification_link)
            self._layout.addWidget(link)

        if metadata.source:
            footer = QLabel(f"Source: {metadata.source}")
            footer.setTextFormat(Qt.PlainText)
            footer.setObjectName("Hint")
            footer.setWordWrap(True)
            self._layout.addWidget(footer)

    def reset(self) -> None:
        self.show_metadata(None)

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
