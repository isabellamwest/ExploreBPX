"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``ValidationPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
``open_requested``/``new_requested``/``file_dropped`` signals to the existing
guarded open/new flows, and calls ``refresh`` wherever it refreshes the
other views.

This is the activity-bar page shell (Step 7), the inline New model-chooser
(Step 8) and drag-and-drop file opening (Step 9).
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.document import BPXDocument
from core.document_factory import SUPPORTED_MODELS

from .style import ERROR, OK, WARNING

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

# Kept in sync with the Open/Export dialog filter ("BPX (*.json *.yaml *.yml)")
# in main_window.py; both describe the same supported set of file extensions.
SUPPORTED_BPX_EXTENSIONS = (".json", ".yaml", ".yml")


def _first_supported_local_file(mime_data: QMimeData) -> Path | None:
    """The first local file in *mime_data* with a supported BPX extension.

    Returns ``None`` if there is no such file (no URLs, no local files, or
    none with a supported extension) -- callers treat that as "ignore".
    """
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.suffix.lower() in SUPPORTED_BPX_EXTENSIONS:
            return path
    return None


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
    file_dropped = Signal(str)  # local file path

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("Panel")
        self.setAcceptDrops(True)

        # Two columns: actions on the left (open + new-from-model), the current
        # document's details on the right. A single full-width Open button over
        # a stack of everything read awkwardly; splitting actions from data
        # makes each half legible on its own.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(24)

        left = QVBoxLayout()
        left.setSpacing(16)
        self._open_button = QPushButton("Open File…")
        self._open_button.setObjectName("WorkspaceOpen")
        self._open_button.clicked.connect(self.open_requested)
        left.addWidget(self._open_button, 0, Qt.AlignLeft)
        left.addWidget(self._build_new_chooser(), 0)
        left.addStretch(1)
        layout.addLayout(left, 1)

        layout.addWidget(self._build_info_card(), 1)

        self.refresh(None, None, False)

    def _build_info_card(self) -> QWidget:
        """The right-hand current-document card: identity, validity, contents."""
        card = QFrame()
        card.setObjectName("DocInfoCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 16, 16, 16)
        card_layout.setSpacing(10)

        self._info_title = QLabel()
        self._info_title.setObjectName("DocInfoTitle")
        self._info_title.setWordWrap(True)
        card_layout.addWidget(self._info_title)

        self._info_badge = QLabel()
        self._info_badge.setObjectName("DocInfoBadge")
        card_layout.addWidget(self._info_badge, 0, Qt.AlignLeft)

        self._info_form = QFormLayout()
        self._info_form.setContentsMargins(0, 4, 0, 0)
        self._info_form.setHorizontalSpacing(12)
        self._info_form.setVerticalSpacing(6)
        self._info_fields: dict[str, QLabel] = {}
        for key in ("Model", "BPX version", "File", "State", "Contents"):
            value = QLabel()
            value.setObjectName("DocInfoValue")
            value.setWordWrap(True)
            label = QLabel(f"{key}:")
            label.setObjectName("DocInfoKey")
            self._info_form.addRow(label, value)
            self._info_fields[key] = value
        card_layout.addLayout(self._info_form)
        card_layout.addStretch(1)
        return card

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
        """Update the info card from the active document's identity and state.

        Identity (Title/Model/BPX version) and the section/parameter counts are
        read only through the document's own properties; ``filename``/``dirty``
        are caller-supplied facts derived from the active session, never from
        the raw dict.
        """
        if document is None:
            self._info_title.setText(_INFO_PANEL_EMPTY_STATE_TEXT)
            self._info_title.setEnabled(False)
            self._info_badge.hide()
            for value in self._info_fields.values():
                value.setText("")
            self._set_form_visible(False)
            return

        self._info_title.setEnabled(True)
        identity = document.identity
        self._info_title.setText(identity.title or "Untitled document")
        self._set_form_visible(True)
        self._info_fields["Model"].setText(identity.model or "—")
        self._info_fields["BPX version"].setText(identity.bpx_version or "—")
        self._info_fields["File"].setText(filename or "—")
        self._info_fields["State"].setText("Modified" if dirty else "Saved")
        self._info_fields["Contents"].setText(
            f"{document.section_count} sections · {document.parameter_count} parameters"
        )
        self._set_validity_badge(document)

    def _set_validity_badge(self, document: BPXDocument) -> None:
        errors, warnings = document.error_count, document.warning_count
        if document.is_valid and not warnings:
            text, colour = "Valid", OK
        elif errors:
            parts = [f"{errors} error" + ("s" if errors != 1 else "")]
            if warnings:
                parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
            text, colour = ", ".join(parts), ERROR
        else:
            text, colour = (
                f"{warnings} warning" + ("s" if warnings != 1 else ""),
                WARNING,
            )
        self._info_badge.setText(text)
        self._info_badge.setStyleSheet(
            f"color: white; background: {colour}; padding: 2px 10px; border-radius: 3px;"
        )
        self._info_badge.show()

    def _set_form_visible(self, visible: bool) -> None:
        for row in range(self._info_form.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                item = self._info_form.itemAt(row, role)
                if item is not None and item.widget() is not None:
                    item.widget().setVisible(visible)

    # --- drag-and-drop ---------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        """Accept the drag only if it carries at least one supported local file."""
        if _first_supported_local_file(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        """Emit ``file_dropped`` for the first supported local file, if any.

        Single-document model: any additional dropped files are ignored.
        MainWindow owns what happens next (discard guard, then open).
        """
        path = _first_supported_local_file(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.file_dropped.emit(str(path))
