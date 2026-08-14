"""Workspace page: the workspace rail and the board of files it holds.

Peer of ``TreePanel``/``DiagnosticsPanel``: a self-contained widget that owns
its own layout and rendering. MainWindow only constructs it, wires its
signals to the existing guarded open/new flows, and calls ``refresh``
wherever it refreshes the other views.

The page is two surfaces edge to edge, the Diagnostics page's anatomy:

* a shaded **rail** -- New workspace, then the workspaces themselves (named
  ones above, untitled Recent ones below, each group hidden whole whenever
  it has no rows). Row actions are hover-revealed, never a ⋯ menu. Nothing
  about *files* lives here: opening one and starting one are acts on the
  workspace that is on the board, so they belong on the board.
* a white **pane** carrying the board: the workspace's own name at the top
  (click to rename), then a "This workspace" frame holding the main card
  beside four reference slots -- the slots *are* the drawn cap, so there is
  no "n of 4 pinned" counter and no separate dock buttons. An empty slot's
  ＋ opens one menu with three routes (reference library, a file, a recent
  file). With no main open the card gives its place to the **start
  surface**, which carries every way to fill it inline. Below the board sit
  the selected reference's record and the main document's own strip: the
  editable identity rows over the fact plaque.

No lines anywhere in the pane -- no hairlines, borders, rounded corners or
shadows beyond the tinted washes and the cards themselves; the bordered
``GroupBox`` chrome used elsewhere in the app is not used on this page.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import QAction, QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import BPX_VERSION, SUPPORTED_EXTENSIONS, CheckReach
from core.document_factory import SUPPORTED_MODELS
from core.reference_library import PROVENANCE as LIBRARY_PROVENANCE
from state.app_state import MAX_PINNED_REFERENCES

from . import badges, icons, typography
from .elided_label import ElidedLabel, PathLabel
from .group_box import TintedSection
from .reference_identity import badge_colour, badge_letters
from .style import (
    ERROR,
    MUTED,
    OK,
    PAGE_MEASURE,
    SPACING_LG,
    WARNING,
    not_checked_tooltip,
)
from .typography import panel_title

if TYPE_CHECKING:
    from core.document import BPXDocument
    from core.load_record import LoadRecord
    from state.reference_snapshot import ReferenceSnapshot

_INFO_PANEL_EMPTY_STATE_TEXT = "No document open"

#: Why a pin was refused. One sentence for every surface that has to explain
#: it: MainWindow's toast on a refused pin and the Open dialog's disabled
#: "Pin as reference". The board itself never needs it -- at the cap there
#: is simply no empty slot to click.
AT_CAP_MESSAGE = f"{MAX_PINNED_REFERENCES} already pinned · remove one first"

#: What an untitled workspace is called before anyone names it.
UNTITLED_WORKSPACE = "Untitled workspace"

#: What a drop on this panel is allowed to be. Re-exported from
#: ``core.bpx_gateway`` rather than restated: the drop target and every file
#: dialog now answer "which files can this app open?" from the one tuple the
#: loader itself reads (see ``ui_qt/file_filters.py``).
SUPPORTED_BPX_EXTENSIONS = SUPPORTED_EXTENSIONS

#: The actions rail's fixed width. Narrower than the original 340px
#: (explicit user call): the row labels already elide gracefully, and 340
#: gave the rail far more room than the New chooser's rows or a workspace
#: row need, at the cost of the board beside it.
_RAIL_WIDTH = 280

#: The white gap between the board and the strip beneath it -- the page
#: gutter rung, not a width of its own.
_SECTION_GAP = SPACING_LG

#: How tall an empty reference slot stays *before* the row is levelled. The
#: slots are top-aligned, so without a floor a slot holding only its ＋ would
#: shrink to the button and stop reading as a place a reference goes.
#: ``_level_board_cards`` raises it to whatever the tallest card asks for.
_EMPTY_SLOT_HEIGHT = 56

#: The measure every section on this page is capped at -- one right edge for
#: the whole page, so the board and the strip beneath it are bookends of the
#: same column rather than two bands ending in different places. The shared
#: ``style.PAGE_MEASURE`` (see that constant's own comment, which quotes this
#: page's own discovery: at the reading measure the four reference slots got
#: about 90 px each and their names elided to a few characters, and the From
#: row could not show a path) now that the Inspector page hit the identical
#: disease. The description is the one paragraph here and it does run to
#: this measure -- capping that label alone re-clips it, because a
#: word-wrapped label narrower than the form column it sits in is measured
#: for height at the column's width and handed too few pixels (the same
#: mismatch ``_MeasureBoundVBox`` guards at the section level).

#: The Main slot's share of the board row, against 2 per reference slot.
#: The row is capped at the page measure, so the two states want
#: different splits: a main *card* is a filename and a mark, while the start
#: surface is four model names each beside a descriptor, read side by side to
#: choose between. A descriptor that elides cannot be compared, so the
#: surface takes the width the empty slots are not using -- and gives it
#: straight back the moment a reference is pinned, because a pinned
#: reference's own name is real content and outranks a menu.
_MAIN_CARD_STRETCH = 3
_START_SURFACE_STRETCH = 8


@dataclass(frozen=True)
class RecentEntryView:
    """One recent *file*, pre-digested by the shell.

    Two surfaces read these: the empty board's start surface, where a
    recent file is the quickest route to a main document, and the ＋ menu,
    where it is a reference. ``mtime`` is the file's modified time when the
    shell probed it (``None`` when it could not be read) -- the panel turns
    it into the stamp, because how a fact is spelled is the panel's business
    and whether it is true is the shell's.
    """

    path: str
    name: str
    exists: bool
    mtime: float | None = None


@dataclass(frozen=True)
class WorkspaceRowView:
    """One rail row: a workspace as the rail needs to draw it.

    ``label`` is the workspace's own name once it has one, the main's
    filename before that, and "Untitled workspace" when it holds neither --
    a workspace exists before it holds anything, and still has to be
    recognisable. ``has_main`` is whether one is *recorded*;
    ``main_exists`` is whether that recording still points at a file, and
    is True when there is nothing recorded (nothing recorded is nothing
    lost). The panel renders and emits; it never touches the filesystem or
    the history store.
    """

    id: str
    label: str
    named: bool
    reference_count: int
    main_exists: bool
    is_current: bool
    has_main: bool = True


@dataclass(frozen=True)
class MissingFileView:
    """One file a workspace remembers but could not open.

    ``reference_index`` is ``None`` for the main document, else the
    reference's position in the record -- what Locate… and Remove act on.
    ``message`` is composed by the shell, which is the only layer that knows
    *why* the file did not open: a file that has moved and one that will not
    parse are different problems, and the banner must not call the second
    one "not found".
    """

    label: str
    path: str
    reference_index: int | None
    message: str


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
# without breaking the start surface. Short enough to sit whole beside the
# longest model name at the board's width -- these are read side by side to
# choose between, so one that elides is one that cannot be compared.
_MODEL_DESCRIPTORS: dict[str, str] = {
    "SPM": "Single Particle Model",
    "SPMe": "Single Particle Model with electrolyte",
    "DFN": "Doyle-Fuller-Newman model",
    "Partial": "Sections are all optional",
}


def _reference_validity_text(errors: int, warnings: int) -> tuple[str, str]:
    """The reference's validity text and dot colour, matching the document
    badge's own wording and format exactly ("Valid", "2 errors, 1 warning")
    with one deliberate exception: never ``ERROR`` red -- a docked reference
    is read-only and never blocks anything, so amber is as loud as its mark
    gets."""
    if not errors and not warnings:
        return "Valid", OK
    parts = []
    if errors:
        parts.append(f"{errors} error" + ("s" if errors != 1 else ""))
    if warnings:
        parts.append(f"{warnings} warning" + ("s" if warnings != 1 else ""))
    return ", ".join(parts), WARNING


def _verdict_words(errors: int, warnings: int) -> str:
    """The validity-ladder words for a completed run: "Valid",
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
    return " · ".join(part for part in (model or "-", f"BPX {bpx_version}" if bpx_version else "") if part)


def _checked_row_text(reach: CheckReach, errors: int, warnings: int, is_legacy: bool) -> str:
    """The record's Checked row: how far checking went, then the verdict.

    An aborted run names the stage it stopped after and says plainly that
    nothing below it was judged; a completed run leads with "Complete"
    and the ladder words. A legacy file prefixes the fact that ``bpx``
    judged a converted copy, not the file as it stands."""
    if reach is CheckReach.COMPLETE:
        base = f"Complete · {_verdict_words(errors, warnings)}"
    elif reach is CheckReach.NOT_RUN:
        base = "Not run · nothing was checked"
    else:
        stage = "Header" if reach is CheckReach.HEADER else "Parameterisation"
        base = f"{stage}, then stopped"
        # With counted findings, they explain the stop and the row stays
        # compact; with none to show, the absence must be said out loud --
        # an empty-looking aborted run must not read as a clean one.
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
#: comments. States the consequence only -- the once-per-document save
#: confirmation is a separate dialog and is not promised here before it
#: exists.
_COMMENTS_DETAIL = "Saving rewrites the whole file: comments and formatting will not survive."


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


def _fact_with_detail(value_html: str, detail: str) -> str:
    """A record row's rich text: the value, then *detail* as a muted META
    second line when there is one -- the same rendering an expanded
    ``_ExpandableFact`` uses, minus the toggle (the reference record states
    its details outright; see ``ReferenceRecordPanel``)."""
    if not detail:
        return value_html
    return f"{value_html}<br/><span style='color:{MUTED}; font-size:{typography.META}px'>{detail}</span>"


def _read_as_fact(record: LoadRecord | None, fmt: str) -> tuple[str, str]:
    """The Read as row's (value html, expandable detail) pair: the format
    the loader actually used, plus the comment fact when the source carries
    comments a save would destroy."""
    shown = (record.fmt if record else fmt).upper()
    if record is not None and record.has_yaml_comments:
        value = f"{shown} <span style='color:#57606a'>·</span> <span style='color:{WARNING}'>has comments</span>"
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
    itself lives in a separate plain ``QLabel`` beside it, which the tests
    and driver read via ``text()``."""
    label = QLabel()
    label.setObjectName("ValidityDot")
    return label


def _detail_value(text: str) -> QLabel:
    label = QLabel(text)
    label.setObjectName("WorkspaceCardValue")
    label.setWordWrap(True)
    return label


class _EditableText(QWidget):
    """An in-place editable record value: a label until clicked, a line
    edit while editing (not a second editor: the caller routes the
    committed text through the same ``SetValue`` command as the Header
    cards, so undo is identical wherever the user typed).

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
        record). While not editable the row is the reference record's
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

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._editor.isHidden() and self._editable:
            self.begin_edit()
            event.accept()
            return
        super().mousePressEvent(event)

    def eventFilter(self, watched, event) -> bool:
        if watched is self._editor and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Escape:
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


class WorkspaceNameField(_EditableText):
    """The board's header: the workspace's own name, click to rename.

    An untitled workspace shows a ghosted invitation rather than a blank,
    because naming is the one act that stops a workspace decaying and the
    page should say so where it happens. Names are unique, so a commit can
    be refused: :meth:`reject` puts the draft back in the editor with the
    reason beneath it, which is the whole of the "that name is in use"
    treatment -- no dialog, no overwrite prompt.
    """

    def __init__(self) -> None:
        super().__init__(
            "WorkspaceNameDisplay",
            UNTITLED_WORKSPACE,
            editor_object_name="WorkspaceNameEditor",
        )
        self._error = QLabel()
        self._error.setObjectName("WorkspaceNameError")
        self._error.setWordWrap(True)
        self._error.hide()
        self.layout().addWidget(self._error)

    def set_text(self, text: str) -> None:
        super().set_text(text)
        if self._editor.isHidden():
            self._error.hide()

    def begin_edit(self) -> None:
        self._error.hide()
        super().begin_edit()

    def reject(self, message: str, draft: str) -> None:
        """Refuse the committed name: say why, and hand the draft back so
        the next attempt starts from what was typed rather than from
        nothing."""
        self._error.setText(message)
        self._error.show()
        self._display.hide()
        self._editor.setText(draft)
        self._editor.show()
        self._editor.setFocus()
        self._editor.selectAll()

    def error_text(self) -> str:
        """The inline refusal currently shown, or "" -- the test seam."""
        return self._error.text() if not self._error.isHidden() else ""


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
            text = f"{text}<br/><span style='color:#57606a; font-size:{typography.META}px'>{self._detail_text}</span>"
        self.setText(text)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.LeftButton and self._detail_text:
            self.set_expanded(not self.is_expanded())
            event.accept()
            return
        super().mousePressEvent(event)


# Shared with the other panes that must never clip a squeezed label; the
# classes themselves moved to ``ui_qt.elided_label``.
_ElidedLabel = ElidedLabel
_PathLabel = PathLabel


def _record_form() -> QFormLayout:
    """A keyed record-row layout -- one shared recipe so the document strip,
    the fact plaque and the reference record can never drift apart. Explicit
    left alignment throughout: macOS's native form style centres the rows and
    right-aligns the labels, which reads as scattered text rather than a
    keyed record. Growing fields keep a long value ("11 sections · 44
    parameters") fully visible instead of squeezed."""
    form = QFormLayout()
    form.setContentsMargins(0, 4, 0, 0)
    form.setHorizontalSpacing(12)
    form.setVerticalSpacing(6)
    form.setFormAlignment(Qt.AlignLeft | Qt.AlignTop)
    form.setLabelAlignment(Qt.AlignLeft)
    form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
    return form


def _add_record_row(form: QFormLayout, key: str, widget: QWidget) -> None:
    label = QLabel(f"{key}:")
    label.setObjectName("WorkspaceCardKey")
    form.addRow(label, widget)


class ReferenceRecordPanel(QWidget):
    """The selected reference's full record, shown beneath the board.

    The one record shape the main document uses: Title · Description ·
    Citation · Model · Read as · Checked · Contents · From -- identical
    rows, all read-only, no Status row (a reference is never saved). The
    slot above stays compact and this says everything else, so no fact has
    to be squeezed into a card or hidden behind a hover.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceRecordPanel")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._snapshot: ReferenceSnapshot | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # One panel serves all four slots, so it has to say whose record it
        # is showing -- a badge and a name, the same identity the slot above
        # wears. The Read-only tag belongs here rather than on every slot:
        # it is true of all references, so saying it four times on the board
        # would be noise, and this is where someone reads the detail.
        head = QWidget()
        head_row = QHBoxLayout(head)
        head_row.setContentsMargins(12, 8, 12, 0)
        head_row.setSpacing(6)
        self._badge_host = QWidget()
        self._badge_layout = QHBoxLayout(self._badge_host)
        self._badge_layout.setContentsMargins(0, 0, 0, 0)
        self._badge_layout.setSpacing(0)
        head_row.addWidget(self._badge_host, 0, Qt.AlignVCenter)
        # A filename, so it elides rather than pushing the Read-only tag off
        # a narrow pane.
        self._title = _ElidedLabel("ReferenceRecordTitle")
        head_row.addWidget(self._title, 0, Qt.AlignVCenter)
        self._read_only_tag = QLabel("Read-only")
        self._read_only_tag.setObjectName("ReferenceReadOnlyTag")
        head_row.addWidget(self._read_only_tag, 0, Qt.AlignVCenter)
        head_row.addStretch(1)
        outer.addWidget(head)

        self._form = form = _record_form()
        # The shared recipe carries no side insets (the strip's section
        # gutter indents it there); this panel is its own washed surface,
        # so the card-interior inset lives here. The form sits directly on
        # the panel's own column -- no wrapper widget -- so a row growing
        # (an _ExpandableFact toggling its detail open) propagates height-
        # for-width straight up to the section instead of clipping the
        # rows above it (geometry-probed: the wrapped Description lost
        # exactly the detail's added lines).
        form.setContentsMargins(12, 6, 12, 8)
        outer.addLayout(form)

        # Every detail sentence in this record is stated directly as a muted
        # second line inside its row's own always-visible label, set before
        # the panel shows -- never toggled open later. This panel opens on a
        # slot click, so it already *is* the detail surface; and growing a
        # row after the pane has measured is precisely the geometry failure
        # ``_ExpandableFact``'s docstring records (probed again here: an
        # expansion's added lines were taken out of the wrapped Description
        # row above instead of growing the panel).
        self._values: dict[str, QLabel] = {}
        for key in ("Title", "Description", "Citation", "Model"):
            value = _detail_value("-")
            self._values[key] = value
            _add_record_row(form, key, value)

        # Read as states its comment consequence exactly like the main
        # document's row: the detail is computed and shown, not thrown
        # away, so a reference's record says as much as the main file does.
        self._read_as = _detail_value("-")
        _add_record_row(form, "Read as", self._read_as)

        contents = _detail_value("-")
        self._values["Contents"] = contents
        _add_record_row(form, "Contents", contents)

        self._checked_dot = _validity_dot_label()
        # Carries the legacy "what did bpx actually judge" sentence for the
        # same reason as Read as: computed facts are shown, not discarded.
        self._checked_text = QLabel()
        self._checked_text.setObjectName("DocInfoBadge")
        self._checked_text.setWordWrap(True)
        #: The Checked row's first line alone (no detail sentence), for the
        #: ``validity_text`` seam -- tests pin these words exactly.
        self._checked_value = ""
        checked = QWidget()
        checked_row = QHBoxLayout(checked)
        checked_row.setContentsMargins(0, 0, 0, 0)
        checked_row.setSpacing(6)
        checked_row.addWidget(self._checked_dot, 0, Qt.AlignTop)
        checked_row.addWidget(self._checked_text, 1, Qt.AlignVCenter)
        _add_record_row(form, "Checked", checked)

        self._from = QWidget()
        from_row = QHBoxLayout(self._from)
        from_row.setContentsMargins(0, 0, 0, 0)
        from_row.setSpacing(6)
        #: The From row for a bundled set: names the origin and states the
        #: library's provenance beneath it -- the sentence the library
        #: dialog shows before pinning used to vanish the moment the pin
        #: landed.
        self._from_fact = _detail_value("")
        self._from_fact.hide()
        from_row.addWidget(self._from_fact, 1)
        self._from_path = _PathLabel("")
        from_row.addWidget(self._from_path, 1)
        self._from_meta = QLabel()
        self._from_meta.setObjectName("WorkspaceCardKey")
        from_row.addWidget(self._from_meta, 0, Qt.AlignVCenter)
        _add_record_row(form, "From", self._from)

    @property
    def snapshot(self) -> ReferenceSnapshot | None:
        return self._snapshot

    def show_snapshot(self, snapshot: ReferenceSnapshot, letters: str = "", colour: str = "") -> None:
        self._snapshot = snapshot
        record = snapshot.record
        self._title.setText(snapshot.filename)
        while self._badge_layout.count():
            item = self._badge_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        if letters:
            self._badge_layout.addWidget(badges.make_reference_badge(letters, colour, snapshot.filename))
        self._values["Title"].setText(snapshot.title or "-")
        self._values["Description"].setText(snapshot.description or "-")
        self._values["Citation"].setText(snapshot.citation or "-")
        self._values["Model"].setText(_model_row_text(snapshot.model, snapshot.bpx_version))
        read_as, comment_detail = _read_as_fact(record, "json")
        self._read_as.setText(_fact_with_detail(read_as, comment_detail))
        self._values["Contents"].setText(f"{snapshot.section_count} sections · {snapshot.parameter_count} parameters")

        # Checked as dot *and* words: how far checking went, then the
        # verdict. The dot goes MUTED for anything short of a completed run
        # -- zero errors from an aborted run is not a verdict.
        reach = record.checked if record is not None else CheckReach.COMPLETE
        is_legacy = record.is_legacy if record is not None else False
        self._checked_value = _checked_row_text(reach, snapshot.error_count, snapshot.warning_count, is_legacy)
        self._checked_text.setText(
            _fact_with_detail(
                self._checked_value,
                _legacy_checked_detail(snapshot.filename, snapshot.bpx_version) if is_legacy else "",
            )
        )
        if reach is CheckReach.COMPLETE:
            _, colour = _reference_validity_text(snapshot.error_count, snapshot.warning_count)
        else:
            colour = MUTED
        # Isolated dot, no text in its own document: lift=0, like the card
        # header's dot (the x-height-midline artifact the lift corrects only
        # exists when the image shares a line with text).
        self._checked_dot.setText(icons.html_img(icons.DOT, color=colour, lift=0))

        # From: a bundled set names the library and states its provenance
        # beneath (derived from PyBaMM, BSD 3-Clause -- retained after
        # pinning, not only in the pre-pin dialog); a file names its path
        # plus the disk facts captured at pin time.
        if snapshot.set_id is not None:
            self._from_fact.setText(_fact_with_detail("Reference library", LIBRARY_PROVENANCE))
            self._from_fact.show()
            self._from_path.hide()
            self._from_meta.hide()
        elif snapshot.path is None:
            self._from_fact.hide()
            self._from_path.show()
            self._from_path.set_path("-")
            self._from_meta.hide()
        else:
            self._from_fact.hide()
            self._from_path.show()
            self._from_path.set_path(str(snapshot.path))
            has_disk_facts = record is not None and record.size_bytes is not None and record.mtime is not None
            if has_disk_facts:
                self._from_meta.setText(f"· {_size_text(record.size_bytes)} · {_stamp_text(record.mtime)}")
            self._from_meta.setVisible(has_disk_facts)

    def validity_text(self) -> str:
        """The Checked row's first line alone (never the legacy detail
        sentence beneath it) -- the test and driver seam."""
        return self._checked_value


def _card_height(card: QWidget) -> int:
    """How tall a board card will actually draw.

    The layout's own formula rather than the size hint alone, because that
    is what decides the drawn height: ``QWidgetItem`` expands a widget's
    hint by its *minimum* size hint. The two agree on today's cards; a card
    whose children ever carry minimums of their own would be levelled to the
    wrong number without this.
    """
    return max(card.sizeHint().height(), card.minimumSizeHint().height())


class _MainCard(QFrame):
    """The board's main document: the one editable file, and the two ways
    out of this page that belong to it.

    Routes rather than a dead end (the page's own rule): "Edit ▸" always,
    and "Diagnostics ▸" only when there is something to explain -- a route
    to Diagnostics with nothing wrong there would be an invitation to a
    blank page.
    """

    edit_requested = Signal()
    diagnostics_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("BoardMainCard")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # A floor, not a width: the row's stretch decides the real size, but
        # the main document's name must never be squeezed to initials.
        self.setMinimumWidth(160)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(4)

        role = QLabel("Main")
        role.setObjectName("BoardSlotRole")
        layout.addWidget(role)

        name_row = QHBoxLayout()
        name_row.setContentsMargins(0, 0, 0, 0)
        name_row.setSpacing(6)
        # Elided, not wrapped, for the reference slots' own reason (see
        # ``_ReferenceSlot``): a wrapped filename grew the card by a line and
        # left the slots beside it short. The whole name is a hover away, and
        # spelled out in the strip below and in the window title.
        self._name = _ElidedLabel("BoardMainName")
        self._name.setText(_INFO_PANEL_EMPTY_STATE_TEXT)
        name_row.addWidget(self._name)
        # A document that has never been written is a plain fact about where
        # it lives, not a problem with it -- so a muted word, never a warning
        # colour and never a mark.
        self._unsaved_tag = QLabel("Unsaved")
        self._unsaved_tag.setObjectName("UnsavedTag")
        self._unsaved_tag.hide()
        name_row.addWidget(self._unsaved_tag, 0, Qt.AlignBottom)
        name_row.addStretch(1)
        layout.addLayout(name_row)

        validity = QHBoxLayout()
        validity.setContentsMargins(0, 0, 0, 0)
        validity.setSpacing(6)
        self._dot = _validity_dot_label()
        self._badge = QLabel()
        self._badge.setObjectName("DocInfoBadge")
        self._read_only_tag = QLabel("Read-only")
        self._read_only_tag.setObjectName("ReferenceReadOnlyTag")
        self._read_only_tag.hide()
        validity.addWidget(self._dot, 0, Qt.AlignVCenter)
        validity.addWidget(self._badge, 0, Qt.AlignVCenter)
        validity.addWidget(self._read_only_tag, 0, Qt.AlignVCenter)
        validity.addStretch(1)
        layout.addLayout(validity)

        routes = QHBoxLayout()
        routes.setContentsMargins(0, 0, 0, 0)
        routes.setSpacing(10)
        self._edit_route = QPushButton("Edit ▸")
        self._edit_route.setObjectName("BoardRoute")
        self._edit_route.setCursor(Qt.PointingHandCursor)
        self._edit_route.clicked.connect(self.edit_requested)
        routes.addWidget(self._edit_route)
        self._issue_route = QPushButton()
        self._issue_route.setObjectName("BoardRoute")
        self._issue_route.setCursor(Qt.PointingHandCursor)
        self._issue_route.clicked.connect(self.diagnostics_requested)
        routes.addWidget(self._issue_route)
        routes.addStretch(1)
        layout.addLayout(routes)
        # Surplus height belongs under the last row, not shared out between
        # them: the row is levelled to its tallest card, and a card that is
        # not the tallest must not answer by loosening its own lines.
        layout.addStretch(1)

    def set_missing(self) -> None:
        """The workspace's recorded main is not on disk. The card states the
        absence, the banner above names the file, and no route is offered
        into a document that is not there.

        This is the card's only empty state. A workspace that records *no*
        main has lost nothing, so it shows the start surface instead -- the
        two must never appear together.
        """
        self._name.setText("Main not found")
        self._set_ghosted(True)
        self._unsaved_tag.hide()
        self._dot.hide()
        self._badge.hide()
        self._read_only_tag.hide()
        self._edit_route.hide()
        self._issue_route.hide()

    def set_document(
        self,
        filename: str,
        validity: str,
        colour: str,
        tooltip: str,
        errors: int,
        read_only: bool,
        never_saved: bool = False,
    ) -> None:
        self._name.setText(filename)
        self._set_ghosted(False)
        self._unsaved_tag.setVisible(never_saved)
        # Isolated dot: lift=0, same reasoning as the record plaque's dot.
        self._dot.setText(icons.html_img(icons.DOT, color=colour, lift=0))
        self._dot.setToolTip(tooltip)
        self._dot.show()
        self._badge.setText(validity)
        self._badge.setToolTip(tooltip)
        self._badge.show()
        self._read_only_tag.setVisible(read_only)
        self._edit_route.show()
        if errors:
            self._issue_route.setText("Diagnostics ▸")
            self._issue_route.show()
        else:
            self._issue_route.hide()

    def _set_ghosted(self, ghosted: bool) -> None:
        """Swap the name between "a document" and "the absence of one".

        The unpolish/polish is the whole point: a dynamic property that
        changes after the widget has been styled does nothing until the
        style is re-evaluated, so without this the card kept whichever look
        it was born with -- an open document's name rendered in the ghost
        grey meant for "No document open".
        """
        if self._name.property("ghosted") == ghosted:
            return
        self._name.setProperty("ghosted", ghosted)
        style = self._name.style()
        style.unpolish(self._name)
        style.polish(self._name)

    def validity_text(self) -> str:
        return self._badge.text()

    def name_text(self) -> str:
        # The full name, never the elided one: this is what the app is
        # asked "which document is open?", not what fits today's width.
        return self._name.full_text()


class _ReferenceSlot(QFrame):
    """One of the four reference slots: a pinned reference, or an empty
    slot whose ＋ is the only way to fill it.

    The slots are the drawn cap. At four pinned there is simply no ＋ left
    to click, which is a truer statement of the limit than a counter
    reading "4 of 4" beside a button that refuses -- nothing has to explain
    itself because nothing looks available.
    """

    #: Clicked to show this reference's record beneath the board.
    selected = Signal(object)
    remove_requested = Signal(object)
    #: Clicked the differ count: diff the main against this reference.
    diff_requested = Signal(object)
    add_requested = Signal()

    def __init__(self, index: int) -> None:
        super().__init__()
        self._index = index
        self._snapshot: ReferenceSnapshot | None = None
        self._letters = ""
        self._colour = ""
        self.setObjectName("BoardSlotEmpty")
        self.setAttribute(Qt.WA_StyledBackground, True)
        # Top-aligned on the board, so an empty slot is sized by its own ＋
        # rather than by its neighbour. The floor keeps it a slot rather
        # than a button: it has to read as a place a reference goes.
        self.setMinimumHeight(_EMPTY_SLOT_HEIGHT)
        # The matching floor across: a pinned reference's name still elides
        # at narrow windows, but never past a few readable characters.
        self.setMinimumWidth(100)
        self._layout = QVBoxLayout(self)
        # The main card's own insets, so the two card kinds share one grid.
        self._layout.setContentsMargins(12, 10, 12, 10)
        self._layout.setSpacing(4)

        self._add_button = QPushButton("＋")
        self._add_button.setObjectName("BoardSlotAdd")
        self._add_button.setCursor(Qt.PointingHandCursor)
        self._add_button.setToolTip("Add a reference")
        self._add_button.clicked.connect(self.add_requested)
        self._layout.addWidget(self._add_button, 0, Qt.AlignCenter)

        self._filled = QWidget()
        filled = QVBoxLayout(self._filled)
        filled.setContentsMargins(0, 0, 0, 0)
        filled.setSpacing(4)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(6)
        self._badge_host = QWidget()
        self._badge_layout = QHBoxLayout(self._badge_host)
        self._badge_layout.setContentsMargins(0, 0, 0, 0)
        self._badge_layout.setSpacing(0)
        head.addWidget(self._badge_host, 0, Qt.AlignVCenter)
        head.addStretch(1)
        self._remove = QPushButton("✕")
        self._remove.setObjectName("BoardSlotRemove")
        self._remove.setCursor(Qt.PointingHandCursor)
        self._remove.clicked.connect(self._emit_remove)
        head.addWidget(self._remove, 0, Qt.AlignVCenter)
        filled.addLayout(head)

        # Elided, not wrapped: four slots side by side are narrow, and a
        # long set name ("Chen2020 (LG M50 21700)") wrapped to three lines
        # made one card twice the height of its neighbours. The full name is
        # a hover away and spelled out in the record below.
        self._name = _ElidedLabel("BoardSlotName")
        filled.addWidget(self._name)

        # Elided like the name above it: model strings ("SPMe (blended)")
        # outgrow a narrow slot the same way filenames do.
        self._model = _ElidedLabel("BoardSlotModel")
        filled.addWidget(self._model)

        self._diff_route = QPushButton()
        self._diff_route.setObjectName("BoardRoute")
        self._diff_route.setCursor(Qt.PointingHandCursor)
        self._diff_route.clicked.connect(self._emit_diff)
        filled.addWidget(self._diff_route, 0, Qt.AlignLeft)
        # The main card's rule, for the same reason: a slot levelled up to a
        # taller neighbour packs its rows at the top and leaves the surplus
        # below, rather than opening gaps between name, model and route.
        filled.addStretch(1)

        self._filled.hide()
        self._layout.addWidget(self._filled)

    @property
    def index(self) -> int:
        return self._index

    @property
    def snapshot(self) -> ReferenceSnapshot | None:
        return self._snapshot

    @property
    def letters(self) -> str:
        return self._letters

    @property
    def colour(self) -> str:
        return self._colour

    def set_empty(self) -> None:
        self._snapshot = None
        self.setObjectName("BoardSlotEmpty")
        self.setProperty("selected", False)
        self._repolish()
        self._filled.hide()
        self._add_button.show()
        self.setCursor(Qt.ArrowCursor)
        self.setToolTip("")

    def set_reference(self, snapshot: ReferenceSnapshot, letters: str, colour: str, differ: int | None) -> None:
        self._snapshot = snapshot
        self._letters = letters
        self._colour = colour
        self.setObjectName("BoardSlotFilled")
        self._repolish()
        self._add_button.hide()
        self._filled.show()
        self.setCursor(Qt.PointingHandCursor)
        # Name plus origin: a bundled set and a user file look identical on
        # the slot, so the hover says which this is (the record below has
        # the full story).
        if snapshot.set_id is not None:
            origin = "Reference library"
        elif snapshot.path is not None:
            origin = str(snapshot.path)
        else:
            origin = ""
        self.setToolTip(f"{snapshot.filename}\n{origin}" if origin else snapshot.filename)

        while self._badge_layout.count():
            item = self._badge_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._badge_layout.addWidget(badges.make_reference_badge(letters, colour, snapshot.filename))
        self._name.setText(snapshot.filename)
        self._model.setText(snapshot.model or "-")
        self.set_differ(differ)

    def set_differ(self, differ: int | None) -> None:
        """The differ-count route. ``None`` while no comparison exists yet
        (no main document open, or the comparison has not been recomputed):
        an absent route is honest, a route reading "0 differ" would not be.
        """
        if differ is None:
            self._diff_route.hide()
            return
        plural = "s" if differ != 1 else ""
        text = f"{differ} value{plural} differ ▸" if differ else "Identical ▸"
        self._diff_route.setText(text)
        # A native button clips its text with no ellipsis in a narrow slot.
        self._diff_route.setToolTip(text)
        self._diff_route.show()

    def set_selected(self, selected: bool) -> None:
        self.setProperty("selected", bool(selected))
        self._repolish()

    def _repolish(self) -> None:
        style = self.style()
        style.unpolish(self)
        style.polish(self)

    def _emit_remove(self) -> None:
        if self._snapshot is not None:
            self.remove_requested.emit(self._snapshot)

    def _emit_diff(self) -> None:
        if self._snapshot is not None:
            self.diff_requested.emit(self._snapshot)

    def mousePressEvent(self, event) -> None:
        """Clicking a filled slot shows its record. The ✕ and the differ
        route are child buttons and eat their own clicks, so neither can
        select the slot on the way to acting."""
        if event.button() == Qt.LeftButton and self._snapshot is not None:
            self.selected.emit(self._snapshot)
            event.accept()
            return
        super().mousePressEvent(event)


class _MissingBanner(QFrame):
    """What a workspace remembered but could not open.

    Names each file and offers the only two answers there are: Locate…
    repoints the stored path, Remove forgets it. The rest of the workspace
    opened anyway -- refusing the whole thing over one moved file would
    throw away the arrangement the record exists to protect.
    """

    locate_requested = Signal(object)  # reference index, or None for the main
    forget_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("WorkspaceMissingBanner")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(12, 8, 12, 8)
        self._layout.setSpacing(4)
        self._rows: list[QWidget] = []
        self.hide()

    def set_missing(self, missing: list[MissingFileView]) -> None:
        for row in self._rows:
            row.setParent(None)
            row.deleteLater()
        self._rows = []
        for entry in missing:
            self._rows.append(self._build_row(entry))
            self._layout.addWidget(self._rows[-1])
        self.setVisible(bool(missing))

    def _build_row(self, entry: MissingFileView) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(entry.message)
        label.setObjectName("WorkspaceMissingText")
        label.setToolTip(entry.path)
        # Stretch-1 and wrapped: the sentence gives way before the two
        # buttons do, folding instead of shoving them off the banner.
        label.setWordWrap(True)
        layout.addWidget(label, 1)

        locate = QPushButton("Locate…")
        locate.setObjectName("HistoryRowButton")
        locate.setToolTip("Find where the file moved to")
        locate.clicked.connect(lambda _=False, index=entry.reference_index: self.locate_requested.emit(index))
        layout.addWidget(locate)

        forget = QPushButton("Remove")
        forget.setObjectName("HistoryRowButton")
        forget.setToolTip("Forget this file (the file itself is not touched)")
        forget.clicked.connect(lambda _=False, index=entry.reference_index: self.forget_requested.emit(index))
        layout.addWidget(forget)
        return row

    def missing_labels(self) -> list[str]:
        """The files this banner is currently naming -- the test seam."""
        from PySide6.QtWidgets import QLabel as _QLabel

        return [row.findChild(_QLabel, "WorkspaceMissingText").text() for row in self._rows]


class _HistoryRow(QFrame):
    """One rail row: a white chip whose whole surface is the click target,
    with any inner buttons taking their clicks for themselves (a pressed
    QPushButton never forwards to the row). Non-clickable rows -- one whose
    main is gone -- keep the chip shape but answer nothing, matching the
    struck-through label beside them."""

    clicked = Signal()

    def __init__(self, clickable: bool = True) -> None:
        super().__init__()
        self._clickable = clickable
        #: Widgets shown only while the pointer is over the row (Name,
        #: Rename, Duplicate, Remove, Locate…) -- the wireframe's hover
        #: reveal, and the app's idiom in place of a ⋯ menu.
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

    def enterEvent(self, event) -> None:
        self.set_hovered(True)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:
        self.set_hovered(False)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:
        if self._clickable and event.button() == Qt.LeftButton:
            self.clicked.emit()
            return
        super().mousePressEvent(event)


class _StartSurface(QWidget):
    """The empty Main area: every way to fill it, visible at once.

    Two acts in frequency order. **Open a file** leads, with the recent
    files beneath it -- they are the same act, pre-filled. **New document**
    follows, each model beside its own one-line descriptor, because
    choosing between them is the decision this surface exists to support
    and a tooltip cannot be compared with three others.

    Nothing hides behind a click: with Open no longer in the rail, the only
    route into a file must not be a menu. Flat white chips on the board
    wash, in the rail rows' own language -- no dashed box, no popup, and no
    line anywhere, which is the page's standing rule.
    """

    open_requested = Signal()
    #: A recent file chosen as the main document, carrying its path.
    recent_open_requested = Signal(str)
    new_requested = Signal(str)  # model name

    #: How many recent files the surface offers. Four keeps the two acts
    #: about the same height; the rest are one Open away.
    MAX_RECENT_ROWS = 4

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("BoardStartSurface")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        role = QLabel("Main")
        role.setObjectName("BoardSlotRole")
        layout.addWidget(role)

        self._open_button = QPushButton("Open a file…")
        self._open_button.setObjectName("StartOpenButton")
        self._open_button.setCursor(Qt.PointingHandCursor)
        self._open_button.clicked.connect(self.open_requested)
        layout.addWidget(self._open_button)

        self._recent_rows: list[_HistoryRow] = []
        self._recent_host = QWidget()
        self._recent_layout = QVBoxLayout(self._recent_host)
        self._recent_layout.setContentsMargins(0, 0, 0, 0)
        self._recent_layout.setSpacing(4)
        recent_label = QLabel("Recent files")
        recent_label.setObjectName("BoardSlotRole")
        self._recent_layout.addWidget(recent_label)
        self._recent_host.hide()
        layout.addWidget(self._recent_host)

        new_label = QLabel("New document")
        new_label.setObjectName("BoardSlotRole")
        layout.addSpacing(4)
        layout.addWidget(new_label)
        for model in SUPPORTED_MODELS:
            row = self._build_row(model, _MODEL_DESCRIPTORS.get(model, ""), f"NewButton_{model}")
            row.clicked.connect(lambda name=model: self.new_requested.emit(name))
            layout.addWidget(row)
        layout.addStretch(1)

    def set_recent_files(self, entries: list[RecentEntryView]) -> None:
        """Offer the newest files still on disk, newest first.

        A file that has gone is left out rather than struck through: every
        row here is a route, and a route that cannot be taken is not one.
        """
        for row in self._recent_rows:
            # setParent(None) as well as deleteLater, for the same reason the
            # rail rows do it: a merely-scheduled widget stays a visible child
            # until the event loop unwinds, so rebuilds would stack ghosts.
            row.setParent(None)
            row.deleteLater()
        self._recent_rows = []
        for entry in [entry for entry in entries if entry.exists][: self.MAX_RECENT_ROWS]:
            row = self._build_row(
                entry.name,
                _stamp_text(entry.mtime) if entry.mtime is not None else "",
                "StartRecentRow",
            )
            row.setToolTip(entry.path)
            row.clicked.connect(lambda path=entry.path: self.recent_open_requested.emit(path))
            self._recent_layout.addWidget(row)
            self._recent_rows.append(row)
        self._recent_host.setVisible(bool(self._recent_rows))

    def recent_row_labels(self) -> list[str]:
        """The recent files this surface is offering -- the test seam."""
        return [row.findChild(QLabel, "StartRowName").text() for row in self._recent_rows]

    @staticmethod
    def _build_row(name: str, trailing: str, object_name: str) -> _HistoryRow:
        """One start-surface chip: a name on the left, a muted fact on the
        right, the whole row the click target. ``startRow`` carries the
        shared styling because the model rows keep their per-model
        ``NewButton_{model}`` objectNames -- the test and driver seam, which
        QSS cannot prefix-match."""
        row = _HistoryRow()
        row.setObjectName(object_name)
        row.setProperty("startRow", True)
        layout = QHBoxLayout(row)
        # The rail rows' own insets -- these chips are documented as speaking
        # that language, so they share its metrics too.
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)
        label = QLabel(name)
        label.setObjectName("StartRowName")
        layout.addWidget(label, 0)
        # Elided rather than wrapped: a long descriptor must not make one row
        # twice the height of its neighbours (the reference slots' lesson).
        detail = _ElidedLabel("StartRowDetail")
        detail.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        # An explicit non-zero minimum is what makes the detail the side that
        # gives way: without it the layout weighs two labels both demanding
        # their whole text and squeezes the name, which clipped a filename
        # mid-word on screen. The name identifies the row, so it goes last.
        detail.setMinimumWidth(1)
        detail.setText(trailing)
        layout.addWidget(detail, 1)
        return row


def _workspace_glyph(reference_count: int, has_main: bool = True) -> QLabel:
    """The rail row's shape-at-a-glance: a bar for the main, a dot per
    reference. Two workspaces over the same file but different references
    are told apart without reading either label.

    A workspace with no main draws no bar -- the glyph says what is in the
    workspace, so an empty one is empty. It keeps the label (blank) rather
    than losing it, so every row's name still starts at the same x.
    """
    references = "".join(" ·" for _ in range(reference_count))
    label = QLabel(("▌" if has_main else "") + references)
    label.setObjectName("WorkspaceGlyph")
    plural = "s" if reference_count != 1 else ""
    if not has_main:
        label.setToolTip(f"{reference_count} reference{plural}, no main" if reference_count else "Empty workspace")
    else:
        label.setToolTip(f"Main + {reference_count} reference{plural}" if reference_count else "Main, no references")
    return label


class WorkspacePanel(QWidget):
    """The Workspace page: the rail of workspaces beside the board of files
    the current one holds."""

    open_requested = Signal()
    new_requested = Signal(str)  # model name
    file_dropped = Signal(str)  # local file path
    open_reference_requested = Signal()
    open_library_requested = Signal()
    #: Carries the ``ReferenceSnapshot`` its slot points at -- with several
    #: references pinned, "Remove" has to say *which*.
    remove_reference_requested = Signal(object)
    #: An in-place identity edit in the record: (Header field alias, new
    #: text). MainWindow routes it through the session's ``SetValue`` --
    #: the same command and undo the Header cards use.
    identity_edited = Signal(str, str)
    #: Pin a recent file as a reference (the ＋ menu's third route).
    recent_pin_requested = Signal(str)
    #: Open a recent file as the main document (the start surface's rows),
    #: carrying its path.
    recent_open_requested = Signal(str)

    #: The rail's workspace requests, each carrying the workspace's id.
    #: Opening, naming and removing all happen in MainWindow -- the rows are
    #: shortcuts to the same guarded doors, never side doors.
    workspace_open_requested = Signal(str)
    workspace_name_requested = Signal(str)
    workspace_remove_requested = Signal(str)
    workspace_locate_requested = Signal(str)
    new_workspace_requested = Signal()
    #: The board header's click-to-rename, carrying the typed name.
    workspace_renamed = Signal(str)

    #: The board's routes out, so the page is never a dead end.
    edit_requested = Signal()
    diagnostics_requested = Signal()
    diff_requested = Signal(object)  # the ReferenceSnapshot to diff against
    #: A missing file's Locate…/Remove, carrying the reference index (or
    #: ``None`` for the main document).
    locate_requested = Signal(object)
    forget_missing_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        # A plain QWidget subclass ignores stylesheet backgrounds unless told
        # to paint them (same note as the Diagnostics strip), so without
        # WA_StyledBackground the page's white ground silently never draws.
        self.setObjectName("WorkspacePage")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAcceptDrops(True)

        #: The four reference slots, built once and refilled on every refresh.
        self._slots: list[_ReferenceSlot] = []
        #: Which reference's record is open beneath the board, by identity.
        self._selected_reference: int | None = None
        #: Recent files, for the ＋ menu's third route.
        self._recent_files: list[RecentEntryView] = []

        # Rail beside pane, edge to edge -- the Diagnostics page's structure.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_rail())
        layout.addWidget(self._build_pane_scroll(), 1)

        self.set_workspaces([], [])
        self.refresh(None, None, False)

    # --- the rail ---------------------------------------------------------

    def _build_rail(self) -> QWidget:
        """The shaded rail: the one verb, then the two lists.

        Nothing about *files* lives here any more. Opening is an act on the
        workspace that is on the board, so it belongs on the board -- in the
        rail it read as global and silently swapped the current workspace's
        main. Starting a new document is the same story, and the start
        surface says both plainly. No heading over the button: it names
        itself.
        """
        rail = QWidget()
        rail.setObjectName("WorkspaceRail")
        rail.setAttribute(Qt.WA_StyledBackground, True)
        rail.setFixedWidth(_RAIL_WIDTH)
        rail_layout = QVBoxLayout(rail)
        # The pane's 16px gutter, so the two columns' text shares one grid.
        rail_layout.setContentsMargins(SPACING_LG, 12, SPACING_LG, 12)
        rail_layout.setSpacing(6)

        self._new_workspace_button = QPushButton("New workspace")
        self._new_workspace_button.setObjectName("NewWorkspace")
        self._new_workspace_button.clicked.connect(self.new_workspace_requested)
        rail_layout.addWidget(self._new_workspace_button)

        self._workspaces_group, self._workspace_rows_layout = self._build_group("Named workspaces")
        rail_layout.addSpacing(6)
        rail_layout.addWidget(self._workspaces_group)

        self._recent_group, self._recent_rows_layout = self._build_group("Recent workspaces")
        rail_layout.addSpacing(6)
        rail_layout.addWidget(self._recent_group)
        rail_layout.addStretch(1)
        return rail

    @staticmethod
    def _build_group(title: str) -> tuple[QWidget, QVBoxLayout]:
        """A rail group: a title over its rows.

        Hidden whole, title included, whenever it has no rows -- an empty
        group has nothing to teach, so it simply is not there.
        """
        container = QWidget()
        container.setObjectName(f"{title}Group")
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(panel_title(title))
        return container, layout

    def set_workspaces(
        self,
        named: list[WorkspaceRowView],
        recent: list[WorkspaceRowView],
        recent_files: list[RecentEntryView] = (),
    ) -> None:
        """Rebuild both rail groups from pre-digested views.

        The shell decides existence (``main_exists``) and which row is
        current; rows only render the verdicts. ``recent_files`` gets no
        rows in the rail -- it feeds the start surface and the board's
        ＋ menu, the two places a file is actually reached for.
        """
        self._recent_files = list(recent_files)
        self._start_surface.set_recent_files(self._recent_files)
        for row in getattr(self, "_workspace_rows", []):
            # setParent(None) now, not just deleteLater: a merely-scheduled
            # widget stays a visible child until the event loop unwinds, so
            # successive rebuilds would stack ghost rows (same gotcha as the
            # Inspector's _clear_surface).
            row.setParent(None)
            row.deleteLater()
        self._workspace_rows: list[_HistoryRow] = []

        for entry in named:
            row = self._build_workspace_row(entry)
            self._workspace_rows_layout.addWidget(row)
            self._workspace_rows.append(row)
        self._workspaces_group.setVisible(bool(named))

        for entry in recent:
            row = self._build_workspace_row(entry)
            self._recent_rows_layout.addWidget(row)
            self._workspace_rows.append(row)
        self._recent_group.setVisible(bool(recent))

    def _build_workspace_row(self, entry: WorkspaceRowView) -> _HistoryRow:
        row = _HistoryRow(clickable=not entry.is_current)
        row.setObjectName("WorkspaceNamedRow" if entry.named else "RecentRow")
        row.setProperty("current", entry.is_current)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(8, 5, 8, 5)
        layout.setSpacing(6)

        layout.addWidget(_workspace_glyph(entry.reference_count, entry.has_main))

        # Elided: the hover-revealed actions shrink the row mid-interaction,
        # and a long workspace name must give way visibly, not clip.
        name = _ElidedLabel("HistoryRowName")
        name.setText(entry.label)
        if not entry.main_exists:
            _strike(name)
        layout.addWidget(name)
        layout.addStretch(1)

        if entry.is_current:
            pill = QLabel("Open")
            pill.setObjectName("HistoryRowPill")
            layout.addWidget(pill)
        else:
            if not entry.main_exists:
                chip = QLabel("Not found")
                chip.setObjectName("HistoryRowChip")
                layout.addWidget(chip)
            # Clickable even with the main gone: opening it brings back
            # every reference that is still there and names what is not.
            # Refusing outright would throw away the arrangement.
            row.clicked.connect(lambda ws_id=entry.id: self.workspace_open_requested.emit(ws_id))

        def _action(text: str, signal, ws_id: str = entry.id) -> None:
            button = QPushButton(text)
            button.setObjectName("HistoryRowButton")
            button.clicked.connect(lambda _=False: signal.emit(ws_id))
            layout.addWidget(button)
            row.add_hover_action(button)

        if not entry.main_exists:
            _action("Locate…", self.workspace_locate_requested)
        _action(
            "Rename" if entry.named else "Name",
            self.workspace_name_requested,
        )
        _action("Remove", self.workspace_remove_requested)
        return row

    # --- the pane ---------------------------------------------------------

    def _build_pane_scroll(self) -> QWidget:
        """The pane, in the one scroll area the page needs.

        The pane states a whole record -- a reference's eight rows, then the
        main document's own -- and a record is as tall as its file's prose
        makes it. Without this the layout had nowhere to put the overflow
        and compressed the widgets below their hints instead: at 1280x720 an
        ordinary file's fact band was already being sliced through the
        glyphs, with no scrollbar to say so. Vertical only, matching
        ``InspectorScroll``; horizontally the pane still fits itself to the
        width it is given, as it always has.
        """
        scroll = QScrollArea()
        scroll.setObjectName("WorkspaceScroll")
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setWidgetResizable(True)
        # AsNeeded, not AlwaysOff: below the board row's own minimums (a
        # squeezed window with four slots pinned) a forbidden scrollbar
        # meant the pane's right edge was simply cut off -- the bar is the
        # honest fallback, and it never appears while the pane fits.
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        scroll.setWidget(self._build_pane())
        return scroll

    def _build_pane(self) -> QWidget:
        """The white pane: the workspace's name, the board of files it
        holds, the selected reference's record, and the main document's own
        strip -- stacked full-width from the top with the tail left white."""
        pane = QWidget()
        pane.setObjectName("WorkspacePane")
        pane.setAttribute(Qt.WA_StyledBackground, True)
        pane_layout = QVBoxLayout(pane)
        # A bottom margin only the scrolled case ever sees: the trailing
        # stretch keeps the tail white when everything fits, and this stops
        # the last row sitting flush against the edge when it does not.
        pane_layout.setContentsMargins(SPACING_LG, 12, SPACING_LG, 12)
        pane_layout.setSpacing(0)

        self._name_field = WorkspaceNameField()
        self._name_field.committed.connect(self.workspace_renamed)
        pane_layout.addWidget(self._name_field)

        self._missing_banner = _MissingBanner()
        self._missing_banner.locate_requested.connect(self.locate_requested)
        self._missing_banner.forget_requested.connect(self.forget_missing_requested)
        pane_layout.addSpacing(8)
        pane_layout.addWidget(self._missing_banner)

        pane_layout.addSpacing(8)
        pane_layout.addWidget(self._build_board())

        self._reference_record = ReferenceRecordPanel()
        self._reference_record.hide()
        pane_layout.addWidget(self._reference_record)

        pane_layout.addSpacing(_SECTION_GAP)
        self._main_section = self._build_strip()
        pane_layout.addWidget(self._main_section)
        pane_layout.addStretch(1)
        return pane

    def _build_board(self) -> QWidget:
        """The board: the main card beside the four reference slots, inside
        the one frame that says what they are to each other."""
        section = TintedSection(
            "This workspace",
            object_name="WorkspaceBoardSection",
            measure=PAGE_MEASURE,
        )
        body = section.body_layout

        board = QHBoxLayout()
        board.setContentsMargins(0, 4, 0, 0)
        board.setSpacing(8)

        self._main_card = _MainCard()
        self._main_card.edit_requested.connect(self.edit_requested)
        self._main_card.diagnostics_requested.connect(self.diagnostics_requested)
        # Top-aligned like the slots, so the levelled height is the last word
        # on how tall a card is. Left to fill the row the main card answered
        # any spare vertical space alone -- 476 px beside 87 px slots when the
        # row was handed the page's leftover height.
        board.addWidget(self._main_card, _MAIN_CARD_STRETCH, Qt.AlignTop)

        # The same flex slot, in the other state, and a wider share of the
        # row while nothing is pinned (see the stretch constants, and
        # _set_references, which is where the share is decided).
        self._start_surface = _StartSurface()
        self._start_surface.open_requested.connect(self.open_requested)
        self._start_surface.recent_open_requested.connect(self.recent_open_requested)
        self._start_surface.new_requested.connect(self.new_requested)
        board.addWidget(self._start_surface, _START_SURFACE_STRETCH)

        arrow = QLabel("⇄")
        arrow.setObjectName("BoardArrow")
        board.addWidget(arrow, 0, Qt.AlignVCenter)

        for index in range(MAX_PINNED_REFERENCES):
            slot = _ReferenceSlot(index)
            slot.selected.connect(self._on_slot_selected)
            slot.remove_requested.connect(self.remove_reference_requested)
            slot.diff_requested.connect(self.diff_requested)
            slot.add_requested.connect(self._show_add_menu)
            self._slots.append(slot)
            # Top-aligned, so a slot is the height of what is in it rather
            # than of whatever stands beside it. Stretched, an empty slot
            # became a tall dashed column next to the start surface -- an
            # emphatic frame around nothing.
            board.addWidget(slot, 2, Qt.AlignTop)

        self._board_layout = board
        self._start_surface_index = board.indexOf(self._start_surface)
        body.addLayout(board)
        return section

    def _build_strip(self) -> QWidget:
        """The main document's own strip, re-housed unchanged: the *identity
        block* -- Title, Description, Citation, the three rows a person may
        edit in place -- over the *fact plaque*, a quieter wash carrying the
        file's own immutable facts. This split makes that rule visible:
        the upper block is yours, the plaque is the file's."""
        section = TintedSection("Main", object_name="WorkspaceMainSection", measure=PAGE_MEASURE)
        body = section.body_layout

        self._info_title = _EditableText(
            "WorkspaceCardTitle",
            "Add a title…",
            editor_object_name="WorkspaceTitleEditor",
        )
        self._info_title.committed.connect(lambda text: self.identity_edited.emit("Title", text))
        body.addWidget(self._info_title)

        self._info_description = _EditableText("WorkspaceCardValue", "Add a description…")
        self._info_description.committed.connect(lambda text: self.identity_edited.emit("Description", text))
        self._info_citation = _EditableText("WorkspaceCardValue", "Add a citation…")
        self._info_citation.committed.connect(lambda text: self.identity_edited.emit("References", text))
        self._identity_form = _record_form()
        _add_record_row(self._identity_form, "Description", self._info_description)
        _add_record_row(self._identity_form, "Citation", self._info_citation)
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
        self._fact_form = _record_form()
        # The card-interior inset (12), on the plaque's own wash.
        self._fact_form.setContentsMargins(12, 8, 12, 8)
        self._fact_band.setLayout(self._fact_form)
        for key, widget in (
            ("Model", self._fact_model),
            ("Read as", self._fact_read_as),
            ("Checked", self._fact_checked),
            ("Contents", self._fact_contents),
            ("From", self._fact_from),
            ("Status", self._fact_status),
        ):
            _add_record_row(self._fact_form, key, widget)
        body.addWidget(self._fact_band)
        return section

    # --- the ＋ menu -------------------------------------------------------

    def _show_add_menu(self) -> None:
        menu = self.build_add_menu()
        menu.exec(self.cursor().pos())

    def build_add_menu(self) -> QMenu:
        """The empty slot's one menu, three routes: the reference library, a
        file, or a file reached for recently.

        Built fresh on every click so the recent-files route always names
        the files that are actually recent, and returned rather than shown
        so the headless driver can trigger a route without a modal exec.
        """
        menu = QMenu(self)
        menu.setObjectName("BoardAddMenu")
        library = QAction("From the reference library…", menu)
        library.triggered.connect(self.open_library_requested)
        menu.addAction(library)
        from_file = QAction("Open a BPX file…", menu)
        from_file.triggered.connect(self.open_reference_requested)
        menu.addAction(from_file)

        recent = [entry for entry in self._recent_files if entry.exists]
        if recent:
            menu.addSeparator()
            submenu = menu.addMenu("Recent files")
            submenu.setObjectName("BoardAddRecentMenu")
            for entry in recent:
                action = QAction(entry.name, submenu)
                action.setToolTip(entry.path)
                action.triggered.connect(lambda _=False, path=entry.path: self.recent_pin_requested.emit(path))
                submenu.addAction(action)
        return menu

    # --- refresh ----------------------------------------------------------

    def set_workspace_name(self, name: str | None, exists: bool = True) -> None:
        """The board header's name. ``None`` is an untitled workspace, which
        shows the ghosted invitation to name it; *exists* False means there
        is no workspace at all, and the header hides rather than inviting a
        name for something that is not there."""
        self._name_field.setVisible(exists)
        self._name_field.set_text(name or "")

    def set_differ_counts(self, counts: list[int]) -> None:
        """Update the slots' differ routes for a freshly recomputed
        comparison.

        Its own entry point because comparisons are recomputed *after* the
        page refreshes: the counts arrive a beat after the references they
        belong to, so a slot that took them from ``refresh`` alone would
        show the previous comparison's numbers -- or, on a restore, none at
        all.
        """
        for index, slot in enumerate(self._slots):
            if slot.snapshot is not None:
                slot.set_differ(counts[index] if index < len(counts) else None)

    def reject_workspace_name(self, message: str, draft: str) -> None:
        self._name_field.reject(message, draft)

    def set_missing_files(self, missing: list[MissingFileView]) -> None:
        self._missing_banner.set_missing(missing)
        self._main_missing = any(entry.reference_index is None for entry in missing)

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
        differ_counts: list[int] | None = None,
    ) -> None:
        """Update the board and the strip from current state.

        Identity and the section/parameter counts are read only through the
        document's own properties; ``filename``/``dirty``/``never_saved``
        are caller-supplied facts derived from the active session, never
        from the raw dict, and ``load_record`` is the session's load-time
        record (``None`` for a New scaffold, which had no load to state).
        ``error_count``/``warning_count`` are likewise supplied by the
        caller -- the already-computed ``PartitionedIssues`` totals from
        ``main_window._refresh_all``, not re-derived here from
        ``document.error_count``/``warning_count``, so the mark can never
        disagree with the Diagnostics rail badge over an absorbed diagnostic.

        ``references`` is independent of ``document``: references may be
        pinned with no main document open, so the slots are updated
        regardless of which branch below runs. ``differ_counts`` pairs with
        it positionally -- the comparison MainWindow already computed, which
        until now was only ever a tooltip.
        """
        self._set_references(list(references or []), differ_counts or [])

        if document is None:
            # Empty and missing are different states, and never both: with a
            # recorded main that would not open the banner and the card say
            # so, and with nothing recorded there is everything still to do.
            missing = getattr(self, "_main_missing", False)
            self._main_card.setVisible(missing)
            self._start_surface.setVisible(not missing)
            if missing:
                self._main_card.set_missing()
            # The strip is one document's record, so with no document there
            # is no record: the section goes rather than standing there
            # saying it has nothing to say. The board above already states
            # the absence, and states it as an invitation.
            self._main_section.hide()
            self._level_board_cards()
            return

        self._main_card.setVisible(True)
        self._start_surface.setVisible(False)
        self._main_section.show()
        self._info_title.show()
        self._set_form_rows_visible(self._identity_form, True)
        self._fact_band.show()

        identity = document.identity
        # The main record gets editable rows when writable; a read-only
        # main gets the reference record's shape instead -- plain values,
        # "-" for absence, no click-to-edit.
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
            _checked_row_text(document.validation_reach, error_count, warning_count, legacy),
            _legacy_checked_detail(filename or document.filename, identity.bpx_version) if legacy else "",
        )
        self._fact_contents.setText(f"{document.section_count} sections · {document.parameter_count} parameters")

        has_source = load_record is not None and bool(load_record.source)
        from_label = self._fact_form.labelForField(self._fact_from)
        self._fact_from.setVisible(has_source)
        if from_label is not None:
            from_label.setVisible(has_source)
        if has_source:
            self._fact_from_path.set_path(load_record.source)
            has_disk_facts = load_record.size_bytes is not None and load_record.mtime is not None
            if has_disk_facts:
                self._fact_from_meta.setText(
                    f"· {_size_text(load_record.size_bytes)} · {_stamp_text(load_record.mtime)}"
                )
            self._fact_from_meta.setVisible(has_disk_facts)

        if read_only:  # noqa: SIM108 - a nested ternary would bury the three states
            # Not the Saved/Unsaved pair: a read-only session will never
            # write, so its status is its mode.
            status = "Read-only"
        else:
            # A document with no backing file has everything still to write,
            # so it counts as unsaved even before its first edit.
            status = "Saved" if not dirty and not never_saved else "Unsaved changes"
        self._fact_status.setText(status)

        validity, colour, tooltip = self._validity_mark(
            error_count, warning_count, outstanding_count, document.validation_reach
        )
        self._main_card.set_document(
            filename or document.filename,
            validity,
            colour,
            tooltip,
            error_count,
            read_only,
            never_saved,
        )
        # Last, because it measures what everything above has just put in the
        # cards.
        self._level_board_cards()

    def _set_references(self, references: list[ReferenceSnapshot], differ_counts: list[int]) -> None:
        """Refill the four slots for the current pins.

        Refilled wholesale, never patched: pin order is what decides every
        badge's letters and colour, so a removal has to re-derive the slots
        below it or one would keep wearing an identity that has moved on.
        Which reference's record is open is carried across by identity, so
        removing one does not close the record someone was reading on
        another.
        """
        # Who gets the row's spare width. A pinned reference has to be
        # readable by name -- an elided slot label cannot even be told from
        # its neighbour -- and its own sizeHint cannot ask on its behalf,
        # because the label reports the width of the text it has already
        # elided to. So the share is set from what is pinned, not from what
        # the widgets claim to want.
        self._board_layout.setStretch(
            self._start_surface_index,
            _MAIN_CARD_STRETCH if references else _START_SURFACE_STRETCH,
        )
        open_id = id(self._reference_record.snapshot) if not self._reference_record.isHidden() else None
        letters = badge_letters([reference.filename for reference in references])
        for index, slot in enumerate(self._slots):
            if index < len(references):
                reference = references[index]
                slot.set_reference(
                    reference,
                    letters[index],
                    badge_colour(index),
                    differ_counts[index] if index < len(differ_counts) else None,
                )
                slot.set_selected(id(reference) == open_id)
            else:
                slot.set_empty()
                slot.set_selected(False)

        still_open = next((slot for slot in self._slots if id(slot.snapshot) == open_id), None)
        if still_open is not None:
            self._reference_record.show_snapshot(still_open.snapshot, still_open.letters, still_open.colour)
            self._reference_record.show()
        else:
            self._reference_record.hide()

    def _level_board_cards(self) -> None:
        """One height for every card on the board row.

        The cards hold different things -- the main card spends a line on its
        role where a slot spends it on a badge, and an empty slot holds only
        its ＋ -- so their own hints came out at 85, 78 and 56 px, three
        bottom edges across one row of tiles. The tallest card sets the
        height and the rest are floored to it.

        Measured over the *cards* only. The start surface stands in the same
        row and is a page's worth of ways to open a file; levelling an empty
        slot up to that is the tall dashed column around nothing that the
        slots are top-aligned to avoid.

        Run on every refresh *and* on every resize. A card filled before the
        page has been shown is measured before the stylesheet has reached
        its new badge, and answers 61 px for a card that goes on to draw 69;
        the resize pass, which happens after all that, is the one that gets
        it right. A card's own hint does not move with its minimum, so
        measuring again on an already-levelled row cannot ratchet it.
        """
        cards = [self._main_card, *self._slots]
        height = max([_EMPTY_SLOT_HEIGHT] + [_card_height(card) for card in cards if not card.isHidden()])
        for card in cards:
            # Only on a real change, or the relayout this triggers would ask
            # for another levelling pass for ever.
            if card.minimumHeight() != height:
                card.setMinimumHeight(height)

    def event(self, event) -> bool:
        """Level the row before Qt re-lays the page out.

        ``refresh`` alone is too early: a slot filled while the page is
        still unshown is measured before the stylesheet has reached its new
        badge, and reports 61 px for a card that goes on to draw 69. The
        layout request that follows the polish is the moment the numbers are
        finally true, and the no-change guard in ``_level_board_cards`` is
        what stops the levelling from requesting a layout for ever.
        """
        # A layout request can reach the panel while it is still building
        # itself, before the board exists to be levelled.
        if event.type() == QEvent.LayoutRequest and hasattr(self, "_main_card"):
            self._level_board_cards()
        return super().event(event)

    def _on_slot_selected(self, snapshot: ReferenceSnapshot) -> None:
        """Clicking a slot opens its record beneath the board; clicking the
        same slot again closes it."""
        already = not self._reference_record.isHidden() and self._reference_record.snapshot is snapshot
        if already:
            self._reference_record.hide()
        else:
            slot = next(slot for slot in self._slots if slot.snapshot is snapshot)
            self._reference_record.show_snapshot(snapshot, slot.letters, slot.colour)
            self._reference_record.show()
        for slot in self._slots:
            slot.set_selected(not already and slot.snapshot is snapshot)

    @staticmethod
    def _validity_mark(errors: int, warnings: int, outstanding: int, reach: CheckReach) -> tuple[str, str, str]:
        """The main document's dot-and-text mark: what the validator says,
        plus what is still missing.

        *outstanding* is the app's own completion count, not a validator
        verdict, so it never changes the dot's colour and always trails the
        validator's own words. It has to be here all the same: a freshly
        created DFN passes the schema with three parameters, and a lone
        green "Valid" beside a title reading "(incomplete)" told the user
        the file was ready when 35 required fields were still empty.

        *reach* is ``validation_reach``: when ``bpx`` aborted its staged
        run, every abort error can be absence-shaped and absorbed into the
        incomplete count, leaving zero errors to show -- but zero errors from
        an aborted run is not a verdict, and "Valid" would claim a check that
        never finished. The mark says "Not checked" instead, exactly the word
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
        return text, colour, tooltip

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
