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
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFontMetrics
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import SUPPORTED_EXTENSIONS
from core.document import BPXDocument
from core.document_factory import SUPPORTED_MODELS
from state.app_state import MAX_PINNED_REFERENCES
from state.reference_snapshot import ReferenceSnapshot

from . import badges, icons
from .group_box import TintedSection
from .reference_identity import badge_colour, badge_letters
from .style import ERROR, OK, WARNING
from .typography import panel_title

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

#: Why a pin was refused. One sentence for every surface that has to explain
#: it: the grey entry buttons' tooltip here, MainWindow's toast on a refused
#: pin, and the Open dialog's disabled "Pin as reference".
AT_CAP_MESSAGE = f"{MAX_PINNED_REFERENCES} already pinned · remove one first"

#: What a drop on this panel is allowed to be. Re-exported from
#: ``core.bpx_gateway`` rather than restated: the drop target and every file
#: dialog now answer "which files can this app open?" from the one tuple the
#: loader itself reads (see ``ui_qt/file_filters.py``).
SUPPORTED_BPX_EXTENSIONS = SUPPORTED_EXTENSIONS

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
    ``_reference_badge`` the tests and driver read via ``text()``)."""
    label = QLabel()
    label.setObjectName("ValidityDot")
    return label


class ReferenceRow(QFrame):
    """One pinned reference's Workspace row: a collapsed identity line that
    expands to the full record.

    Collapsed carries only what tells this reference apart from the other
    three -- badge, name, model -- plus Remove. Deliberately **no validity
    dot**: at a glance, a coloured dot on a row in a section full of
    comparison marks reads as a verdict on the comparison, so validity is
    spelled out in words inside the expanded detail instead, where it can
    say what it means.
    """

    #: Emitted with this row's ``ReferenceSnapshot`` when Remove is clicked.
    remove_requested = Signal(object)

    def __init__(self, snapshot: ReferenceSnapshot, letters: str, colour: str) -> None:
        super().__init__()
        self.setObjectName("ReferenceRow")
        self._snapshot = snapshot

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        head = QWidget()
        head.setObjectName("ReferenceRowHead")
        head_layout = QHBoxLayout(head)
        head_layout.setContentsMargins(8, 5, 8, 5)
        head_layout.setSpacing(8)
        head_layout.addWidget(
            badges.make_reference_badge(letters, colour, snapshot.filename)
        )

        name = QLabel(snapshot.filename)
        name.setObjectName("ReferenceRowName")
        head_layout.addWidget(name)

        model = QLabel(snapshot.model or "-")
        model.setObjectName("ReferenceRowModel")
        head_layout.addWidget(model)
        head_layout.addStretch(1)

        self._remove = QPushButton("Remove")
        self._remove.setObjectName("ReferenceTileRemove")
        self._remove.setCursor(Qt.PointingHandCursor)
        self._remove.clicked.connect(self._emit_remove)
        head_layout.addWidget(self._remove)

        self._chevron = QLabel("▸")
        self._chevron.setObjectName("ReferenceRowChevron")
        head_layout.addWidget(self._chevron)
        # The whole head toggles the detail, so it says so before it is
        # clicked: at MICRO the caret was the sole affordance and too small
        # to register either as a control or as a change of state.
        head.setCursor(Qt.PointingHandCursor)
        layout.addWidget(head)

        self._detail = self._build_detail(snapshot)
        self._detail.hide()
        layout.addWidget(self._detail)

    def _build_detail(self, snapshot: ReferenceSnapshot) -> QWidget:
        """The expanded record: everything the old single-reference section
        showed, per reference. Origin and the last row differ by where the
        reference came from -- a bundled set cites its paper, a file names
        its path."""
        detail = QWidget()
        detail.setObjectName("ReferenceRowDetail")
        form = QFormLayout(detail)
        form.setContentsMargins(34, 6, 8, 8)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(5)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        from_library = snapshot.set_id is not None
        rows: list[tuple[str, QWidget]] = [
            ("Origin", _detail_value("Reference library" if from_library else "File on disk")),
            ("Validity", self._build_validity_value(snapshot)),
            (
                "Model",
                _detail_value(
                    " · ".join(
                        part
                        for part in (
                            snapshot.model or "-",
                            f"BPX {snapshot.bpx_version}" if snapshot.bpx_version else "",
                        )
                        if part
                    )
                ),
            ),
            (
                "Contents",
                _detail_value(
                    f"{snapshot.section_count} sections · {snapshot.parameter_count} parameters"
                ),
            ),
        ]
        if from_library:
            rows.append(("Citation", _detail_value(snapshot.citation or "-")))
        else:
            rows.append(("File", _PathLabel(str(snapshot.path)) if snapshot.path else _detail_value("-")))

        for key, widget in rows:
            label = QLabel(f"{key}:")
            label.setObjectName("WorkspaceCardKey")
            form.addRow(label, widget)
        return detail

    def _build_validity_value(self, snapshot: ReferenceSnapshot) -> QWidget:
        """Validity as dot *and* words -- the dot alone lives nowhere on
        this page, so it can never be misread as a comparison mark."""
        text, colour = _reference_validity_text(snapshot.error_count, snapshot.warning_count)
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        dot = _validity_dot_label()
        dot.setText(icons.html_img(icons.DOT, color=colour))
        row.addWidget(dot, 0, Qt.AlignVCenter)
        self._validity_label = QLabel(text)
        self._validity_label.setObjectName("DocInfoBadge")
        row.addWidget(self._validity_label, 0, Qt.AlignVCenter)
        row.addStretch(1)
        return widget

    @property
    def snapshot(self) -> ReferenceSnapshot:
        return self._snapshot

    def is_expanded(self) -> bool:
        return not self._detail.isHidden()

    def set_expanded(self, expanded: bool) -> None:
        self._detail.setVisible(expanded)
        self._chevron.setText("▾" if expanded else "▸")

    def _emit_remove(self) -> None:
        self.remove_requested.emit(self._snapshot)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Clicking the row toggles its detail. Remove is a child button and
        eats its own click, so it can never expand the row on the way to
        removing it."""
        if event.button() == Qt.LeftButton:
            self.set_expanded(not self.is_expanded())
            event.accept()
            return
        super().mousePressEvent(event)


def _detail_value(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("WorkspaceCardValue")
    label.setWordWrap(True)
    return label


class _PathLabel(QLabel):
    """A file path elided from the *left*, keeping the file name visible.

    Word wrap cannot help here: a Windows path has no spaces to break at, so
    a long one simply ran off the row and lost exactly the end that
    identifies it. Elides head-first (the sibling of ``main_window``'s
    ``_IdentityLabel``, which elides the other way for a title), with the
    full path always one hover away.
    """

    def __init__(self, path: str) -> None:
        super().__init__()
        self.setObjectName("WorkspaceCardValue")
        self._full_text = path
        self.setToolTip(path)
        self.setMinimumWidth(0)
        self._apply_elision()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self._full_text, Qt.ElideLeft, max(self.width(), 1)))


class WorkspacePanel(QWidget):
    """Workspace-level actions (Open, New) plus current-document identity/state."""

    open_requested = Signal()
    new_requested = Signal(str)  # model name
    file_dropped = Signal(str)  # local file path
    open_reference_requested = Signal()
    open_library_requested = Signal()
    new_from_file_requested = Signal()
    #: Carries the ``ReferenceSnapshot`` its row points at -- with several
    #: references pinned, "Remove" has to say *which*.
    remove_reference_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        # A plain QWidget subclass ignores stylesheet backgrounds unless told
        # to paint them (same note as the Diagnostics strip), so without
        # WA_StyledBackground the page's white ground silently never draws.
        self.setObjectName("WorkspacePage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)

        #: One row per pinned reference, rebuilt on every refresh.
        self._reference_rows: list[ReferenceRow] = []

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

    def _build_validity_row(self) -> tuple[QHBoxLayout, QLabel, QLabel]:
        """The dot-plus-text validity line: a coloured mark from the shared
        dot family beside a plain-text label. Two widgets on purpose -- the
        text label keeps returning the bare wording ("3 warnings") from
        ``text()``, which the tests and the driver read. Used for the
        reference section's own validity line, still shown in its body (only
        the main section's validity summary moved into its title row --
        see :meth:`_build_validity_suffix`)."""
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
        """The References tinted section: a collapsed row per pinned
        reference over the two entry buttons and the pin count.

        Plural in name and shape -- the title mirrors the main section's
        format, and the reference-specific marks are that title's purple and
        the small light Read-only tag as its suffix. The section must never
        read louder than the main document's own."""
        self._reference_tag = QLabel("Read-only")
        self._reference_tag.setObjectName("ReferenceReadOnlyTag")
        section = TintedSection(
            "References",
            object_name="WorkspaceReferenceSection",
            title_object_name="ReferenceHeading",
            suffix=self._reference_tag,
        )
        body = section.body_layout

        self._reference_rows_layout = QVBoxLayout()
        self._reference_rows_layout.setContentsMargins(0, 4, 0, 0)
        self._reference_rows_layout.setSpacing(4)
        body.addLayout(self._reference_rows_layout)

        # With nothing pinned the section is the reference library's front
        # door -- the teaching line over the two entry buttons, both of which
        # stay in either state.
        self._reference_empty_text = QLabel(
            "No references pinned. Compare the main document against a "
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
        self._reference_cap_label = QLabel()
        self._reference_cap_label.setObjectName("ReferenceCapCount")
        dock_row.addWidget(self._reference_cap_label)
        body.addLayout(dock_row)

        return section

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
        references: list[ReferenceSnapshot] | None = None,
    ) -> None:
        """Update the main-document and reference sections from current state.

        Identity (Title/Model/BPX version) and the section/parameter counts are
        read only through the document's own properties; ``filename``/``dirty``
        are caller-supplied facts derived from the active session, never from
        the raw dict. ``error_count``/``warning_count`` are likewise supplied
        by the caller -- the already-computed ``PartitionedIssues`` totals
        from ``main_window._refresh_all``, not re-derived here from
        ``document.error_count``/``warning_count``, so the badge can never
        disagree with the Diagnostics rail badge over an absorbed diagnostic.

        ``references`` is independent of ``document``: references may be
        pinned with no main document open, so the References section is
        updated regardless of which branch below runs.
        """
        self._set_references(list(references or []))

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

    def _set_references(self, references: list[ReferenceSnapshot]) -> None:
        """Rebuild the References section's rows for the current pins.

        Rebuilt wholesale, never patched in place: pin order is what decides
        every badge's letters and colour, so a removal has to re-derive the
        rows below it or a row would keep wearing an identity that has moved
        on. Which rows were expanded is carried across by snapshot identity,
        so removing one reference does not collapse the record someone was
        reading on another.

        The section itself is always visible -- with nothing pinned it is the
        reference library's front door.
        """
        expanded = {
            id(row.snapshot) for row in self._reference_rows if row.is_expanded()
        }
        for row in self._reference_rows:
            self._reference_rows_layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._reference_rows = []

        letters = badge_letters([reference.filename for reference in references])
        for index, reference in enumerate(references):
            row = ReferenceRow(reference, letters[index], badge_colour(index))
            row.remove_requested.connect(self.remove_reference_requested)
            row.set_expanded(id(reference) in expanded)
            self._reference_rows.append(row)
            self._reference_rows_layout.addWidget(row)

        self._reference_empty_text.setVisible(not references)
        at_cap = len(references) >= MAX_PINNED_REFERENCES
        self._reference_cap_label.setText(
            f"{len(references)} of {MAX_PINNED_REFERENCES} pinned"
        )
        for button in (self._reference_library_button, self._open_reference_button):
            button.setEnabled(not at_cap)
            button.setToolTip(AT_CAP_MESSAGE if at_cap else "")

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
