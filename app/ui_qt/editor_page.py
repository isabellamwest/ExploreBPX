"""Editor page: the tree/params/inspector three-pane splitter, plus its
empty-state placeholder when no document is open.

A thin wrapper (not a redesign of the three-pane layout): it hosts the
existing splitter unchanged and composes a private ``QStackedWidget`` to
swap in a placeholder page -- the same list/placeholder pattern already
used by ``IssuesView``/``DiagnosticsPanel`` for their own empty states, a
``QWidget`` wrapping a private stack rather than a stack subclass, so it
exposes only ``set_has_document`` and not the full ``QStackedWidget`` API.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSplitter, QStackedWidget, QVBoxLayout, QWidget

_EMPTY_STATE_TEXT = "No document open - open or create one on the Workspace page"

_SPLITTER_INDEX = 0
_EMPTY_INDEX = 1


class EditorPage(QWidget):
    """Hosts the editor splitter; shows an empty-state hint with no document."""

    def __init__(self, tree: QWidget, params: QWidget, inspector: QWidget) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        splitter = QSplitter()
        splitter.setObjectName("EditorSplitter")
        splitter.setHandleWidth(1)
        for panel in (tree, params, inspector):
            panel.setObjectName("Panel")
            splitter.addWidget(panel)
        splitter.setSizes([240, 280, 680])
        # Without a floor, dragging a handle can crush a pane to nothing --
        # its labels would elide at width 0 rather than stop shrinking.
        tree.setMinimumWidth(160)
        params.setMinimumWidth(200)
        inspector.setMinimumWidth(280)
        self._stack.addWidget(splitter)  # _SPLITTER_INDEX

        self._placeholder = QLabel(_EMPTY_STATE_TEXT)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # _EMPTY_INDEX

        layout.addWidget(self._stack)
        self.set_has_document(False)

    def set_has_document(self, has_document: bool) -> None:
        """Show the splitter when a document is loaded, else the empty-state hint."""
        self._stack.setCurrentIndex(_SPLITTER_INDEX if has_document else _EMPTY_INDEX)
