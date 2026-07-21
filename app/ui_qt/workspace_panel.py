"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``DiagnosticsPanel``: a self-contained widget that owns
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
from state.reference_snapshot import ReferenceSnapshot

from . import style
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


def _reference_validity_text(errors: int, warnings: int) -> tuple[str, str]:
    """The reference tile's validity line and colour.

    Only two colours are used here (never ``ERROR``): a docked reference is
    read-only and never blocks anything, so its tile never needs the same
    alarm colour as the main document's own invalid state."""
    if not errors and not warnings:
        return "valid", OK
    parts = []
    if errors:
        parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
    if warnings:
        parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
    return " · ".join(parts), WARNING


class WorkspacePanel(QWidget):
    """Workspace-level actions (Open, New) plus current-document identity/state."""

    open_requested = Signal()
    new_requested = Signal(str)  # model name
    file_dropped = Signal(str)  # local file path
    open_reference_requested = Signal()
    remove_reference_requested = Signal()

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
        self._open_reference_button = QPushButton("Open File as Reference…")
        self._open_reference_button.setObjectName("WorkspaceOpenReference")
        self._open_reference_button.clicked.connect(self.open_reference_requested)
        left.addWidget(self._open_reference_button, 0, Qt.AlignLeft)
        left.addWidget(self._build_new_chooser(), 0)
        left.addStretch(1)
        layout.addLayout(left, 1)

        # The document card is a compact, top-aligned tile, not a page-filling
        # panel: its height follows its content and its width is capped. The
        # future multi-document Workspace stacks one tile per document in this
        # column, so the single tile today already has that shape. The
        # reference heading/tile sit below it, both hidden when no reference
        # is docked -- no empty-state placeholder (explicit user decision).
        right = QVBoxLayout()
        right.setSpacing(8)
        heading = QLabel("Current document")
        heading.setObjectName("Heading")
        right.addWidget(heading)
        self._info_card = self._build_info_card()
        self._info_card.setMaximumWidth(420)
        right.addWidget(self._info_card, 0, Qt.AlignTop)

        self._reference_heading = QLabel("Reference")
        self._reference_heading.setObjectName("Heading")
        right.addWidget(self._reference_heading)
        self._reference_tile = self._build_reference_tile()
        self._reference_tile.setMaximumWidth(420)
        right.addWidget(self._reference_tile, 0, Qt.AlignTop)

        right.addStretch(1)
        layout.addLayout(right, 1)

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
        # Explicit left alignment throughout: macOS's native form style centres
        # the rows and right-aligns the labels, which reads as scattered text
        # rather than a keyed record. Growing fields keep a long value ("11
        # sections · 44 parameters") fully visible instead of squeezed.
        self._info_form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        self._info_form.setLabelAlignment(Qt.AlignLeft)
        self._info_form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
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
        return card

    def _build_reference_tile(self) -> QWidget:
        """The docked-reference tile: a compact, lighter-weight sibling of
        the current-document card (see ``QFrame#ReferenceTile`` in
        ``style.py`` for the deliberately narrower visual treatment)."""
        tile = QFrame()
        tile.setObjectName("ReferenceTile")
        tile_layout = QVBoxLayout(tile)
        tile_layout.setContentsMargins(12, 10, 12, 10)
        tile_layout.setSpacing(4)

        self._reference_tag = QLabel("◇ REFERENCE · read-only")
        self._reference_tag.setObjectName("ReferenceTileTag")
        tile_layout.addWidget(self._reference_tag)

        self._reference_filename = QLabel()
        self._reference_filename.setObjectName("ReferenceTileFilename")
        self._reference_filename.setWordWrap(True)
        tile_layout.addWidget(self._reference_filename)

        self._reference_meta = QLabel()
        tile_layout.addWidget(self._reference_meta)

        self._reference_validity = QLabel()
        tile_layout.addWidget(self._reference_validity)

        self._reference_remove_button = QPushButton("Remove")
        self._reference_remove_button.setObjectName("ReferenceTileRemove")
        self._reference_remove_button.clicked.connect(self.remove_reference_requested)
        tile_layout.addWidget(self._reference_remove_button, 0, Qt.AlignLeft)

        return tile

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

    def refresh(
        self,
        document: BPXDocument | None,
        filename: str | None,
        dirty: bool,
        error_count: int = 0,
        warning_count: int = 0,
        reference: ReferenceSnapshot | None = None,
    ) -> None:
        """Update the info card and reference tile from current state.

        Identity (Title/Model/BPX version) and the section/parameter counts are
        read only through the document's own properties; ``filename``/``dirty``
        are caller-supplied facts derived from the active session, never from
        the raw dict. ``error_count``/``warning_count`` are likewise supplied
        by the caller -- the already-computed ``PartitionedIssues`` totals
        (decision G in ``main_window._refresh_all``), not re-derived here from
        ``document.error_count``/``warning_count``, so the pill can never
        disagree with the Diagnostics rail badge over an absorbed diagnostic.

        ``reference`` is independent of ``document``: a reference may be
        docked with no main document open, so its tile is updated regardless
        of which branch below runs.
        """
        self._set_reference(reference)

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
        self._info_fields["Model"].setText(identity.model or "-")
        self._info_fields["BPX version"].setText(identity.bpx_version or "-")
        self._info_fields["File"].setText(filename or "-")
        self._info_fields["State"].setText("Modified" if dirty else "Saved")
        self._info_fields["Contents"].setText(
            f"{document.section_count} sections · {document.parameter_count} parameters"
        )
        self._set_validity_badge(error_count, warning_count)

    def _set_reference(self, reference: ReferenceSnapshot | None) -> None:
        """Show/populate or hide the reference heading + tile.

        Both are hidden together when no reference is docked -- no
        empty-state placeholder (explicit user decision)."""
        if reference is None:
            self._reference_heading.hide()
            self._reference_tile.hide()
            return
        self._reference_heading.show()
        self._reference_tile.show()
        self._reference_filename.setText(reference.filename)
        self._reference_meta.setText(
            f"{reference.model or '-'} · {reference.section_count} sections · "
            f"{reference.parameter_count} parameters"
        )
        text, colour = _reference_validity_text(reference.error_count, reference.warning_count)
        self._reference_validity.setText(text)
        self._reference_validity.setStyleSheet(f"color: {colour};")

    def _set_validity_badge(self, errors: int, warnings: int) -> None:
        if not errors and not warnings:
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
        self._info_badge.setStyleSheet(style.validity_pill_qss(colour))
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
