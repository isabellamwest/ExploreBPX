"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``ValidationPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
``open_requested``/``new_requested`` signals to the existing guarded
open/new flows, and calls ``refresh`` wherever it refreshes the other views.

This is the activity-bar page shell (Step 7) plus the inline New
model-chooser (Step 8). Drag-and-drop lands in a later step.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from core.document import BPXDocument
from core.document_factory import SUPPORTED_MODELS

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

# Short, factual one-line descriptors. A model without an entry here still
# renders correctly (name only) so this mapping can lag SUPPORTED_MODELS
# without breaking the chooser.
_MODEL_DESCRIPTORS: dict[str, str] = {
    "SPM": "Single Particle Model",
    "SPMe": "Single Particle Model with electrolyte",
    "DFN": "Doyle-Fuller-Newman model",
    "Partial": "Partial parameterisation; sections are all optional",
}


class WorkspacePanel(QWidget):
    """Workspace-level actions (Open, New) plus current-document identity/state."""

    open_requested = Signal()
    new_requested = Signal(str)  # model name

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        self._open_button = QPushButton("Open File")
        self._open_button.clicked.connect(self.open_requested)
        layout.addWidget(self._open_button, 0)

        layout.addWidget(self._build_new_chooser(), 0)

        self._info = QLabel()
        self._info.setObjectName("WorkspaceInfo")
        self._info.setWordWrap(True)
        layout.addWidget(self._info, 0)

        layout.addStretch(1)

        self.refresh(None, None, False)

    def _build_new_chooser(self) -> QWidget:
        """Inline "New" surface: one labelled button per supported model.

        Rendered directly on the page (not a dialog or dropdown) so the
        Workspace page's roomy layout is used as intended.
        """
        container = QWidget()
        container.setObjectName("NewChooser")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        heading = QLabel("New")
        heading.setObjectName("NewChooserHeading")
        layout.addWidget(heading)

        for model in SUPPORTED_MODELS:
            layout.addWidget(self._build_model_option(model))

        return container

    def _build_model_option(self, model: str) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(12)

        button = QPushButton(model)
        button.setObjectName(f"NewButton_{model}")
        button.clicked.connect(lambda: self.new_requested.emit(model))
        row_layout.addWidget(button, 0)

        descriptor = _MODEL_DESCRIPTORS.get(model, model)
        label = QLabel(descriptor)
        label.setObjectName("NewChooserDescriptor")
        row_layout.addWidget(label, 1)

        return row

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
