"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``DiagnosticsPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
``open_requested``/``new_requested``/``file_dropped`` signals to the existing
guarded open/new flows, and calls ``refresh`` wherever it refreshes the
other views.

This is the activity-bar page shell, the inline New model-chooser and
drag-and-drop file opening.

The Diagnostics page's own anatomy is reused here -- a shaded fixed-width
actions rail (Open buttons + the New chooser) beside a white pane holding
the document and reference as banded-header group boxes. The earlier
floating-cards-on-a-canvas treatment is gone: no page background tint, no
vertically centred actions card, no solid validity pill.
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
from .group_box import GroupBox
from .style import ERROR, OK, WARNING
from .titles import panel_title

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

# Kept in sync with the Open/Export dialog filter ("BPX (*.json *.yaml *.yml)")
# in main_window.py; both describe the same supported set of file extensions.
SUPPORTED_BPX_EXTENSIONS = (".json", ".yaml", ".yml")

#: The actions rail's fixed width. Wider than the content strictly needs
#: (explicit user call): the rail/pane divider sits further right so the
#: centred document column doesn't leave a lopsided field on its right.
_RAIL_WIDTH = 340

#: The document column's fixed width -- one width for both group boxes so
#: the main and reference cards always read as the same component.
_CARD_COLUMN_WIDTH = 440


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
    open_library_requested = Signal()
    new_from_file_requested = Signal()
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
        """The shaded actions rail: the Open button over the New chooser.
        No heading over the buttons -- they name themselves (an "Actions"
        label over buttons is noise). Reference docking lives on the
        reference card itself, not here: the card is the reference
        feature's home, so its affordances sit where their result appears."""
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
        # The boxes live in one fixed-width column centred between the rail
        # and the window edge (explicit user call): left-hugging the divider
        # left an awkward empty field on the column's right.
        pane_layout = QHBoxLayout(pane)
        pane_layout.setContentsMargins(24, 24, 24, 24)
        column = QWidget()
        column.setFixedWidth(_CARD_COLUMN_WIDTH)
        column_layout = QVBoxLayout(column)
        column_layout.setContentsMargins(0, 0, 0, 0)
        column_layout.setSpacing(16)

        self._info_card = self._build_info_card()
        column_layout.addWidget(self._info_card)

        self._reference_tile = self._build_reference_card()
        column_layout.addWidget(self._reference_tile)

        column_layout.addStretch(1)
        pane_layout.addStretch(1)
        pane_layout.addWidget(column)
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
        """The main-document group box: banded header naming the role
        plainly ("Main document" -- "main" is the app's one role word, per
        the UI copy rule; no tag, the caps MAIN tag read as noise), then
        identity, validity, contents."""
        box = GroupBox("Main document")
        body = box.body_layout

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
        rows -- so the two read as the same component. Its header mirrors the
        primary box's format ("Reference document"); the reference-specific
        marks are that title's purple, the small light Read-only tag on the
        band, and the band's own subtle purple tint
        (``QWidget#ReferenceGroupBoxHeader``) -- the card must never read
        louder than the document's own."""
        self._reference_tag = QLabel("Read-only")
        self._reference_tag.setObjectName("ReferenceReadOnlyTag")
        box = GroupBox(
            "Reference document",
            variant="reference",
            title_object_name="ReferenceHeading",
            trailing=self._reference_tag,
        )
        body = box.body_layout

        self._reference_filename = QLabel()
        self._reference_filename.setObjectName("WorkspaceCardTitle")
        self._reference_filename.setWordWrap(True)
        body.addWidget(self._reference_filename)

        badge_row, self._reference_dot, self._reference_badge = self._build_validity_row()
        body.addLayout(badge_row)

        self._reference_form, self._reference_fields = self._build_kv_form(("Model", "Contents"))
        body.addLayout(self._reference_form)

        # Make main comes first, at the same plain weight as Remove --
        # neither is styled as a loud action, so the card still never
        # reads louder than the document card above it.
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

        # The dock affordances: with no reference docked the card is the
        # reference library's front door --
        # the teaching line over these two buttons. Both buttons stay while
        # a reference is docked: docking over one replaces it silently (a
        # snapshot is disposable), the flow the reference-open tests pin.
        self._reference_empty_text = QLabel(
            "No reference docked. Compare the main document against a "
            "published set or a file."
        )
        self._reference_empty_text.setObjectName("ReferenceEmptyStateText")
        self._reference_empty_text.setWordWrap(True)
        body.addWidget(self._reference_empty_text)

        dock_row = QHBoxLayout()
        dock_row.setSpacing(8)
        self._reference_library_button = QPushButton("From the reference library…")
        self._reference_library_button.setObjectName("ReferenceFromLibrary")
        self._reference_library_button.clicked.connect(self.open_library_requested)
        dock_row.addWidget(self._reference_library_button)
        self._open_reference_button = QPushButton("Open BPX file…")
        self._open_reference_button.setObjectName("WorkspaceOpenReference")
        self._open_reference_button.clicked.connect(self.open_reference_requested)
        dock_row.addWidget(self._open_reference_button)
        dock_row.addStretch(1)
        body.addLayout(dock_row)

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

        heading = panel_title("New")
        layout.addWidget(heading)

        for model in SUPPORTED_MODELS:
            layout.addWidget(self._build_model_option(model))

        divider = QFrame()
        divider.setObjectName("WorkspaceRailDivider")
        divider.setFixedHeight(1)
        layout.addSpacing(2)
        layout.addWidget(divider)
        layout.addSpacing(2)
        layout.addWidget(self._build_new_from_file_option())

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

    def _build_new_from_file_option(self) -> QWidget:
        """The chooser's non-model row, below its own divider: clone an existing
        file into a fresh unsaved document with the origin docked as the
        reference ("New from source"). Same row anatomy as the model options --
        the ``modelOption`` property carries the shared flat-row styling."""
        row = QWidget()
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(0)

        self._new_from_file_button = QPushButton("From existing file…")
        self._new_from_file_button.setObjectName("NewFromFile")
        self._new_from_file_button.setProperty("modelOption", True)
        self._new_from_file_button.clicked.connect(self.new_from_file_requested)
        row_layout.addWidget(self._new_from_file_button)

        self._new_from_file_descriptor = QLabel(
            "Start from a copy · the file docks as reference"
        )
        self._new_from_file_descriptor.setObjectName("NewChooserDescriptor")
        self._new_from_file_descriptor.setWordWrap(True)
        row_layout.addWidget(self._new_from_file_descriptor)

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
        from ``main_window._refresh_all``, not re-derived here from
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
            self._set_form_rows_visible(self._info_form, False)
            return

        self._info_title.setEnabled(True)
        identity = document.identity
        self._info_title.setText(identity.title or "Untitled document")
        self._set_form_rows_visible(self._info_form, True)
        self._info_fields["Model"].setText(identity.model or "-")
        self._info_fields["BPX version"].setText(identity.bpx_version or "-")
        self._info_fields["File"].setText(filename or "-")
        self._info_fields["State"].setText("Modified" if dirty else "Saved")
        self._info_fields["Contents"].setText(
            f"{document.section_count} sections · {document.parameter_count} parameters"
        )
        self._set_validity_badge(error_count, warning_count)

    def _set_reference(self, reference: ReferenceSnapshot | None) -> None:
        """Populate the reference card for the docked or empty state.

        The card is always visible, even with no reference docked, since
        it is then the reference library's front door -- the teaching line
        over the two dock buttons. The dock buttons stay in both states --
        see ``_build_reference_card``."""
        docked = reference is not None
        self._reference_empty_text.setVisible(not docked)
        self._reference_filename.setVisible(docked)
        self._reference_dot.setVisible(docked)
        self._reference_badge.setVisible(docked)
        self._set_form_rows_visible(self._reference_form, docked)
        self._reference_remove_button.setVisible(docked)
        # "Make main" promotes a file on disk; a bundled library set has no
        # path to promote, so the button disappears rather than sit as a
        # disabled placeholder (the standing no-dead-controls rule).
        self._reference_make_main_button.setVisible(
            docked and reference.path is not None
        )
        if reference is None:
            return
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

    @staticmethod
    def _set_form_rows_visible(form: QFormLayout, visible: bool) -> None:
        for row in range(form.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                item = form.itemAt(row, role)
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
