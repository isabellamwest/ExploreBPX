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

from datetime import datetime
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QFontMetrics
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import BPX_VERSION, SUPPORTED_EXTENSIONS, CheckReach
from core.document import BPXDocument
from core.document_factory import SUPPORTED_MODELS
from core.load_record import LoadRecord
from state.app_state import MAX_PINNED_REFERENCES
from state.reference_snapshot import ReferenceSnapshot

from . import badges, icons
from .group_box import TintedSection
from .reference_identity import badge_colour, badge_letters
from . import typography
from .style import ERROR, MUTED, OK, WARNING, not_checked_tooltip
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


@dataclass(frozen=True)
class RecentEntryView:
    """One recent-files row, pre-digested by the shell: the panel renders
    and emits, it never touches the filesystem or the history store."""

    path: str
    name: str
    folder: str
    exists: bool


@dataclass(frozen=True)
class LastWorkspaceView:
    """The automatic resume row: the last workspace's main filename, how
    many references come back with it, and whether the main still exists."""

    label: str
    reference_count: int
    main_exists: bool


@dataclass(frozen=True)
class WorkspaceEntryView:
    """One named-workspace row: the user's own name for the bundle, how
    many references it carries, and whether its main still exists."""

    name: str
    reference_count: int
    main_exists: bool


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


def _verdict_words(errors: int, warnings: int) -> str:
    """The D7 validity-ladder words for a completed run: "Valid",
    "2 errors, 1 warning", "3 warnings" -- the same composition every other
    validity surface uses."""
    if not errors and not warnings:
        return "Valid"
    parts = []
    if errors:
        parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
    if warnings:
        parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
    return ", ".join(parts)


def _model_row_text(model: str | None, bpx_version: str | None) -> str:
    """The record's merged Model row: "DFN · BPX 1.1.0" (the version part
    omitted when the Header declares none) -- the format reference rows
    already used, now shared by the main document (one record shape)."""
    return " · ".join(
        part
        for part in (model or "-", f"BPX {bpx_version}" if bpx_version else "")
        if part
    )


def _checked_row_text(
    reach: CheckReach, errors: int, warnings: int, is_legacy: bool
) -> str:
    """The record's Checked row: how far checking went, then the verdict.

    An aborted run names the stage it stopped after and says plainly that
    nothing below it was judged (H2); a completed run leads with "Complete"
    and the ladder words. A legacy file prefixes the fact that ``bpx``
    judged a converted copy, not the file as it stands (finding 1)."""
    if reach is CheckReach.COMPLETE:
        base = f"Complete · {_verdict_words(errors, warnings)}"
    elif reach is CheckReach.NOT_RUN:
        base = "Not run · nothing was checked"
    else:
        stage = "Header" if reach is CheckReach.HEADER else "Parameterisation"
        base = f"{stage}, then stopped"
        # With counted findings, they explain the stop and the row stays
        # compact; with none to show, the absence must be said out loud --
        # an empty-looking aborted run is exactly the H2 hazard.
        if errors or warnings:
            base = f"{base} · {_verdict_words(errors, warnings)}"
        else:
            base = f"{base} · nothing below it was checked"
    if is_legacy:
        # Stage names keep their capital; "Complete"/"Not run" fold into the
        # sentence after the conversion prefix.
        tail = base if base.startswith(("Header", "Parameterisation")) else base[0].lower() + base[1:]
        return f"As a BPX {BPX_VERSION} conversion · {tail}"
    return base


def _legacy_checked_detail(filename: str, file_version: str | None) -> str:
    """The Checked row's expanded sentence for a legacy file: names the
    file, its own version, and what the conversion bpx judged actually did
    (bpx's documented consequences, not our summary of them)."""
    version = f"BPX {file_version}" if file_version else "a BPX 0.x file"
    return (
        f"{filename} is {version} · bpx checked a converted copy: State "
        "synthesised, initial SOC set to 1, lumped thermal conductivity "
        "dropped. The editor shows the file as it is on disk."
    )


#: The Read as row's expanded sentence when the opened YAML carries
#: comments (decision D4). States the consequence only -- the once-per-
#: document save confirmation is Phase 5's dialog and is not promised here
#: before it exists.
_COMMENTS_DETAIL = (
    "Saving rewrites the whole file: comments and formatting will not survive."
)


def _size_text(size_bytes: int) -> str:
    """A disk size in the record's units: bytes below 1 KB, whole KB below
    1 MB, one-decimal MB above."""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{max(round(size_bytes / 1024), 1)} KB"
    return f"{size_bytes / (1024 * 1024):.1f} MB"


def _stamp_text(mtime: float) -> str:
    """A modified time as "2 Aug 14:22", gaining its year only when it is
    not this year's -- the shortest stamp that stays unambiguous."""
    stamped = datetime.fromtimestamp(mtime)
    if stamped.year == datetime.now().year:
        return f"{stamped.day} {stamped:%b %H:%M}"
    return f"{stamped.day} {stamped:%b %Y %H:%M}"


def _read_as_fact(record: LoadRecord | None, fmt: str) -> tuple[str, str]:
    """The Read as row's (value html, expandable detail) pair: the format
    the loader actually used, plus the comment fact when the source carries
    comments a save would destroy."""
    shown = (record.fmt if record else fmt).upper()
    if record is not None and record.has_yaml_comments:
        value = (
            f"{shown} <span style='color:#57606a'>·</span> "
            f"<span style='color:{WARNING}'>has comments</span>"
        )
        return value, _COMMENTS_DETAIL
    return shown, ""


def _strike(label: QLabel) -> None:
    """Strike a row's name label through: the missing-file mark, stated in
    the type itself so it survives palette changes."""
    font = label.font()
    font.setStrikeOut(True)
    label.setFont(font)


def _validity_dot_label() -> QLabel:
    """The small filled dot beside a validity line -- the shared dot family
    (:mod:`ui_qt.icons`), rendered as a rich-text ``<img>`` exactly like the
    Diagnostics strip chips, so the two surfaces can never drift. The text
    itself lives in a separate plain ``QLabel`` (the ``_info_badge``/
    ``_reference_badge`` the tests and driver read via ``text()``)."""
    label = QLabel()
    label.setObjectName("ValidityDot")
    return label


class _EditableText(QWidget):
    """An in-place editable record value: a label until clicked, a line
    edit while editing (decision D6 -- not a second editor: the caller
    routes the committed text through the same ``SetValue`` command as the
    Header cards, so undo is identical wherever the user typed).

    Card discipline, translated to a record row: the editor is seeded
    *before* it is shown, a commit fires only when the text actually
    changed from that seed (a bare Enter or stray focus-out can never
    commit something nobody typed), Esc reverts, and a refresh mid-edit
    never clobbers the editor (``set_text`` only updates the seed and the
    label). An empty value shows its ghost invitation ("Add a citation…")
    -- absence stated, per the record's own rules.
    """

    #: The edited text, emitted only when it differs from the seed.
    committed = Signal(str)

    def __init__(
        self,
        display_object_name: str,
        placeholder: str,
        editor_object_name: str = "WorkspaceRecordEditor",
    ) -> None:
        super().__init__()
        self._seed = ""
        self._placeholder = placeholder
        self._cancelling = False
        self._editable = True
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # A plain wrapped label on purpose: the identity form sizes its
        # rows correctly, and pinning wrapped minimums here left a stale
        # mid-layout minimum inflating the row (caught on screen).
        self._display = QLabel()
        self._display.setObjectName(display_object_name)
        self._display.setProperty("editableValue", True)
        self._display.setWordWrap(True)
        self._display.setCursor(Qt.IBeamCursor)
        layout.addWidget(self._display)

        self._editor = QLineEdit()
        self._editor.setObjectName(editor_object_name)
        self._editor.setPlaceholderText(placeholder)
        self._editor.editingFinished.connect(self._commit)
        self._editor.installEventFilter(self)
        self._editor.hide()
        layout.addWidget(self._editor)

        self._apply_display()

    def set_text(self, text: str) -> None:
        """Update the committed value this row shows. Mid-edit, only the
        seed moves: the user's draft is theirs until they commit or Esc.
        ``isHidden`` throughout this class, never ``isVisible`` -- the
        latter is False for every widget of an unshown window, so it would
        misread "editing" as "closed" in the offscreen suite."""
        self._seed = text
        if self._editor.isHidden():
            self._apply_display()

    def text(self) -> str:
        return self._seed

    def set_editable(self, editable: bool) -> None:
        """Close or reopen the click-to-edit path (a read-only main's
        record, D3). While not editable the row is the reference record's
        own shape: a plain label, absence shown as "-" rather than an
        invitation to type. A session swap mid-edit drops the draft
        uncommitted."""
        if self._editable == editable:
            return
        self._editable = editable
        if not editable and not self._editor.isHidden():
            self._cancelling = True
            self._editor.hide()
            self._display.show()
            self._cancelling = False
        self._display.setCursor(Qt.IBeamCursor if editable else Qt.ArrowCursor)
        self._apply_display()

    def begin_edit(self) -> None:
        """Open the editor, seeded with the committed value (populated
        before it can see focus or keys -- the card rule)."""
        self._editor.setText(self._seed)
        self._display.hide()
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton and self._editor.isHidden() and self._editable:
            self.begin_edit()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt naming
        if (
            watched is self._editor
            and event.type() == QEvent.KeyPress
            and event.key() == Qt.Key_Escape
        ):
            # Revert: close without committing. The hide() below drops focus,
            # which fires editingFinished -- the flag stops that stray signal
            # from committing the abandoned draft.
            self._cancelling = True
            self._editor.hide()
            self._display.show()
            self._cancelling = False
            self._apply_display()
            return True
        return super().eventFilter(watched, event)

    def _commit(self) -> None:
        if self._cancelling or self._editor.isHidden():
            return
        text = self._editor.text()
        self._editor.hide()
        self._display.show()
        if text != self._seed:
            self._seed = text
            self._apply_display()
            self.committed.emit(text)
        else:
            self._apply_display()

    def _apply_display(self) -> None:
        ghosted = not self._seed
        placeholder = self._placeholder if self._editable else "-"
        self._display.setText(self._seed or placeholder)
        if self._display.property("ghosted") != ghosted:
            self._display.setProperty("ghosted", ghosted)
            style = self._display.style()
            style.unpolish(self._display)
            style.polish(self._display)


class _ExpandableFact(QLabel):
    """A fact row that can expand one sentence of detail beneath its value.

    One label, one form row, text-only state changes: the detail renders
    as a muted ``META`` second line inside this label's own rich text when
    expanded, and the chevron appears only when there is detail to show, so
    a plain fact ("JSON") carries no dead affordance. Expansion survives a
    refresh because the widget persists and only its texts are rewritten.

    This shape is the conclusion of three geometry-probed on-screen
    failures: a detail label in its own row -- nested, spanning, form or
    grid, with or without wrapped-minimum pinning -- is mis-sized whenever
    it starts hidden, because the pane computes height-for-width at full
    section width while the body renders inside the content measure.
    ``setText`` on an always-visible direct form field is the one operation
    this pane provably lays out correctly (the identity and reference
    forms live on it)."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("WorkspaceCardValue")
        self.setWordWrap(True)
        self._value_html = ""
        self._detail_text = ""
        self._expanded = False

    def set_fact(self, value_html: str, detail: str = "") -> None:
        self._value_html = value_html
        self._detail_text = detail
        self.setCursor(Qt.PointingHandCursor if detail else Qt.ArrowCursor)
        if not detail:
            self._expanded = False
        self._render()

    def value_text(self) -> str:
        return self._value_html

    def detail_text(self) -> str:
        return self._detail_text

    def is_expanded(self) -> bool:
        return self._expanded and bool(self._detail_text)

    def set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded and bool(self._detail_text)
        self._render()

    def _render(self) -> None:
        text = self._value_html
        if self._detail_text:
            chevron = "▾" if self._expanded else "▸"
            text = f"{text}&nbsp; <span style='color:{MUTED}'>{chevron}</span>"
        if self._expanded and self._detail_text:
            text = (
                f"{text}<br/><span style='color:#57606a; "
                f"font-size:{typography.META}px'>{self._detail_text}</span>"
            )
        self.setText(text)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if event.button() == Qt.LeftButton and self._detail_text:
            self.set_expanded(not self.is_expanded())
            event.accept()
            return
        super().mousePressEvent(event)


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
        """The expanded record, in the one record shape the main document
        uses (Phase 4): Title · Description · Citation · Model · Read as ·
        Checked · Contents · From -- identical rows, all read-only, no
        Status row (a reference is never saved). The old Origin row is
        absorbed into From, and the old Validity row into Checked, whose
        dot keeps the reference rule: never ``ERROR`` red."""
        detail = QWidget()
        detail.setObjectName("ReferenceRowDetail")
        form = QFormLayout(detail)
        form.setContentsMargins(34, 6, 8, 8)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(5)
        form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignLeft)
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)

        record = snapshot.record
        read_as, _comment_detail = _read_as_fact(record, "json")
        rows: list[tuple[str, QWidget]] = [
            ("Title", _detail_value(snapshot.title or "-")),
            ("Description", _detail_value(snapshot.description or "-")),
            ("Citation", _detail_value(snapshot.citation or "-")),
            ("Model", _detail_value(_model_row_text(snapshot.model, snapshot.bpx_version))),
            ("Read as", _detail_value(read_as)),
            ("Checked", self._build_checked_value(snapshot)),
            (
                "Contents",
                _detail_value(
                    f"{snapshot.section_count} sections · {snapshot.parameter_count} parameters"
                ),
            ),
            ("From", self._build_from_value(snapshot)),
        ]

        for key, widget in rows:
            label = QLabel(f"{key}:")
            label.setObjectName("WorkspaceCardKey")
            form.addRow(label, widget)
        return detail

    def _build_from_value(self, snapshot: ReferenceSnapshot) -> QWidget:
        """The From row: a bundled set came from the reference library; a
        file names its path plus the disk facts captured at pin time."""
        if snapshot.set_id is not None:
            return _detail_value("Reference library")
        if snapshot.path is None:
            return _detail_value("-")
        record = snapshot.record
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        row.addWidget(_PathLabel(str(snapshot.path)), 1)
        if record is not None and record.size_bytes is not None and record.mtime is not None:
            meta = QLabel(f"· {_size_text(record.size_bytes)} · {_stamp_text(record.mtime)}")
            meta.setObjectName("WorkspaceCardKey")
            row.addWidget(meta, 0, Qt.AlignVCenter)
        return widget

    def _build_checked_value(self, snapshot: ReferenceSnapshot) -> QWidget:
        """Checked as dot *and* words: how far checking went, then the
        verdict (the absorbed Validity row). The dot goes ``MUTED`` for
        anything short of a completed run -- zero errors from an aborted
        run is not a verdict (H2)."""
        record = snapshot.record
        reach = record.checked if record is not None else CheckReach.COMPLETE
        text = _checked_row_text(
            reach,
            snapshot.error_count,
            snapshot.warning_count,
            record.is_legacy if record is not None else False,
        )
        if reach is CheckReach.COMPLETE:
            _, colour = _reference_validity_text(snapshot.error_count, snapshot.warning_count)
        else:
            colour = MUTED
        widget = QWidget()
        row = QHBoxLayout(widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)
        dot = _validity_dot_label()
        dot.setText(icons.html_img(icons.DOT, color=colour))
        row.addWidget(dot, 0, Qt.AlignVCenter)
        self._validity_label = QLabel(text)
        self._validity_label.setObjectName("DocInfoBadge")
        self._validity_label.setWordWrap(True)
        row.addWidget(self._validity_label, 1, Qt.AlignVCenter)
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

    def set_path(self, path: str) -> None:
        self._full_text = path
        self.setToolTip(path)
        self._apply_elision()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self._full_text, Qt.ElideLeft, max(self.width(), 1)))


class _HistoryRow(QFrame):
    """One rail row of the Recent (and later Workspaces) group: a white chip
    whose whole surface is the click target, with any inner buttons taking
    their clicks for themselves (a pressed QPushButton never forwards to the
    row). Non-clickable rows -- a missing file -- keep the chip shape but
    answer nothing, matching the struck-through label beside them."""

    clicked = Signal()

    def __init__(self, clickable: bool = True) -> None:
        super().__init__()
        self._clickable = clickable
        #: Widgets shown only while the pointer is over the row (a named
        #: workspace's Rename/Remove) -- the wireframe's hover reveal.
        self._hover_widgets: list[QWidget] = []
        if clickable:
            self.setCursor(Qt.PointingHandCursor)

    def add_hover_action(self, widget: QWidget) -> None:
        widget.hide()
        self._hover_widgets.append(widget)

    def set_hovered(self, hovered: bool) -> None:
        """Show/hide the hover-only actions. Public on purpose: the test
        driver simulates the pointer through this, the same path
        enter/leaveEvent take."""
        for widget in self._hover_widgets:
            widget.setVisible(hovered)

    def enterEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - Qt naming
        self.set_hovered(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - Qt naming
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)


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
    #: An in-place identity edit in the record: (Header field alias, new
    #: text). MainWindow routes it through the session's ``SetValue`` --
    #: decision D6, the same command and undo the Header cards use.
    identity_edited = Signal(str, str)
    #: The Recent group's requests, each carrying the row's stored path
    #: spelling. Restore/open/pin/remove all happen in MainWindow -- the
    #: rows are shortcuts to the same guarded doors, never side doors.
    resume_last_requested = Signal()
    recent_open_requested = Signal(str)
    recent_pin_requested = Signal(str)
    recent_remove_requested = Signal(str)
    #: The named Workspaces group's requests, carrying the workspace name.
    workspace_open_requested = Signal(str)
    workspace_save_requested = Signal()
    workspace_rename_requested = Signal(str)
    workspace_remove_requested = Signal(str)

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

        self._workspaces_group = self._build_workspaces_group()
        rail_layout.addSpacing(6)
        rail_layout.addWidget(self._workspaces_group)

        self._recent_group = self._build_recent_group()
        rail_layout.addSpacing(6)
        rail_layout.addWidget(self._recent_group)

        divider = QFrame()
        divider.setObjectName("WorkspaceRailDivider")
        divider.setFixedHeight(1)
        rail_layout.addSpacing(6)
        rail_layout.addWidget(divider)
        rail_layout.addSpacing(6)

        rail_layout.addWidget(self._build_new_chooser())
        rail_layout.addStretch(1)
        return rail

    def _build_recent_group(self) -> QWidget:
        """The rail's Recent group: the resume-last-workspace row over the
        recent files. Content is rebuilt by :meth:`set_history`; the group
        hides itself entirely while there is no history to show, so a first
        launch looks exactly as it did before this feature existed."""
        container = QWidget()
        container.setObjectName("RecentGroup")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(panel_title("Recent"))
        self._history_rows: list[_HistoryRow] = []
        self._recent_rows_layout = layout
        container.hide()
        return container

    def _build_workspaces_group(self) -> QWidget:
        """The rail's named Workspaces group: the user's saved bundles over
        the "Save current workspace as…" action. Hidden until there is
        either a saved workspace to show or a workspace worth saving, so a
        first launch stays as spare as it always was."""
        container = QWidget()
        container.setObjectName("WorkspacesGroup")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(panel_title("Workspaces"))
        self._workspace_rows_layout = layout

        self._save_workspace_button = QPushButton("Save current workspace as…")
        self._save_workspace_button.setObjectName("SaveWorkspaceAs")
        self._save_workspace_button.setProperty("modelOption", True)
        self._save_workspace_button.clicked.connect(self.workspace_save_requested)
        layout.addWidget(self._save_workspace_button)

        container.hide()
        return container

    def set_history(
        self,
        last: LastWorkspaceView | None,
        recents: list[RecentEntryView],
        document_open: bool,
        workspaces: list[WorkspaceEntryView] = (),
        save_enabled: bool = False,
    ) -> None:
        """Rebuild the Workspaces and Recent groups from pre-digested views.

        The resume row shows only while nothing is open: with a document on
        screen the last workspace *is* the current one (or the user has
        already replaced it on purpose), and "Reopen" would be noise. The
        shell decides existence (``exists``/``main_exists``) and
        saveability; rows only render the verdicts.
        """
        for row in self._history_rows:
            # setParent(None) now, not just deleteLater: a merely-scheduled
            # widget stays a visible child until the event loop unwinds, so
            # successive rebuilds would stack ghost rows (same gotcha as the
            # Inspector's _clear_surface).
            row.setParent(None)
            row.deleteLater()
        self._history_rows = []

        for entry in workspaces:
            self._add_history_row(
                self._build_workspace_row(entry), self._workspace_rows_layout
            )
        self._save_workspace_button.setEnabled(save_enabled)
        self._save_workspace_button.setToolTip(
            "" if save_enabled else "Save the document first"
        )
        self._workspaces_group.setVisible(bool(workspaces) or save_enabled)

        if last is not None and not document_open:
            self._add_history_row(self._build_resume_row(last))
        for entry in recents:
            self._add_history_row(self._build_recent_row(entry))
        recent_count = len(recents) + (
            1 if last is not None and not document_open else 0
        )
        self._recent_group.setVisible(recent_count > 0)

    def _add_history_row(self, row: _HistoryRow, layout: QVBoxLayout | None = None) -> None:
        target = layout if layout is not None else self._recent_rows_layout
        if target is self._workspace_rows_layout:
            # Keep the save action last in its group.
            target.insertWidget(target.count() - 1, row)
        else:
            target.addWidget(row)
        self._history_rows.append(row)

    def _build_workspace_row(self, entry: WorkspaceEntryView) -> _HistoryRow:
        row = _HistoryRow(clickable=entry.main_exists)
        row.setObjectName("WorkspaceNamedRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        name = QLabel(entry.name)
        name.setObjectName("HistoryRowName")
        layout.addWidget(name)
        if entry.reference_count:
            plural = "s" if entry.reference_count != 1 else ""
            refs = QLabel(f"+ {entry.reference_count} ref{plural}")
            refs.setObjectName("HistoryRowDetail")
            layout.addWidget(refs)
        layout.addStretch(1)

        if entry.main_exists:
            action = QLabel("Open ▸")
            action.setObjectName("HistoryRowAction")
            layout.addWidget(action)
            row.setToolTip(
                "Open this workspace: main document + references"
            )
            row.clicked.connect(
                lambda name=entry.name: self.workspace_open_requested.emit(name)
            )
        else:
            chip = QLabel("Main not found")
            chip.setObjectName("HistoryRowChip")
            layout.addWidget(chip)
            row.setToolTip("This workspace's main document is gone from disk")

        rename = QPushButton("Rename")
        rename.setObjectName("HistoryRowButton")
        rename.clicked.connect(
            lambda _=False, name=entry.name: self.workspace_rename_requested.emit(name)
        )
        layout.addWidget(rename)
        row.add_hover_action(rename)
        remove = QPushButton("Remove")
        remove.setObjectName("HistoryRowButton")
        remove.setToolTip("Remove this workspace (its files are not touched)")
        remove.clicked.connect(
            lambda _=False, name=entry.name: self.workspace_remove_requested.emit(name)
        )
        layout.addWidget(remove)
        row.add_hover_action(remove)
        return row

    def _build_resume_row(self, last: LastWorkspaceView) -> _HistoryRow:
        row = _HistoryRow(clickable=last.main_exists)
        row.setObjectName("ResumeRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        name = QLabel(last.label)
        name.setObjectName("HistoryRowName")
        layout.addWidget(name)
        if last.reference_count:
            plural = "s" if last.reference_count != 1 else ""
            refs = QLabel(f"+ {last.reference_count} ref{plural}")
            refs.setObjectName("HistoryRowDetail")
            layout.addWidget(refs)
        layout.addStretch(1)

        if last.main_exists:
            action = QLabel("Reopen ▸")
            action.setObjectName("HistoryRowAction")
            layout.addWidget(action)
            row.setToolTip("Reopen the last workspace: main document + references")
            row.clicked.connect(self.resume_last_requested)
        else:
            _strike(name)
            chip = QLabel("Not found")
            chip.setObjectName("HistoryRowChip")
            layout.addWidget(chip)
            row.setToolTip("The last workspace's main document is gone from disk")
        return row

    def _build_recent_row(self, entry: RecentEntryView) -> _HistoryRow:
        row = _HistoryRow(clickable=entry.exists)
        row.setObjectName("RecentRow")
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)

        name = QLabel(entry.name)
        name.setObjectName("HistoryRowName")
        layout.addWidget(name)
        # _PathLabel, not a bare QLabel: a long folder must elide with an
        # ellipsis rather than clip mid-character against the Pin button.
        folder = _PathLabel(entry.folder)
        folder.setObjectName("HistoryRowDetail")
        layout.addWidget(folder, 1)

        if entry.exists:
            row.setToolTip(entry.path)
            row.clicked.connect(
                lambda path=entry.path: self.recent_open_requested.emit(path)
            )
            pin = QPushButton("Pin")
            pin.setObjectName("HistoryRowButton")
            pin.setToolTip("Pin as reference")
            pin.clicked.connect(
                lambda _=False, path=entry.path: self.recent_pin_requested.emit(path)
            )
            layout.addWidget(pin)
        else:
            _strike(name)
            row.setToolTip(f"{entry.path} — not found on disk")
            chip = QLabel("Not found")
            chip.setObjectName("HistoryRowChip")
            layout.addWidget(chip)
            remove = QPushButton("✕")
            remove.setObjectName("HistoryRowButton")
            remove.setToolTip("Remove from Recent")
            remove.clicked.connect(
                lambda _=False, path=entry.path: self.recent_remove_requested.emit(path)
            )
            layout.addWidget(remove)
        return row

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
    def _record_form() -> QFormLayout:
        """A section's keyed record-row layout -- one shared recipe so the
        document and reference sections can never drift apart. Explicit left
        alignment throughout: macOS's native form style centres the rows and
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
        return form

    @staticmethod
    def _add_record_row(form: QFormLayout, key: str, widget: QWidget) -> None:
        label = QLabel(f"{key}:")
        label.setObjectName("WorkspaceCardKey")
        form.addRow(label, widget)

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
        # The same small light tag a reference wears, shown only for a
        # read-only main (D3's "Open as-is") -- one mode, one word, both
        # record shapes.
        self._main_read_only_tag = QLabel("Read-only")
        self._main_read_only_tag.setObjectName("ReferenceReadOnlyTag")
        self._main_read_only_tag.hide()
        row.addWidget(self._main_read_only_tag, 0, Qt.AlignVCenter)
        dot = _validity_dot_label()
        text = QLabel()
        text.setObjectName("DocInfoBadge")
        row.addWidget(dot, 0, Qt.AlignVCenter)
        row.addWidget(text, 0, Qt.AlignVCenter)
        return widget, dot, text

    def _build_info_section(self) -> QWidget:
        """The main-document tinted section, in the signed concept B shape:
        caps title naming the role plainly ("Main document" -- "main" is the
        app's one role word, per the UI copy rule) with the validity summary
        in the title row's suffix; then the *identity block* -- Title,
        Description, Citation, the three rows a person may edit in place --
        over the *fact plaque*, a quieter wash carrying the file's own
        immutable facts (Model · Read as · Checked · Contents · From ·
        Status). The split is the D6 rule made visible: the upper block is
        yours, the plaque is the file's."""
        suffix, self._info_dot, self._info_badge = self._build_validity_suffix()
        section = TintedSection(
            "Main document", object_name="WorkspaceMainSection", suffix=suffix
        )
        body = section.body_layout

        # Empty-state line, shown alone when no document is open.
        self._info_empty = QLabel(_INFO_PANEL_EMPTY_STATE_TEXT)
        self._info_empty.setObjectName("WorkspaceCardTitle")
        self._info_empty.setEnabled(False)
        body.addWidget(self._info_empty)

        self._info_title = _EditableText(
            "WorkspaceCardTitle", "Add a title…",
            editor_object_name="WorkspaceTitleEditor",
        )
        self._info_title.committed.connect(
            lambda text: self.identity_edited.emit("Title", text)
        )
        body.addWidget(self._info_title)

        self._info_description = _EditableText(
            "WorkspaceCardValue", "Add a description…"
        )
        self._info_description.committed.connect(
            lambda text: self.identity_edited.emit("Description", text)
        )
        self._info_citation = _EditableText("WorkspaceCardValue", "Add a citation…")
        self._info_citation.committed.connect(
            lambda text: self.identity_edited.emit("References", text)
        )
        self._identity_form = self._record_form()
        self._add_record_row(self._identity_form, "Description", self._info_description)
        self._add_record_row(self._identity_form, "Citation", self._info_citation)
        body.addLayout(self._identity_form)

        self._fact_band = QWidget()
        self._fact_band.setObjectName("WorkspaceFactBand")
        self._fact_band.setAttribute(Qt.WA_StyledBackground, True)

        self._fact_model = _detail_value("")
        self._fact_read_as = _ExpandableFact()
        self._fact_checked = _ExpandableFact()
        self._fact_contents = _detail_value("")

        self._fact_from = QWidget()
        from_row = QHBoxLayout(self._fact_from)
        from_row.setContentsMargins(0, 0, 0, 0)
        from_row.setSpacing(6)
        self._fact_from_path = _PathLabel("")
        from_row.addWidget(self._fact_from_path, 1)
        self._fact_from_meta = QLabel()
        self._fact_from_meta.setObjectName("WorkspaceCardKey")
        from_row.addWidget(self._fact_from_meta, 0, Qt.AlignVCenter)

        self._fact_status = _detail_value("")

        # The form is the band's direct layout with every row visible from
        # construction -- the one shape the pane provably sizes correctly
        # (see _ExpandableFact's docstring for the paid-for detour).
        self._fact_form = self._record_form()
        self._fact_form.setContentsMargins(10, 7, 10, 9)
        self._fact_band.setLayout(self._fact_form)
        for key, widget in (
            ("Model", self._fact_model),
            ("Read as", self._fact_read_as),
            ("Checked", self._fact_checked),
            ("Contents", self._fact_contents),
            ("From", self._fact_from),
            ("Status", self._fact_status),
        ):
            self._add_record_row(self._fact_form, key, widget)
        body.addWidget(self._fact_band)
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
        outstanding_count: int = 0,
        references: list[ReferenceSnapshot] | None = None,
        load_record: LoadRecord | None = None,
        never_saved: bool = False,
        read_only: bool = False,
    ) -> None:
        """Update the main-document and reference sections from current state.

        Identity and the section/parameter counts are read only through the
        document's own properties; ``filename``/``dirty``/``never_saved``
        are caller-supplied facts derived from the active session, never
        from the raw dict, and ``load_record`` is the session's load-time
        record (``None`` for a New scaffold, which had no load to state).
        ``error_count``/``warning_count`` are likewise supplied by the
        caller -- the already-computed ``PartitionedIssues`` totals from
        ``main_window._refresh_all``, not re-derived here from
        ``document.error_count``/``warning_count``, so the badge can never
        disagree with the Diagnostics rail badge over an absorbed diagnostic.

        ``references`` is independent of ``document``: references may be
        pinned with no main document open, so the References section is
        updated regardless of which branch below runs.
        """
        self._set_references(list(references or []))

        if document is None:
            self._info_empty.show()
            self._info_title.hide()
            self._set_form_rows_visible(self._identity_form, False)
            self._fact_band.hide()
            self._info_dot.hide()
            self._info_badge.hide()
            self._main_read_only_tag.hide()
            return

        self._info_empty.hide()
        self._info_title.show()
        self._set_form_rows_visible(self._identity_form, True)
        self._fact_band.show()
        self._main_read_only_tag.setVisible(read_only)

        identity = document.identity
        # D6 gives the main record its editable rows; a read-only main gets
        # the reference record's shape instead -- plain values, "-" for
        # absence, no click-to-edit.
        for row in (self._info_title, self._info_description, self._info_citation):
            row.set_editable(not read_only)
        self._info_title.set_text(identity.title)
        self._info_description.set_text(identity.description)
        self._info_citation.set_text(identity.references)

        self._fact_model.setText(_model_row_text(identity.model, identity.bpx_version))
        read_as, comment_detail = _read_as_fact(load_record, document.fmt)
        self._fact_read_as.set_fact(read_as, comment_detail)
        legacy = load_record.is_legacy if load_record is not None else False
        self._fact_checked.set_fact(
            _checked_row_text(
                document.validation_reach, error_count, warning_count, legacy
            ),
            _legacy_checked_detail(filename or document.filename, identity.bpx_version)
            if legacy
            else "",
        )
        self._fact_contents.setText(
            f"{document.section_count} sections · {document.parameter_count} parameters"
        )

        has_source = load_record is not None and bool(load_record.source)
        from_label = self._fact_form.labelForField(self._fact_from)
        self._fact_from.setVisible(has_source)
        if from_label is not None:
            from_label.setVisible(has_source)
        if has_source:
            self._fact_from_path.set_path(load_record.source)
            has_disk_facts = (
                load_record.size_bytes is not None and load_record.mtime is not None
            )
            if has_disk_facts:
                self._fact_from_meta.setText(
                    f"· {_size_text(load_record.size_bytes)}"
                    f" · {_stamp_text(load_record.mtime)}"
                )
            self._fact_from_meta.setVisible(has_disk_facts)

        if read_only:
            # Not the D8 saved-state pair: a read-only session will never
            # write, so its status is its mode. (It also has no backing
            # file, which must not read as "never saved".)
            status = "Read-only"
        elif never_saved:
            status = "Unsaved changes · never saved"
        else:
            status = "Unsaved changes" if dirty else "Saved"
        self._fact_status.setText(status)

        self._set_validity_badge(
            error_count,
            warning_count,
            outstanding_count,
            reach=document.validation_reach,
        )

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

    def _set_validity_badge(
        self,
        errors: int,
        warnings: int,
        outstanding: int = 0,
        reach: CheckReach = CheckReach.COMPLETE,
    ) -> None:
        """The main document's dot-and-text mark: what the validator says,
        plus what is still missing.

        *outstanding* is the app's own completion count, not a validator
        verdict, so it never changes the dot's colour and always trails the
        validator's own words. It has to be here all the same: a freshly
        created DFN passes the schema with three parameters, and a lone
        green "Valid" beside a title reading "(incomplete)" told the user
        the file was ready when 35 required fields were still empty.

        *reach* is ``validation_reach`` (H2): when ``bpx`` aborted its staged
        run, every abort error can be absence-shaped and absorbed into the
        incomplete count, leaving zero errors to show -- but zero errors from
        an aborted run is not a verdict, and "Valid" would claim a check that
        never finished. The badge says "Not checked" instead, exactly the word
        the Inspector uses for a parameter in that state, and carries the same
        hover sentence naming the stage the run stopped at.
        """
        tooltip = ""
        if not errors and not warnings:
            if reach is CheckReach.COMPLETE:
                text, colour = "Valid", OK
            else:
                text, colour = "Not checked", MUTED
                tooltip = not_checked_tooltip(reach)
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
        if outstanding:
            text = f"{text} · {outstanding} incomplete"
        self._info_badge.setText(text)
        self._info_badge.setToolTip(tooltip)
        self._info_dot.setToolTip(tooltip)
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
