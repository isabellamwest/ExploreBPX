"""Workspace page: workspace-level actions and the current-document info panel.

Peer of ``TreePanel``/``DiagnosticsPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
``open_requested``/``new_requested``/``file_dropped`` signals to the existing
guarded open/new flows, and calls ``refresh`` wherever it refreshes the
other views.

This is the activity-bar page shell, the inline New model-chooser and
drag-and-drop file opening.

The Diagnostics page's actions-rail anatomy is reused here -- a shaded
fixed-width rail (Open buttons + the New chooser) beside a white pane. The
pane itself (Phase 3) is a full-width whitespace-structured page: two
stacked, borderless tinted section washes (``group_box.TintedSection``),
top-aligned, with a 16px white gap between them and the tail stretch left
white. No lines anywhere in the pane -- no hairlines, borders, rounded
corners or shadows; the bordered ``GroupBox`` chrome used elsewhere in the
app is not used on this page. The earlier fixed-width centred card column
is gone, and before that the floating-cards-on-a-canvas treatment (no page
background tint, no vertically centred actions card, no solid validity
pill).
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
from state.app_state import REFERENCE_PIN_CAP

from . import icons
from .group_box import TintedSection
from .reference_identity import ReferencePin, badge_label
from .style import ERROR, OK, WARNING
from . import typography
from .typography import panel_title

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

# Kept in sync with the Open/Export dialog filter ("BPX (*.json *.yaml *.yml)")
# in main_window.py; both describe the same supported set of file extensions.
SUPPORTED_BPX_EXTENSIONS = (".json", ".yaml", ".yml")

#: The actions rail's fixed width (explicit user call): wider than the
#: New chooser's rows strictly need, so the rail/pane divider sits further
#: right than the bare minimum.
_RAIL_WIDTH = 340

#: The white gap between the main and reference tinted sections.
_SECTION_GAP = 16


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
    """The reference section's validity text and dot colour, matching the
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
    pin-detail labels the tests and driver read via ``text()``)."""
    label = QLabel()
    label.setObjectName("ValidityDot")
    return label


class _ReferencePinRow(QFrame):
    """One pinned reference's row in the References section (design rule 1).

    Collapsed: badge, name, model, Remove -- deliberately no validity dot;
    the full record (origin, validity spelled out beside its dot, model and
    BPX version, contents, citation or file path) lives in the expandable
    detail, so the dot can never be misread at a glance. Rows are rebuilt
    wholesale on every refresh (never mutated in place), so no stale button
    connection can survive a pin change; expansion state is the panel's to
    remember across rebuilds.
    """

    remove_requested = Signal()
    toggle_requested = Signal()

    def __init__(self, pin: ReferencePin, expanded: bool) -> None:
        super().__init__()
        self.setObjectName("ReferencePinRow")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        header = QWidget()
        header.setObjectName("ReferencePinHeader")
        header.setCursor(Qt.PointingHandCursor)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(8, 5, 8, 5)
        header_layout.setSpacing(8)
        header_layout.addWidget(badge_label(pin))
        name = QLabel(pin.name)
        name.setObjectName("ReferencePinName")
        name.setFont(typography.semibold(name.font()))
        header_layout.addWidget(name)
        model = QLabel(pin.snapshot.model or "-")
        model.setObjectName("ReferencePinModel")
        header_layout.addWidget(model)
        header_layout.addStretch(1)
        self._remove_button = QPushButton("Remove")
        self._remove_button.setObjectName("ReferencePinRemove")
        self._remove_button.setFlat(True)
        self._remove_button.setCursor(Qt.PointingHandCursor)
        self._remove_button.clicked.connect(self.remove_requested)
        header_layout.addWidget(self._remove_button)
        self._chevron = QLabel("▾" if expanded else "▸")
        self._chevron.setObjectName("ReferencePinChevron")
        header_layout.addWidget(self._chevron)
        # The whole header toggles the detail; the Remove button consumes
        # its own clicks before they reach the header.
        header.mousePressEvent = lambda event: self.toggle_requested.emit()
        layout.addWidget(header)

        self._detail = self._build_detail(pin)
        self._detail.setVisible(expanded)
        layout.addWidget(self._detail)

    @staticmethod
    def _build_detail(pin: ReferencePin) -> QWidget:
        """The expanded record: keyed rows in the section's shared form
        style. Row set varies by origin -- Citation for a library set (when
        its file carries one), File path for a file reference."""
        snapshot = pin.snapshot
        detail = QFrame()
        detail.setObjectName("ReferencePinDetail")
        form = QFormLayout(detail)
        form.setContentsMargins(36, 4, 8, 8)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(4)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        def add_row(key: str, widget: QWidget) -> None:
            label = QLabel(f"{key}:")
            label.setObjectName("WorkspaceCardKey")
            form.addRow(label, widget)

        def add_text_row(key: str, text: str, object_name: str) -> None:
            value = QLabel(text)
            value.setObjectName(object_name)
            value.setWordWrap(True)
            add_row(key, value)

        origin = (
            "Reference library · PyBaMM" if snapshot.set_id is not None else "File on disk"
        )
        add_text_row("Origin", origin, "ReferencePinOrigin")

        validity = QWidget()
        validity_layout = QHBoxLayout(validity)
        validity_layout.setContentsMargins(0, 0, 0, 0)
        validity_layout.setSpacing(6)
        text, colour = _reference_validity_text(snapshot.error_count, snapshot.warning_count)
        dot = _validity_dot_label()
        dot.setText(icons.html_img(icons.DOT, color=colour))
        validity_layout.addWidget(dot, 0, Qt.AlignVCenter)
        validity_text = QLabel(text)
        validity_text.setObjectName("ReferencePinValidity")
        validity_layout.addWidget(validity_text, 0, Qt.AlignVCenter)
        validity_layout.addStretch(1)
        add_row("Validity", validity)

        model_text = snapshot.model or "-"
        if snapshot.bpx_version:
            model_text = f"{model_text} · BPX {snapshot.bpx_version}"
        add_text_row("Model", model_text, "ReferencePinDetailModel")
        add_text_row(
            "Contents",
            f"{snapshot.section_count} sections · {snapshot.parameter_count} parameters",
            "ReferencePinContents",
        )
        if snapshot.set_id is not None:
            if snapshot.citation:
                add_text_row("Citation", snapshot.citation, "ReferencePinCitation")
        elif snapshot.path is not None:
            # Middle-shortened textually (a path has no spaces, so word wrap
            # breaks mid-string and overflows the row); the full path stays
            # one hover away.
            full = str(snapshot.path)
            shown = full if len(full) <= 60 else f"{full[:20]}…{full[-39:]}"
            path_value = QLabel(shown)
            path_value.setObjectName("ReferencePinPath")
            path_value.setToolTip(full)
            add_row("File path", path_value)
        return detail

    def set_expanded(self, expanded: bool) -> None:
        self._detail.setVisible(expanded)
        self._chevron.setText("▾" if expanded else "▸")


class WorkspacePanel(QWidget):
    """Workspace-level actions (Open, New) plus current-document identity/state."""

    open_requested = Signal()
    new_requested = Signal(str)  # model name
    file_dropped = Signal(str)  # local file path
    open_reference_requested = Signal()
    open_library_requested = Signal()
    new_from_file_requested = Signal()
    #: Carries the pin's ``ReferenceSnapshot`` -- ``AppState.remove_reference``
    #: removes by snapshot identity, so the panel names exactly which pin.
    remove_reference_requested = Signal(object)

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
        reference section itself, not here: the section is the reference
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
        """The white pane: the main-document and reference tinted sections,
        stacked full-width from the top, a 16px white gap between them and
        the tail stretch left white (nothing expands to fill the pane). The
        future multi-document Workspace stacks one section per document
        here, so the single section today already has that shape. The
        reference section is always shown, even with no reference docked --
        no empty-state placeholder is needed since its body is itself the
        reference library's front door."""
        pane = QWidget()
        pane.setObjectName("WorkspacePane")
        pane.setAttribute(Qt.WA_StyledBackground, True)
        pane_layout = QVBoxLayout(pane)
        pane_layout.setContentsMargins(0, 0, 0, 0)
        pane_layout.setSpacing(0)

        self._info_section = self._build_info_section()
        pane_layout.addWidget(self._info_section)

        pane_layout.addSpacing(_SECTION_GAP)

        self._reference_section = self._build_reference_section()
        pane_layout.addWidget(self._reference_section)

        pane_layout.addStretch(1)
        return pane

    @staticmethod
    def _build_kv_form(keys: tuple[str, ...]) -> tuple[QFormLayout, dict[str, QLabel]]:
        """A section's keyed record rows -- one shared recipe so the document
        and reference sections can never drift apart. Explicit left alignment
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

    def _build_validity_suffix(self) -> tuple[QWidget, QLabel, QLabel]:
        """The main section's title-row suffix: the same dot-plus-text
        validity mark as :meth:`_build_validity_row`, wrapped in a plain
        widget (``TintedSection.suffix`` takes a widget, not a layout) and
        sized to its own content -- no trailing stretch, since it sits
        compactly after the title row's own stretch rather than filling a
        full-width body row."""
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        dot = _validity_dot_label()
        text = QLabel()
        text.setObjectName("DocInfoBadge")
        row.addWidget(dot, 0, Qt.AlignVCenter)
        row.addWidget(text, 0, Qt.AlignVCenter)
        return widget, dot, text

    def _build_info_section(self) -> QWidget:
        """The main-document tinted section: caps title naming the role
        plainly ("Main document" -- "main" is the app's one role word, per
        the UI copy rule), its validity summary in the title row's suffix,
        then identity and contents in the body."""
        suffix, self._info_dot, self._info_badge = self._build_validity_suffix()
        section = TintedSection(
            "Main document", object_name="WorkspaceMainSection", suffix=suffix
        )
        body = section.body_layout

        self._info_title = QLabel()
        self._info_title.setObjectName("WorkspaceCardTitle")
        self._info_title.setWordWrap(True)
        body.addWidget(self._info_title)

        self._info_form, self._info_fields = self._build_kv_form(
            ("Model", "BPX version", "File", "State", "Contents")
        )
        body.addLayout(self._info_form)
        return section

    def _build_reference_section(self) -> QWidget:
        """The References tinted section (design rule 1): one collapsed,
        expandable row per pinned reference, then the two pin entry points
        with the "N of 4 pinned" note as the footer. The title carries the
        feature's purple and the small light Read-only tag -- the section
        must never read louder than the document's own."""
        self._reference_tag = QLabel("Read-only")
        self._reference_tag.setObjectName("ReferenceReadOnlyTag")
        section = TintedSection(
            "References",
            object_name="WorkspaceReferenceSection",
            title_object_name="ReferenceHeading",
            suffix=self._reference_tag,
        )
        body = section.body_layout

        #: Which pins are expanded, keyed by origin identity (path or set
        #: id) -- rows are rebuilt wholesale on every refresh, so the panel,
        #: not the row, remembers expansion across rebuilds.
        self._expanded_pins: set[str] = set()
        self._pin_rows: list[_ReferencePinRow] = []
        self._pin_rows_layout = QVBoxLayout()
        self._pin_rows_layout.setContentsMargins(0, 4, 0, 0)
        self._pin_rows_layout.setSpacing(5)
        body.addLayout(self._pin_rows_layout)

        # With no reference pinned the section is the reference library's
        # front door -- the teaching line over the two pin buttons.
        self._reference_empty_text = QLabel(
            "No references pinned. Compare the main document against "
            "published sets or files."
        )
        self._reference_empty_text.setObjectName("ReferenceEmptyStateText")
        self._reference_empty_text.setWordWrap(True)
        body.addWidget(self._reference_empty_text)

        # Footer: both entry points stay put in every state; at the pin cap
        # they disable rather than disappear, beside the note saying why.
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
        self._pin_cap_note = QLabel()
        self._pin_cap_note.setObjectName("ReferencePinCapNote")
        dock_row.addWidget(self._pin_cap_note)
        body.addLayout(dock_row)

        return section

    @staticmethod
    def _pin_key(pin: ReferencePin) -> str:
        """A pin's origin identity for expansion memory: its set id or its
        path -- stable across rebuilds, unlike the row widgets."""
        snapshot = pin.snapshot
        if snapshot.set_id is not None:
            return f"set:{snapshot.set_id}"
        return f"path:{snapshot.path}"

    def _set_references(self, pins: list[ReferencePin]) -> None:
        """Rebuild the pin rows wholesale for the current pin list.

        Wholesale on purpose (the Qt-risk note in the plan): every row and
        its button connections are torn down and rebuilt, so a removed
        pin's Remove can never fire against a stale snapshot. Expansion
        survives via ``_expanded_pins``, keyed by origin, and entries for
        unpinned references are dropped so the set cannot grow stale.
        """
        for row in self._pin_rows:
            self._pin_rows_layout.removeWidget(row)
            # Hidden before deleteLater: a removed widget keeps painting at
            # its old geometry until the event loop runs deferred deletion,
            # which briefly ghosted the old row over the footer.
            row.hide()
            row.deleteLater()
        self._pin_rows = []
        keys = {self._pin_key(pin) for pin in pins}
        self._expanded_pins &= keys
        for pin in pins:
            key = self._pin_key(pin)
            row = _ReferencePinRow(pin, expanded=key in self._expanded_pins)
            row.remove_requested.connect(
                lambda snapshot=pin.snapshot: self.remove_reference_requested.emit(snapshot)
            )
            row.toggle_requested.connect(
                lambda key=key, row=row: self._toggle_pin_row(key, row)
            )
            self._pin_rows_layout.addWidget(row)
            self._pin_rows.append(row)

        self._reference_empty_text.setVisible(not pins)
        at_cap = len(pins) >= REFERENCE_PIN_CAP
        self._reference_library_button.setEnabled(not at_cap)
        self._open_reference_button.setEnabled(not at_cap)
        self._pin_cap_note.setText(
            f"{len(pins)} of {REFERENCE_PIN_CAP} pinned" if pins else ""
        )
        self._pin_cap_note.setVisible(bool(pins))

    def _toggle_pin_row(self, key: str, row: _ReferencePinRow) -> None:
        if key in self._expanded_pins:
            self._expanded_pins.discard(key)
            row.set_expanded(False)
        else:
            self._expanded_pins.add(key)
            row.set_expanded(True)

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
            "Start from a copy · the file is pinned as a reference"
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
        pins: list[ReferencePin] | None = None,
    ) -> None:
        """Update the main-document and References sections from current state.

        Identity (Title/Model/BPX version) and the section/parameter counts are
        read only through the document's own properties; ``filename``/``dirty``
        are caller-supplied facts derived from the active session, never from
        the raw dict. ``error_count``/``warning_count`` are likewise supplied
        by the caller -- the already-computed ``PartitionedIssues`` totals
        from ``main_window._refresh_all``, not re-derived here from
        ``document.error_count``/``warning_count``, so the badge can never
        disagree with the Diagnostics rail badge over an absorbed diagnostic.

        ``pins`` is independent of ``document``: references may be pinned
        with no main document open, so the References section is updated
        regardless of which branch below runs.
        """
        self._set_references(list(pins) if pins else [])

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
