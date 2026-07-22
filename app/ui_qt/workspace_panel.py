"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``DiagnosticsPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
``open_requested``/``new_requested``/``file_dropped`` signals to the existing
guarded open/new flows, and calls ``refresh`` wherever it refreshes the
other views.

This is the activity-bar page shell (Step 7), the inline New model-chooser
(Step 8) and drag-and-drop file opening (Step 9).

Restyle (Concept A, signed 2026-07-22): the Diagnostics page's own anatomy,
reused -- a shaded fixed-width actions rail (Open buttons + the New chooser)
beside a white pane holding the document and reference as banded-header group
boxes. The earlier floating-cards-on-a-canvas treatment is gone: no page
background tint, no vertically centred actions card, no solid validity pill.
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

from . import icons
from .style import ERROR, OK, WARNING

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

# Kept in sync with the Open/Export dialog filter ("BPX (*.json *.yaml *.yml)")
# in main_window.py; both describe the same supported set of file extensions.
SUPPORTED_BPX_EXTENSIONS = (".json", ".yaml", ".yml")

#: The actions rail's fixed width -- sized so "Open File as Reference…" and
#: the longest model descriptor fit on one line at the app's 13px base font.
_RAIL_WIDTH = 248


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
    """The reference card's validity text and dot colour, matching the
    document badge's own wording and format exactly ("Valid", "2 errors,
    1 warning") with one deliberate exception: never ``ERROR`` red -- a
    docked reference is read-only and never blocks anything, so amber is
    as loud as its mark gets."""
    if not errors and not warnings:
        return "Valid", OK
    parts = []
    if errors:
        parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
    if warnings:
        parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
    return ", ".join(parts), WARNING


def _validity_dot_label() -> QLabel:
    """The small filled dot beside a validity line -- the shared dot family
    (:mod:`ui_qt.icons`), rendered as a rich-text ``<img>`` exactly like the
    Diagnostics strip chips, so the two surfaces can never drift. The text
    itself lives in a separate plain ``QLabel`` (the ``_info_badge``/
    ``_reference_badge`` the tests and driver read via ``text()``)."""
    label = QLabel()
    label.setObjectName("ValidityDot")
    return label


class WorkspacePanel(QWidget):
    """Workspace-level actions (Open, New) plus current-document identity/state."""

    open_requested = Signal()
    new_requested = Signal(str)  # model name
    file_dropped = Signal(str)  # local file path
    open_reference_requested = Signal()
    remove_reference_requested = Signal()
    make_main_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        # A plain QWidget subclass ignores stylesheet backgrounds unless told
        # to paint them (same note as the Diagnostics strip), so without
        # WA_StyledBackground the page's white ground silently never draws.
        self.setObjectName("WorkspacePage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)

        # Rail beside pane, edge to edge -- the Diagnostics page's structure.
        # The rail is a full-height surface, so the page has no floating card
        # and no dead field: empty space falls inside the two surfaces.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_rail())
        layout.addWidget(self._build_pane(), 1)

        self.refresh(None, None, False)

    def _build_rail(self) -> QWidget:
        """The shaded actions rail: Open/Open-as-reference buttons over the
        New chooser. No heading over the buttons -- they name themselves
        (explicit user call: an "Actions" label over buttons is noise)."""
        rail = QWidget()
        rail.setObjectName("WorkspaceRail")
        rail.setAttribute(Qt.WA_StyledBackground, True)
        rail.setFixedWidth(_RAIL_WIDTH)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(12, 12, 12, 12)
        rail_layout.setSpacing(6)

        self._open_button = QPushButton("Open File…")
        self._open_button.setObjectName("WorkspaceOpen")
        self._open_button.clicked.connect(self.open_requested)
        rail_layout.addWidget(self._open_button)
        self._open_reference_button = QPushButton("Open File as Reference…")
        self._open_reference_button.setObjectName("WorkspaceOpenReference")
        self._open_reference_button.clicked.connect(self.open_reference_requested)
        rail_layout.addWidget(self._open_reference_button)

        divider = QFrame()
        divider.setObjectName("WorkspaceRailDivider")
        divider.setFixedHeight(1)
        rail_layout.addSpacing(6)
        rail_layout.addWidget(divider)
        rail_layout.addSpacing(6)

        rail_layout.addWidget(self._build_new_chooser())
        rail_layout.addStretch(1)
        return rail

    def _build_pane(self) -> QWidget:
        """The white pane: the current-document and reference group boxes,
        hanging from the top like every other page's content. The future
        multi-document Workspace stacks one box per document here, so the
        single box today already has that shape. The reference box is hidden
        when no reference is docked -- no empty-state placeholder (explicit
        user decision)."""
        pane = QWidget()
        pane.setObjectName("WorkspacePane")
        pane.setAttribute(Qt.WA_StyledBackground, True)
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(24, 24, 24, 24)
        pane_layout.setSpacing(16)

        self._info_card = self._build_info_card()
        self._info_card.setMaximumWidth(420)
        pane_layout.addWidget(self._info_card, 0, Qt.AlignTop)

        self._reference_tile = self._build_reference_card()
        self._reference_tile.setMaximumWidth(420)
        pane_layout.addWidget(self._reference_tile, 0, Qt.AlignTop)

        pane_layout.addStretch(1)
        return pane

    @staticmethod
    def _build_kv_form(keys: tuple[str, ...]) -> tuple[QFormLayout, dict[str, QLabel]]:
        """A card's keyed record rows -- one shared recipe so the document
        and reference cards can never drift apart. Explicit left alignment
        throughout: macOS's native form style centres the rows and
        right-aligns the labels, which reads as scattered text rather than
        a keyed record. Growing fields keep a long value ("11 sections · 44
        parameters") fully visible instead of squeezed."""
        form = QFormLayout()
        form.setContentsMargins(0, 4, 0, 0)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(6)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        fields: dict[str, QLabel] = {}
        for key in keys:
            value = QLabel()
            value.setObjectName("WorkspaceCardValue")
            value.setWordWrap(True)
            label = QLabel(f"{key}:")
            label.setObjectName("WorkspaceCardKey")
            form.addRow(label, value)
            fields[key] = value
        return form, fields

    @staticmethod
    def _build_group_box(header: QWidget, frame_name: str, header_name: str) -> tuple[QFrame, QVBoxLayout]:
        """One banded-header group box (the Diagnostics group-box language):
        a bordered rounded frame whose first row is a shaded header band,
        returning the frame and its body layout for the caller to fill."""
        box = QFrame()
        box.setObjectName(frame_name)
        box_layout = QVBoxLayout(box)
        box_layout.setContentsMargins(0, 0, 0, 0)
        box_layout.setSpacing(0)
        header.setObjectName(header_name)
        header.setAttribute(Qt.WA_StyledBackground, True)
        box_layout.addWidget(header)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(12, 10, 12, 12)
        body_layout.setSpacing(8)
        box_layout.addWidget(body)
        return box, body_layout

    @staticmethod
    def _build_header_band(title_label: QLabel, trailing_label: QLabel) -> QWidget:
        header = QWidget()
        band = QHBoxLayout(header)
        band.setContentsMargins(12, 5, 12, 5)
        band.setSpacing(8)
        band.addWidget(title_label)
        band.addStretch(1)
        band.addWidget(trailing_label)
        return header

    def _build_validity_row(self) -> tuple[QHBoxLayout, QLabel, QLabel]:
        """The dot-plus-text validity line: a coloured mark from the shared
        dot family beside a plain-text label. Two widgets on purpose -- the
        text label keeps returning the bare wording ("3 warnings") from
        ``text()``, which the tests and the driver read."""
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        dot = _validity_dot_label()
        text = QLabel()
        text.setObjectName("DocInfoBadge")
        row.addWidget(dot, 0, Qt.AlignVCenter)
        row.addWidget(text, 0, Qt.AlignVCenter)
        row.addStretch(1)
        return row, dot, text

    def _build_info_card(self) -> QWidget:
        """The current-document group box: banded header carrying the role
        ("Current document" · MAIN), then identity, validity, contents."""
        title = QLabel("Current document")
        title.setObjectName("WorkspaceGroupBoxTitle")
        role = QLabel("MAIN")
        role.setObjectName("WorkspaceRoleTag")
        box, body = self._build_group_box(
            self._build_header_band(title, role),
            "WorkspaceGroupBox",
            "WorkspaceGroupBoxHeader",
        )

        self._info_title = QLabel()
        self._info_title.setObjectName("WorkspaceCardTitle")
        self._info_title.setWordWrap(True)
        body.addWidget(self._info_title)

        badge_row, self._info_dot, self._info_badge = self._build_validity_row()
        body.addLayout(badge_row)

        self._info_form, self._info_fields = self._build_kv_form(
            ("Model", "BPX version", "File", "State", "Contents")
        )
        body.addLayout(self._info_form)
        return box

    def _build_reference_card(self) -> QWidget:
        """The docked-reference group box: the exact anatomy of the
        current-document box -- header band, title, validity line, key/value
        rows -- so the two read as the same component. The reference-specific
        marks are the purple "Reference" header title, the small purple
        Read-only tag on the band, and the band's own subtle purple tint
        (``QWidget#ReferenceGroupBoxHeader``) -- the card must never read
        louder than the document's own."""
        self._reference_heading = QLabel("Reference")
        self._reference_heading.setObjectName("ReferenceHeading")
        self._reference_tag = QLabel("Read-only")
        self._reference_tag.setObjectName("ReferenceReadOnlyTag")
        box, body = self._build_group_box(
            self._build_header_band(self._reference_heading, self._reference_tag),
            "ReferenceGroupBox",
            "ReferenceGroupBoxHeader",
        )

        self._reference_filename = QLabel()
        self._reference_filename.setObjectName("WorkspaceCardTitle")
        self._reference_filename.setWordWrap(True)
        body.addWidget(self._reference_filename)

        badge_row, self._reference_dot, self._reference_badge = self._build_validity_row()
        body.addLayout(badge_row)

        self._reference_form, self._reference_fields = self._build_kv_form(("Model", "Contents"))
        body.addLayout(self._reference_form)

        # Make main comes first (M4's signed entry point) at the same plain
        # weight as Remove -- neither is styled as a loud action, so the
        # card still never reads louder than the document card above it.
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        self._reference_make_main_button = QPushButton("Make main")
        self._reference_make_main_button.setObjectName("ReferenceTileMakeMain")
        self._reference_make_main_button.clicked.connect(self.make_main_requested)
        action_row.addWidget(self._reference_make_main_button)
        self._reference_remove_button = QPushButton("Remove")
        self._reference_remove_button.setObjectName("ReferenceTileRemove")
        self._reference_remove_button.clicked.connect(self.remove_reference_requested)
        action_row.addWidget(self._reference_remove_button)
        action_row.addStretch(1)
        body.addLayout(action_row)

        return box

    def _build_new_chooser(self) -> QWidget:
        """Inline "New" surface: one flat, name-first row per supported model
        with its descriptor beneath -- list-row language, sized to the rail.

        Rendered directly on the page (not a dialog or dropdown) so the
        Workspace page's layout is used as intended.
        """
        container = QWidget()
        container.setObjectName("NewChooser")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        heading = QLabel("NEW")
        heading.setObjectName("NewChooserHeading")
        layout.addWidget(heading)

        for model in SUPPORTED_MODELS:
            layout.addWidget(self._build_model_option(model))

        return container

    def _build_model_option(self, model: str) -> QWidget:
        """One chooser row: the model name as a flat bold button over a muted
        descriptor label. The button keeps its plain ``text()`` (the model
        name) and ``NewButton_{model}`` objectName -- the seam the tests and
        driver click -- while the ``modelOption`` dynamic property carries the
        shared flat-row styling (QSS cannot prefix-match objectNames)."""
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        button = QPushButton(model)
        button.setObjectName(f"NewButton_{model}")
        button.setProperty("modelOption", True)
        button.clicked.connect(lambda: self.new_requested.emit(model))
        row_layout.addWidget(button)

        descriptor = QLabel(_MODEL_DESCRIPTORS.get(model, model))
        descriptor.setObjectName("NewChooserDescriptor")
        descriptor.setWordWrap(True)
        row_layout.addWidget(descriptor)

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
        ``document.error_count``/``warning_count``, so the badge can never
        disagree with the Diagnostics rail badge over an absorbed diagnostic.

        ``reference`` is independent of ``document``: a reference may be
        docked with no main document open, so its tile is updated regardless
        of which branch below runs.
        """
        self._set_reference(reference)

        if document is None:
            self._info_title.setText(_INFO_PANEL_EMPTY_STATE_TEXT)
            self._info_title.setEnabled(False)
            self._info_dot.hide()
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
        """Show/populate or hide the reference group box.

        Hidden entirely when no reference is docked -- no empty-state
        placeholder (explicit user decision). The heading lives on the box's
        own header band; it is still shown/hidden alongside so its visibility
        keeps answering "is the reference surface on screen"."""
        if reference is None:
            self._reference_heading.hide()
            self._reference_tile.hide()
            return
        self._reference_heading.show()
        self._reference_tile.show()
        self._reference_filename.setText(reference.filename)
        self._reference_fields["Model"].setText(reference.model or "-")
        self._reference_fields["Contents"].setText(
            f"{reference.section_count} sections · {reference.parameter_count} parameters"
        )
        text, colour = _reference_validity_text(reference.error_count, reference.warning_count)
        self._reference_badge.setText(text)
        self._reference_dot.setText(icons.html_img(icons.DOT, color=colour))

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
        self._info_dot.setText(icons.html_img(icons.DOT, color=colour))
        self._info_dot.show()
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
