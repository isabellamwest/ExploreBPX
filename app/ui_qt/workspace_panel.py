"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``ValidationPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
``open_requested`` signal to the existing guarded open flow, and calls
``refresh`` wherever it refreshes the other views.

This is the activity-bar page shell only (Step 7 of the top-bar/workspace
redesign). The New model-chooser and drag-and-drop land in later steps and
are deliberately not stubbed here.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget

from core.document import BPXDocument

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"


class WorkspacePanel(QWidget):
    """Workspace-level actions (Open) plus current-document identity/state."""

    open_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._open_button = QPushButton("Open File")
        self._open_button.clicked.connect(self.open_requested)
        layout.addWidget(self._open_button, 0)

        self._info = QLabel()
        self._info.setObjectName("WorkspaceInfo")
        self._info.setWordWrap(True)
        layout.addWidget(self._info, 0)

        layout.addStretch(1)

        self.refresh(None, None, False)

    def refresh(self, document: BPXDocument | None, filename: str | None, dirty: bool) -> None:
        """Update the info panel from the active document's identity and file state.

        Identity (Title/Model/BPX version) is read only through
        ``document.identity``; ``filename``/``dirty`` are caller-supplied
        facts derived from the active session, never from the raw dict.
        """
        if document is None:
            self._info.setText(_INFO_PANEL_EMPTY_STATE_TEXT)
            return
        identity = document.identity
        lines = [
            f"Title: {identity.title or '—'}",
            f"Model: {identity.model or '—'}",
            f"BPX version: {identity.bpx_version or '—'}",
            f"File: {filename or '—'}",
            f"State: {'Modified' if dirty else 'Saved'}",
        ]
        self._info.setText("\n".join(lines))
