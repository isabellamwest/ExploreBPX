"""Documentation tab: long-form technical descriptions inside the Inspector's
secondary workspace.

Renders the ordered (heading, prose) sections that
:func:`core.parameter_metadata.resolve_parameter_metadata` resolves from the
technical-descriptions dataset, plus the parameter's symbol as rendered maths
and a provenance footer. The tab is deliberately *data-shaped*: it renders
whatever headings the dataset provides, in dataset order, so a revised
dataset file changes the app's documentation without any code change.

The ( i ) popover stays the quick glance; this tab is where multi-paragraph
prose (physical correspondence, model sensitivity, measurement methods) can
be read properly — it persists beside the editor instead of dismissing on the
first outside click.

Data contract mirrors :class:`~ui_qt.issues_tab.IssuesTab`:
  - ``show_metadata(metadata)`` is the sole inbound data path; ``None``
    clears it back to the no-selection placeholder.
"""

from __future__ import annotations

import html

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.parameter_metadata import ParameterMetadata

from .latex import latex_pixmap

_MSG_NO_SELECTION = "Select a parameter to view its documentation."
_MSG_NO_DOCS = "No technical description is available for this parameter."


class DocumentationTab(QWidget):
    """Shows the selected parameter's technical description, scrollable."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DocumentationTab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.NoFrame)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(12, 8, 12, 8)
        self._scroll.setWidget(self._content)
        self._stack.addWidget(self._scroll)  # index 0 — documentation

        self._placeholder = QLabel(_MSG_NO_SELECTION)
        self._placeholder.setObjectName("DocumentationPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # index 1 — empty state

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)  # start on the placeholder

    def show_metadata(self, metadata: ParameterMetadata | None) -> None:
        """Render *metadata*'s documentation, or an explanatory placeholder.

        A parameter without dataset content (user-defined, or simply not in
        the source document) gets the "no description" placeholder rather
        than a blank pane, so the tab always communicates its state.
        """
        self._clear()
        if metadata is None:
            self._placeholder.setText(_MSG_NO_SELECTION)
            self._stack.setCurrentIndex(1)
            return
        if not metadata.documentation and not metadata.symbol:
            self._placeholder.setText(_MSG_NO_DOCS)
            self._stack.setCurrentIndex(1)
            return

        # Prose comes from the replaceable dataset file, so every text label is
        # forced to plain text: Qt's AutoText heuristic would otherwise
        # silently reinterpret a future revision containing '<' or '&...;' as
        # broken HTML -- exactly the silent-loss failure the loader's
        # raise-on-malformed policy exists to prevent.
        if metadata.symbol:
            row = QLabel()
            pixmap = latex_pixmap(metadata.symbol, point_size=13.0)
            if pixmap is not None:
                row.setPixmap(pixmap)
            else:
                row.setTextFormat(Qt.PlainText)
                row.setText(metadata.symbol)
            row.setToolTip(metadata.symbol)
            self._content_layout.addWidget(row)

        for heading, prose in metadata.documentation:
            title = QLabel(heading, objectName="Heading")
            title.setTextFormat(Qt.PlainText)
            self._content_layout.addWidget(title)
            body = QLabel(prose)
            body.setTextFormat(Qt.PlainText)
            body.setWordWrap(True)
            body.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._content_layout.addWidget(body)

        if metadata.specification_link:
            href = html.escape(metadata.specification_link, quote=True)
            link = QLabel(f'<a href="{href}">BattINFO ontology entry</a>')
            link.setOpenExternalLinks(True)
            link.setToolTip(metadata.specification_link)
            self._content_layout.addWidget(link)

        if metadata.source:
            footer = QLabel(f"Source: {metadata.source}")
            footer.setTextFormat(Qt.PlainText)
            footer.setObjectName("Hint")
            footer.setWordWrap(True)
            self._content_layout.addWidget(footer)

        self._content_layout.addStretch(1)
        self._scroll.verticalScrollBar().setValue(0)
        self._stack.setCurrentIndex(0)

    def reset(self) -> None:
        self.show_metadata(None)

    def _clear(self) -> None:
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
