"""Main application window: activity bar and workspace stack.

This is wiring only: it owns the single :class:`AppState`, connects panel
signals to state mutations, and refreshes views. No BPX logic lives here.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from PySide6.QtCore import QEvent, QSize, QStandardPaths, Qt
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core import completion, export, page_buckets, structure
from core.bpx_gateway import BPX_VERSION, LoadError
from core.commands import (
    AddParameter,
    AddSection,
    DuplicateParameter,
    MoveParameter,
    PullParameter,
    PullSection,
    RemoveParameter,
    RemoveSection,
    RenameKey,
)
from core.compare import ComparisonResult, compare
from core.completion import TaskKind
from state.app_state import AppState, PinReferenceOutcome
from state.document_session import DocumentSession
from state.reference_snapshot import ReferenceSnapshot

from . import icons
from .activity_bar import ActivityBar
from .editor_page import EditorPage
from .file_filters import BPX_FILTER, export_filter
from .inspector import InspectorPanel
from .navigation import NavigationService, NavigationTarget
from .page_header import PageHeader
from .parameter_list import ParameterListPanel
from .reference_identity import ReferencePin, build_pins
from .reference_library_dialog import ReferenceLibraryDialog
from .search import SearchBar
from .source_page import SourcePage
from . import typography
from .style import STYLESHEET
from .toast import Toast
from .tree_panel import TreePanel
from .diagnostics_panel import DiagnosticsPanel
from .workspace_panel import AT_CAP_MESSAGE, WorkspacePanel

_NO_DOCUMENT_TEXT = "No document"
_EDITOR_PAGE_INDEX = 0  # QStackedWidget page hosting the tree/params/inspector
_DIAGNOSTICS_PAGE_INDEX = 1
_WORKSPACE_PAGE_INDEX = 2
_SOURCE_PAGE_INDEX = 3


class OpenIntent(Enum):
    """What to do with a chosen file when a document is already open (the
    Open-dialog choice)."""

    REPLACE_MAIN = "replace_main"
    ADD_REFERENCE = "add_reference"
    CANCEL = "cancel"


class _IdentityLabel(QLabel):
    """A QLabel that elides its text to whatever width it is given.

    The full, untruncated string is kept as the tooltip so hovering always
    reveals the complete identity, even when the rendered text is elided.
    ``sizeHint`` is based on the *full* text rather than the currently
    displayed (possibly already-elided) text, so the label first asks for
    its natural width and only shrinks -- via ``resizeEvent`` -- once the
    toolbar actually has less room to give it.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self._full_text = ""

    def set_full_text(self, text: str) -> None:
        self._full_text = text
        self.setToolTip(text)
        self.updateGeometry()
        self._apply_elision()

    def sizeHint(self) -> QSize:
        width = QFontMetrics(self.font()).horizontalAdvance(self._full_text)
        return QSize(width, super().sizeHint().height())

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self._full_text, Qt.ElideRight, self.width()))


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("ExploreBPX")
        # Type comes from ui_qt.typography: the family on the application
        # (so a bare QFont() inherits it too), the sizes through the sheet.
        typography.apply_application_font()
        self.setStyleSheet(STYLESHEET)
        self.resize(1200, 760)
        self._state = AppState()
        self._navigation = NavigationService(self._state)
        # Cached by _refresh_all, read by _update_workspace_info -- see there.
        self._workspace_error_count = 0
        self._workspace_warning_count = 0
        #: Reference comparison state: one whole-document diff per pinned
        #: reference, in pin order -- empty with nothing pinned or no document
        #: open. UI-session state, not persisted, recomputed whenever a
        #: reference is pinned or removed (see ``_open_reference_path``/
        #: ``_on_remove_reference_requested``).
        self._comparisons: list[ComparisonResult] = []
        #: Where a never-saved document's Save As dialog starts: the folder of
        #: the last Save As this run, else the user's Documents folder -- never
        #: a bundled template/example directory. Session-scoped on purpose; not
        #: persisted.
        self._save_dialog_dir: Path | None = None
        #: Which pinned reference the Source page compares against -- its own
        #: selection, held here because Reload and the page's ← pull arrows
        #: act on it too. Clamped to the pin list on every render.
        self._source_reference_index = 0
        #: When True, ``closeEvent`` skips the unsaved-changes prompt. Set by
        #: test teardown and by shutdown paths that already decided the
        #: document's fate; never set by user-facing code.
        self._suppress_close_guard = False

        self._tree = TreePanel()
        self._params = ParameterListPanel()
        self._inspector = InspectorPanel(self._state)
        self._diagnostics = DiagnosticsPanel()
        self._workspace = WorkspacePanel()
        self._source = SourcePage()
        self._source.pull_requested.connect(self._on_source_pull)
        self._source.reload_requested.connect(self._on_reload_reference)
        self._source.reference_selected.connect(self._on_source_reference_selected)
        # Double-click Editor jump: the page's one Editor link,
        # through the shared NavigationService like every other navigation.
        self._source.navigate_requested.connect(
            lambda path: self._navigation.navigate(tuple(path))
        )
        self._search = SearchBar()
        self._activity_bar = ActivityBar()
        self._identity_label = _IdentityLabel()
        self._status_label = QLabel()

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        # Built last: the toast overlays the whole window, so it needs the
        # fully assembled window as its parent.
        self._toast = Toast(self)
        self._connect()
        self._refresh_all()

    def _build_toolbar(self) -> None:
        """Build the fixed top bar: identity on the left, actions on the right.

        Opening a file lives on the Workspace page's "Open File" button now, so
        the top bar carries no Open action -- only document identity, Save,
        Export and search.
        """
        bar = self.addToolBar("Main")
        # A stock QToolBar is movable, and right-clicking it opens
        # QMainWindow's built-in panel-toggle menu whose only entry ("Main")
        # hides the bar with no way to bring it back. This bar is fixed
        # chrome, not a togglable panel, so both features are switched off.
        bar.setMovable(False)
        bar.setContextMenuPolicy(Qt.PreventContextMenu)
        bar.addWidget(self._identity_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self._save_action = bar.addAction("Save", self._save)
        self._export_action = self._build_export_button()
        bar.addWidget(self._export_action)

        # The button is a document command, like its neighbours Save and
        # Export: it never edits whatever widget happens to hold focus. The
        # *keyboard* shortcut lives on a separate QShortcut precisely because
        # it must be focus-aware -- see _undo. Binding the sequence to the
        # action instead would make one indistinguishable from the other.
        self._undo_action = bar.addAction("Undo", self._undo_document)
        undo_keys = QKeySequence(QKeySequence.Undo).toString(QKeySequence.NativeText)
        self._undo_action.setToolTip(f"Undo ({undo_keys})")
        self._undo_shortcut = QShortcut(QKeySequence.Undo, self, activated=self._undo)

        # Redo mirrors Undo exactly, including the button/shortcut split above.
        # ``QShortcut(QKeySequence.Redo, ...)`` matches *every* platform
        # binding of the standard Redo key at dispatch time -- Qt resolves a
        # StandardKey shortcut against ``QKeySequence.keyBindings``, not just
        # the single sequence its own ``.key()`` reports -- and on Windows
        # that set already includes Ctrl+Shift+Z, the binding most users
        # actually reach for. Registering "Ctrl+Shift+Z" a *second* time, as
        # its own QShortcut, then makes Qt see two WindowShortcuts claiming
        # the same key: it emits ``activatedAmbiguously`` and neither handler
        # runs, so the key goes dead -- on Windows as much as macOS/X11. The
        # alternate shortcut is therefore registered only where it is
        # genuinely additional; elsewhere ``_redo_shortcut_alt`` aliases the
        # primary, since that one QShortcut already serves the key.
        self._redo_action = bar.addAction("Redo", self._redo_document)
        self._redo_shortcut = QShortcut(QKeySequence.Redo, self, activated=self._redo)
        redo_alt_sequence = QKeySequence("Ctrl+Shift+Z")
        if redo_alt_sequence in QKeySequence.keyBindings(QKeySequence.Redo):
            self._redo_shortcut_alt = self._redo_shortcut
        else:
            self._redo_shortcut_alt = QShortcut(
                redo_alt_sequence, self, activated=self._redo
            )
        redo_primary_text = QKeySequence(QKeySequence.Redo).toString(
            QKeySequence.NativeText
        )
        redo_alt_text = redo_alt_sequence.toString(QKeySequence.NativeText)
        redo_keys = (
            redo_primary_text
            if redo_alt_text == redo_primary_text
            else f"{redo_primary_text}, {redo_alt_text}"
        )
        self._redo_action.setToolTip(f"Redo ({redo_keys})")

        bar.addSeparator()
        bar.addWidget(self._search)
        for sequence in (QKeySequence.Find, QKeySequence("Ctrl+P")):
            QShortcut(sequence, self, activated=self._focus_search)

    def _build_export_button(self) -> QToolButton:
        """The toolbar's Export control: a flat button whose click opens a
        two-item format menu ("Export as JSON...", "Export as YAML...")
        rather than one combined save-dialog filter the user had to type an
        extension into. ``InstantPopup`` makes the whole button, not just a
        caret, open the menu -- there is no separate "default" export format
        to warrant ``MenuButtonPopup``'s split behaviour.
        """
        button = QToolButton(self)
        button.setObjectName("ExportButton")
        button.setText("Export")
        button.setAutoRaise(True)
        button.setPopupMode(QToolButton.InstantPopup)
        button.setToolButtonStyle(Qt.ToolButtonTextOnly)
        menu = QMenu(button)
        menu.addAction("Export as JSON…", lambda: self._export_as("json"))
        menu.addAction("Export as YAML…", lambda: self._export_as("yaml"))
        button.setMenu(menu)
        return button

    def _focus_search(self) -> None:
        """Focus the search box and select its text so it can be replaced."""
        self._search.setFocus()
        self._search.selectAll()

    def _build_central(self) -> None:
        # Editor view: three-panel splitter, plus its own empty-state hint
        # when no document is open (EditorPage owns that rendering).
        self._editor_page = EditorPage(self._tree, self._params, self._inspector)

        # Workspace stack pages. Page indices are fixed by add order (Editor
        # then Diagnostics then Workspace) so _EDITOR_PAGE_INDEX stays valid;
        # the activity bar's add_view order below controls only the VISUAL
        # order of the left-rail entries, which is Workspace, Editor,
        # Diagnostics.
        self._stack = QStackedWidget()
        self._stack.addWidget(self._editor_page)  # _EDITOR_PAGE_INDEX
        self._stack.addWidget(self._diagnostics)  # _DIAGNOSTICS_PAGE_INDEX
        self._stack.addWidget(self._workspace)   # _WORKSPACE_PAGE_INDEX
        self._stack.addWidget(self._source)      # _SOURCE_PAGE_INDEX

        self._btn_workspace = self._activity_bar.add_view(
            "Workspace", page_index=_WORKSPACE_PAGE_INDEX, icon=icons.activity_icon(icons.WORKSPACE)
        )
        self._btn_editor = self._activity_bar.add_view(
            "Editor", page_index=_EDITOR_PAGE_INDEX, icon=icons.activity_icon(icons.EDITOR)
        )
        self._btn_source = self._activity_bar.add_view(
            "Source", page_index=_SOURCE_PAGE_INDEX, icon=icons.activity_icon(icons.SOURCE)
        )
        self._btn_diagnostics = self._activity_bar.add_view(
            "Diagnostics", page_index=_DIAGNOSTICS_PAGE_INDEX, icon=icons.activity_icon(icons.DIAGNOSTICS)
        )

        # Page header + stack form the content column; it sits beside the
        # activity bar so the header spans the content width only.
        self._page_header = PageHeader()
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(self._page_header)
        content_layout.addWidget(self._stack, 1)

        # Assemble the central layout.
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._activity_bar)
        layout.addWidget(content, 1)
        self.setCentralWidget(central)

        # Default landing: with no document open, start on the Workspace
        # page rather than the Editor (which has nothing to show yet). Gated
        # on there being no active session so a future preload (file
        # argument, recent document) correctly lands on Editor instead.
        if self._state.active is None:
            self._show_page(_WORKSPACE_PAGE_INDEX)
        else:
            self._show_page(_EDITOR_PAGE_INDEX)

    def _build_statusbar(self) -> None:
        bar = QStatusBar()
        bar.addPermanentWidget(self._status_label, 1)
        # The installed validator's version, permanently visible: every
        # verdict this app shows is that package's, and an environment that
        # drifts from the tested pin should be spottable at a glance rather
        # than silent (the document's own Header.BPX is a separate fact,
        # shown on the Workspace info card).
        version_label = QLabel(f"bpx {BPX_VERSION}")
        version_label.setToolTip(
            "Installed bpx package - the validator every verdict in "
            "this app comes from"
        )
        bar.addPermanentWidget(version_label)
        self.setStatusBar(bar)

    def _connect(self) -> None:
        # All navigation flows through the single NavigationService: object and
        # parameter clicks, validation issues, the Issues tab and search all
        # request navigation, and the views reveal the resolved target.
        self._navigation.navigated.connect(self._on_navigated)
        self._tree.node_selected.connect(self._navigation.navigate)
        self._tree.add_section_requested.connect(self._on_add_section_requested)
        self._tree.rename_requested.connect(self._on_rename_requested)
        self._tree.remove_requested.connect(self._on_remove_section_requested)
        self._params.parameter_selected.connect(self._navigation.navigate)
        self._params.add_parameter_requested.connect(self._on_add_parameter_requested)
        self._params.remove_parameter_requested.connect(self._on_remove_parameter_requested)
        self._params.rename_parameter_requested.connect(self._on_rename_parameter_requested)
        self._params.duplicate_parameter_requested.connect(self._on_duplicate_parameter_requested)
        self._params.move_parameter_requested.connect(self._on_move_parameter_requested)
        self._params.ghost_selected.connect(self._on_ghost_selected)
        self._diagnostics.issue_activated.connect(self._navigation.navigate)
        self._diagnostics.task_activated.connect(self._on_task_activated)
        self._inspector.issue_activated.connect(self._navigation.navigate)
        self._search.navigation_requested.connect(self._navigation.navigate)
        self._search.dismissed.connect(self._tree.focus_tree)
        self._inspector.committed.connect(self._on_committed)
        self._activity_bar.view_requested.connect(self._on_view_changed)
        self._workspace.open_requested.connect(self._open)
        self._workspace.new_requested.connect(self._new)
        self._workspace.file_dropped.connect(self._on_file_dropped)
        self._workspace.open_reference_requested.connect(self._open_reference)
        self._workspace.open_library_requested.connect(self._open_reference_library)
        self._workspace.new_from_file_requested.connect(self._new_from_file)
        self._workspace.remove_reference_requested.connect(self._on_remove_reference_requested)

    # --- navigation -----------------------------------------------------
    def _on_view_changed(self, page_index: int) -> None:
        """Switch the workspace.  The Inspector (and its secondary workspace)
        lives on the editor page, so leaving the editor hides it naturally."""
        self._show_page(page_index)

    def _show_page(self, page_index: int) -> None:
        """Make *page_index* the current workspace page, keeping the activity
        bar's selected entry -- and the page header's title -- in sync so
        neither the left rail nor the header ever disagrees with the stack.
        Setting a button's checked state programmatically does not emit
        ``view_requested``, so this cannot re-trigger navigation."""
        self._stack.setCurrentIndex(page_index)
        self._activity_bar.select(page_index)
        self._page_header.set_title(self._activity_bar.label_for(page_index))
        # Stale-on-disk is checked on notice, never watched;
        # entering the Source page is one of the two notice points (the
        # other is window activation, see ``changeEvent``).
        if page_index == _SOURCE_PAGE_INDEX:
            self._check_reference_stale()
            self._source.focus_view()

    def navigate_to(self, path: tuple) -> None:
        """Request navigation to *path* through the shared NavigationService.

        A thin public entry point so external callers (deep links, drag-and-
        drop, automation) can navigate without reaching into the service.
        """
        self._navigation.navigate(tuple(path))

    def _on_navigated(self, target: NavigationTarget) -> None:
        """Dispatch a resolved navigation target to each view's reveal.

        The tree, parameter list and Inspector live only on the Editor page,
        so any navigation -- from Search, a validation issue or the Issues
        tab -- must first make that page current, however the user reached
        the app; otherwise a reveal from another page lands on hidden
        widgets. This is wiring only: the views own their reveal behaviour
        and the service owns resolution and state; MainWindow merely
        switches to the page that hosts them and fans the notification out.
        """
        self._show_page(_EDITOR_PAGE_INDEX)
        self._tree.reveal(target.object_path)
        document = self._state.active.document if self._state.active else None
        model = structure.infer_model(document.raw) if document else None
        self._params.reveal(target.node, target.parameter_path, model)
        self._inspector.reveal(target.parameter)

    def _on_task_activated(self, task) -> None:
        """Dispatch one Outstanding row's activation by kind.

        Polymorphic by design -- unlike an Issue, a task's target may not
        exist yet, so this cannot route through ``NavigationService`` alone:

        * ``MISSING_FIELD`` -- navigate to the *owning section* (the field
          itself has no address to resolve), then reveal the synthetic
          suggestion row via the parameter list's seam
          (``reveal_missing_alias``). No mutation; the group's own "+" does
          that.
        * ``NULL_FIELD`` -- the parameter already exists (a committed null),
          so it navigates like any other parameter.
        * ``MISSING_SECTION`` -- there is nothing to navigate to first, so
          this adds the section (one ``AddSection`` undo step) and navigates
          into it in the same motion as every other structural add
          (``_on_add_section_requested``).
        * ``DECLARE_MODEL`` -- ``Header.Model`` is either absent (a "fields to
          add" suggestion row, like ``MISSING_FIELD``) or present but
          unrecognised (a real committed parameter, like ``NULL_FIELD``); this
          navigates to ``Header`` and tries the suggestion reveal first,
          falling back to navigating straight to the parameter when there is
          no such suggestion (``reveal_missing_alias`` returns False once the
          field already exists).
        """
        if task.kind is TaskKind.MISSING_FIELD:
            self._navigation.navigate(task.path[:-1])
            self._params.reveal_missing_alias(task.alias)
        elif task.kind is TaskKind.NULL_FIELD:
            self._navigation.navigate(task.path)
        elif task.kind is TaskKind.MISSING_SECTION:
            self._on_add_section_requested(task.path[:-1], task.path[-1])
        elif task.kind is TaskKind.DECLARE_MODEL:
            self._navigation.navigate(task.path[:-1])
            if not self._params.reveal_missing_alias(task.alias):
                self._navigation.navigate(task.path)

    def _on_add_parameter_requested(self, section_path: tuple, alias: str, seed: object) -> None:
        """Add a custom parameter to *section_path* and reveal it.

        Routes through the existing ``AddParameter`` command with *seed* as
        the initial value -- ``None`` (an honest empty value) for a schema
        suggestion, or a type-matching seed (0.0/""/False/table/list) from
        the add-parameter popup's inline custom-parameter form, so the new
        parameter lands on its matching card straight away
        (``core.parameter_types.classify``). Either way the validator, not
        the UI, judges whether the resulting alias/value is legal.
        Refresh-then-navigate mirrors ``_on_committed``: the document is
        rebuilt first, then the new parameter is revealed through the single
        ``NavigationService``.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        session.execute_command(AddParameter(tuple(section_path), alias, seed))
        target = session.selected_parameter_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _on_remove_parameter_requested(self, parameter_path: tuple) -> None:
        """Remove a parameter via its row's context menu (or Delete key).

        Routes through the existing ``RemoveParameter`` command -- the same
        execute/undo seam ``_on_add_parameter_requested`` uses. The command's
        result carries no parameter selection, so navigating to the owning
        object afterwards naturally clears the removed parameter's selection
        (the Inspector falls back to its placeholder) rather than leaving it
        dangling on a row that no longer exists.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        session.execute_command(RemoveParameter(tuple(parameter_path)))
        target = session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _on_rename_parameter_requested(self, parameter_path: tuple) -> None:
        """Open the row's own card-header rename editor (one rename surface --
        see ``cards.parameter_card.ParameterCard.open_rename_editor``).

        Navigates to the parameter first so the Inspector is showing its
        card, then asks that card to expand its inline row -- no command
        runs here; the card's own "Apply" is what does that.
        """
        self._navigation.navigate(tuple(parameter_path))
        self._inspector.open_rename_editor()

    def _on_duplicate_parameter_requested(self, parameter_path: tuple) -> None:
        """Duplicate a parameter via its row's context menu.

        Routes through ``DuplicateParameter``, whose own ``CommandResult``
        selects the new sibling key (``command_service.execute``), so
        navigating to ``selected_parameter_path`` afterwards lands the user
        on the duplicate, not the original.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        path = tuple(parameter_path)
        session.execute_command(DuplicateParameter(path[:-1], path[-1]))
        target = session.selected_parameter_path or session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _on_move_parameter_requested(self, parameter_path: tuple, direction: str) -> None:
        """Reorder a parameter one position via its row's context menu.

        The menu only offers a legal direction (disabled at the first/last
        row), so a refusal here would be a menu-gating bug, not user error.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        path = tuple(parameter_path)
        session.execute_command(MoveParameter(path[:-1], path[-1], direction))
        target = session.selected_parameter_path or session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _on_add_section_requested(self, parent_path: tuple, key: str) -> None:
        """Add the object section *key* under *parent_path* and reveal it.

        One handler for both menu flavours -- a schema-named child section and
        a user-named material/experiment -- because both are exactly an
        ``AddSection``. The menu/popup already scoped what is offerable, so a
        backend refusal here is nothing to swallow silently.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        session.execute_command(AddSection(tuple(parent_path), key))
        target = session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _on_rename_requested(self, path: tuple, new_name: str) -> None:
        """Rename the user-named key at *path* and reveal its new address."""
        session = self._state.active
        if session is None or session.document is None:
            return
        session.execute_command(RenameKey(tuple(path), new_name))
        target = session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _on_remove_section_requested(self, path: tuple) -> None:
        """Remove the section at *path*, confirming first when it has content.

        The command's own preview supplies the "not empty" warning, so the
        confirmation threshold and the backend can never disagree about what
        counts as populated. An empty section removes instantly; undo restores
        either as one step.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        command = RemoveSection(tuple(path))
        preview = session.preview_command(command)
        if preview.warnings and not self._confirm_populated_removal(path[-1]):
            return
        session.execute_command(command)
        target = session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    def _confirm_populated_removal(self, label: str) -> bool:
        """Ask before destroying content; Cancel is the default (safe) answer."""
        from PySide6.QtWidgets import QMessageBox

        choice = QMessageBox.question(
            self,
            "Remove section",
            f"“{label}” is not empty. Remove it and everything it contains?\n"
            "Undo restores it.",
            QMessageBox.Yes | QMessageBox.Cancel,
            QMessageBox.Cancel,
        )
        return choice == QMessageBox.Yes

    def _on_committed(self) -> None:
        if self._state.active is None:
            return
        kept = (
            self._state.active.selected_parameter_path
            or self._state.active.selected_path
        )
        self._refresh_all()
        if kept:
            self._navigation.navigate(kept)

    # --- undo -----------------------------------------------------------
    def _undo(self) -> None:
        """``Ctrl+Z``: undo the focused editor's own work, else the document.

        A window-level shortcut is matched *before* the focused widget sees the
        key, so an unguarded ``Ctrl+Z`` would steal undo from every text field
        in the app -- the search box included. Dispatch therefore consults the
        focus widget first and hands the key back to it.

        Where an editor has no undo of its own, the key still must not reach
        the document while that editor holds an uncommitted draft: a spin box
        or a combo box cannot undo its own change, and reverting the *previous*
        commit instead would silently alter a parameter the user is not looking
        at. In that state ``Ctrl+Z`` does nothing -- exactly as it does in a
        native spin box. Escape reverts the draft, and the toolbar's Undo
        button remains available for the document.

        Once the draft is committed the card is rebuilt around a fresh widget
        with no history and no dirt, so the next ``Ctrl+Z`` reaches the
        document.
        """
        # Focus is read from *this window*, not QApplication: a WindowShortcut
        # only fires while this window is active, so the two agree whenever it
        # matters, and the window's own focus widget is never confused by an
        # active popup that owns its own text field. A compound editor reports
        # itself, not its internal line edit -- a focused QSpinBox is a
        # QSpinBox -- which is why step 1 below cannot match one.
        widget = self.focusWidget()
        if self._undo_focused_editor(widget):
            return
        if self._inspector.has_focused_draft(widget):
            return
        self._undo_document()

    def _undo_document(self) -> None:
        """Revert the last committed change, whatever holds keyboard focus.

        This is what the toolbar's Undo button does: it is a document command,
        like Save and Export beside it, and a toolbar button takes no focus.

        ``DocumentSession.undo`` restores the selection that was current when
        the command ran, so navigating to it reveals the reverted change rather
        than leaving the user where they happened to be. That selection was
        valid in the restored document, so no existence check is needed here.
        """
        session = self._state.active
        if session is None or not session.can_undo:
            return
        session.undo()
        target = session.selected_parameter_path or session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    @staticmethod
    def _undo_focused_editor(widget) -> bool:
        """Undo one step inside *widget* when it is a text editor; True if it did.

        Returns False when *widget* is not a text editor, or is one with an
        empty undo history. Any text widget qualifies, not just a card's: the
        search box must keep the ``Ctrl+Z`` this shortcut intercepted from it.
        """
        if isinstance(widget, QLineEdit):
            if widget.isUndoAvailable():
                widget.undo()
                return True
        elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
            if widget.document().isUndoAvailable():
                widget.undo()
                return True
        return False

    # --- redo -------------------------------------------------------------
    def _redo(self) -> None:
        """``Ctrl+Y`` / ``Ctrl+Shift+Z``: redo the focused editor's own work,
        else the document.

        Mirrors ``_undo`` exactly, including why: a window-level shortcut is
        matched before the focused widget sees the key, so an unguarded redo
        would steal it from every text field, the search box included. A
        focused card holding an uncommitted draft is left alone too --
        reapplying a commit while a card holds a draft would silently alter a
        parameter the user is not looking at.
        """
        widget = self.focusWidget()
        if self._redo_focused_editor(widget):
            return
        if self._inspector.has_focused_draft(widget):
            return
        self._redo_document()

    def _redo_document(self) -> None:
        """Reapply the last undone change, whatever holds keyboard focus.

        This is what the toolbar's Redo button does: it is a document
        command, like Undo beside it, and a toolbar button takes no focus.

        ``DocumentSession.redo`` restores the selection that was current when
        the redone command ran, so navigating to it reveals the change rather
        than leaving the user where they happened to be. That selection was
        valid in the restored document, so no existence check is needed here.
        """
        session = self._state.active
        if session is None or not session.can_redo:
            return
        session.redo()
        target = session.selected_parameter_path or session.selected_path
        self._refresh_all()
        if target:
            self._navigation.navigate(target)

    @staticmethod
    def _redo_focused_editor(widget) -> bool:
        """Redo one step inside *widget* when it is a text editor; True if it did.

        Mirrors ``_undo_focused_editor``. Returns False when *widget* is not a
        text editor, or is one with an empty redo history.
        """
        if isinstance(widget, QLineEdit):
            if widget.isRedoAvailable():
                widget.redo()
                return True
        elif isinstance(widget, (QPlainTextEdit, QTextEdit)):
            if widget.document().isRedoAvailable():
                widget.redo()
                return True
        return False

    # --- file actions ---------------------------------------------------
    def open_document(self, path: Path) -> None:
        """Open a BPX file by path and refresh every view.

        This is the file-open operation independent of any file dialog, so it
        can be driven by drag-and-drop, a recent-files list, deep links or
        automation. Raises :class:`core.bpx_gateway.LoadError` for unparseable
        files and ``OSError`` if the file cannot be read; callers arriving via
        a dialog surface these as a message box.
        """
        self._state.open(Path(path))
        self._params.reset_expansion_state()
        self._diagnostics.reset_view_state()
        self._refresh_all()
        self._show_page(_EDITOR_PAGE_INDEX)

    def _has_unsaved_work(self) -> bool:
        """Whether anything would be lost by replacing the active document.

        Wider than ``session.dirty``: a card draft the user typed but never
        pressed Enter on is not in the document at all, so ``dirty`` stays
        False while a real edit sits on screen. Every guard that protects
        against discarding work asks this instead, so the draft goes through
        the same Save/Discard/Cancel prompt a committed edit does -- and
        "Save" applies it on the way out (see :meth:`_save`).
        """
        session = self._state.active
        if session is None:
            return False
        return session.dirty or self._inspector.has_pending_draft()

    def _confirm_discard_if_dirty(self) -> bool:
        """Guard against silently discarding unsaved changes.

        Reusable by any action that replaces the active document (Open now;
        New and drag-and-drop later). Returns True when it is safe to
        proceed with the destructive action: there is no active session, the
        active session is not dirty, or the user chose "Don't Save". Returns
        False when the caller must abort: the user chose "Cancel", or chose
        "Save" but the save did not actually complete (the Save As dialog
        was cancelled, or the save failed) -- in that case discarding would
        still lose data, so the guard refuses to proceed.
        """
        session = self._state.active
        if session is None or not self._has_unsaved_work():
            return True
        choice = QMessageBox.question(
            self,
            "Unsaved changes",
            "This document has unsaved changes. Save before continuing?",
            QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel,
            QMessageBox.Save,
        )
        if choice == QMessageBox.Discard:
            return True
        if choice == QMessageBox.Cancel:
            return False
        return self._save()

    def _confirm_new(self) -> bool:
        """Guard for New: never replace an open document silently.

        A dirty document goes through the same Save/Discard/Cancel guard as
        Open. A clean one still gets a lightweight Ok/Cancel confirm: the
        file on disk loses nothing, but a single click on a model button
        would otherwise wipe the open document with no warning at all --
        Open asks before replacing the main, so New must too. Returns True
        when it is safe to replace the active session.
        """
        session = self._state.active
        if session is None:
            return True
        if self._has_unsaved_work():
            return self._confirm_discard_if_dirty()
        filename = (
            session.backing_file.name
            if session.backing_file is not None
            else session.document.filename
        )
        choice = QMessageBox.question(
            self,
            "New document",
            f"This will replace {filename}. Continue?",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )
        return choice == QMessageBox.Ok

    def _open(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, "Open BPX", "", BPX_FILTER)
        if not name:
            return
        self._open_chosen_path(Path(name))

    def _open_path(self, path: Path | str) -> None:
        """Open *path*, showing the load-error dialog on parse/OS failure.

        The guard-less half of Open: callers (the Open dialog, drag-and-drop)
        each run ``_confirm_discard_if_dirty`` themselves first, then share
        this single error-handling path so it exists in one place.
        """
        try:
            self.open_document(Path(path))
        except (LoadError, OSError) as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))

    def _open_chosen_path(self, path: Path) -> None:
        """Route a chosen file (Open dialog or drop) to main or reference.

        With no document open, this behaves exactly as before -- straight to
        main, no dialog. With a document already open, :meth:`_ask_open_intent`
        decides: replace the main (today's discard-guarded open), dock/replace
        the reference (no discard guard needed -- the main is untouched), or
        cancel (nothing happens, reference untouched either way).
        """
        if self._state.active is not None:
            intent = self._ask_open_intent(path.name)
            if intent is OpenIntent.CANCEL:
                return
            if intent is OpenIntent.ADD_REFERENCE:
                self._open_reference_path(path)
                return
            if not self._confirm_discard_if_dirty():
                return
        self._open_path(path)

    def _ask_open_intent(self, filename: str) -> OpenIntent:
        """Ask how to open *filename* when a document is already active.

        Overridable seam: headless tests monkeypatch this method directly to
        bypass the real (blocking) dialog; one test exercises the actual
        ``QMessageBox`` via the zero-delay popup-close idiom instead.
        """
        box = QMessageBox(self)
        box.setWindowTitle(f"Open {filename}")
        box.setText("A document is already open. Open this file as:")
        replace_main = box.addButton("Replace main", QMessageBox.AcceptRole)
        # One stable label: pinning appends, so this choice never replaces
        # anything. At the cap it is the one control that cannot act, so it
        # goes grey and says why rather than silently refusing after the click.
        replace_reference = box.addButton("Pin as reference", QMessageBox.ActionRole)
        if self._state.at_reference_cap:
            replace_reference.setEnabled(False)
            replace_reference.setToolTip(AT_CAP_MESSAGE)
        box.addButton("Cancel", QMessageBox.RejectRole)
        box.setDefaultButton(replace_main)
        box.exec()
        clicked = box.clickedButton()
        if clicked is replace_main:
            return OpenIntent.REPLACE_MAIN
        if clicked is replace_reference:
            return OpenIntent.ADD_REFERENCE
        return OpenIntent.CANCEL

    def _open_reference(self) -> None:
        """Open File as Reference: pick a file and dock it, unconditionally.

        No discard guard and no open-intent choice -- the user has already
        said what they want, and docking a reference never touches the main
        document.
        """
        name, _ = QFileDialog.getOpenFileName(self, "Open BPX", "", BPX_FILTER)
        if not name:
            return
        self._open_reference_path(Path(name))

    def _open_reference_path(self, path: Path) -> None:
        """Pin *path* as a reference, showing a toast for the outcome.

        Load failure surfaces through the same error-dialog pattern as the
        main Open flow. Only a genuine pin (``ADDED``) recomputes the
        comparison -- every no-op outcome (already pinned, is-main, at the
        cap) changes nothing to recompute.
        """
        try:
            outcome = self._state.pin_reference(path)
        except (LoadError, OSError) as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))
            return
        message = {
            PinReferenceOutcome.ADDED: f"Pinned {path.name} as reference",
            PinReferenceOutcome.ALREADY_REFERENCE: "Already pinned as reference",
            PinReferenceOutcome.IS_MAIN: "Already open as the main file",
            PinReferenceOutcome.AT_CAP: AT_CAP_MESSAGE,
        }[outcome]
        self._toast.show_message(message)
        if outcome is PinReferenceOutcome.ADDED:
            self._recompute_comparison()
            # A fresh dock/replace re-truths the stale band (a leftover
            # band from the previous reference must not survive it).
            self._check_reference_stale()
        self._update_workspace_info()

    def _open_reference_library(self) -> None:
        """From the reference library…: choose a bundled set and dock it.

        The dialog is a pure chooser holding no app state, so cancelling
        changes nothing. Kept separate from :meth:`_dock_reference_set` so
        headless tests can drive the dock path without the blocking
        ``exec``.
        """
        dialog = ReferenceLibraryDialog(self)
        if dialog.exec() != QDialog.Accepted:
            return
        set_id = dialog.selected_set_id()
        if set_id:
            self._dock_reference_set(set_id)

    def _dock_reference_set(self, set_id: str) -> None:
        """Pin library set *set_id*, mirroring ``_open_reference_path``:
        toast the outcome, and only a genuine pin (``ADDED``) recomputes the
        comparison. ``IS_MAIN`` cannot occur for a bundled set. The stale
        re-check matters here too: a band left over from a removed file
        reference must not survive the pin (the path-less snapshot itself
        can never go stale).
        """
        try:
            outcome = self._state.pin_reference_set(set_id)
        except (KeyError, LoadError, OSError) as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))
            return
        message = {
            PinReferenceOutcome.ADDED: (
                f"{self._state.references[-1].filename} · pinned as reference"
            ),
            PinReferenceOutcome.ALREADY_REFERENCE: "Already pinned as reference",
            PinReferenceOutcome.AT_CAP: AT_CAP_MESSAGE,
        }[outcome]
        self._toast.show_message(message)
        if outcome is PinReferenceOutcome.ADDED:
            self._recompute_comparison()
            self._check_reference_stale()
        self._update_workspace_info()

    def _on_remove_reference_requested(self, reference: ReferenceSnapshot) -> None:
        """Unpin the reference the Workspace row's Remove points at, leaving
        every other pin in place."""
        self._state.remove_reference(reference)
        self._recompute_comparison()
        self._update_workspace_info()

    # --- comparison ----------------------------------------------------------

    def _recompute_comparison(self) -> None:
        """Recompute the reference comparisons from the current document +
        pinned references and push them to every view.

        Called once per document change (via ``_refresh_all``) and once
        whenever a reference is pinned/removed -- never incrementally
        (``core.compare.compare`` re-walks both raw dicts). One ``compare()``
        call per pinned snapshot, up to the cap of four; no caching in this
        track, by explicit decision.
        """
        document = self._state.active.document if self._state.active else None
        self._comparisons = (
            [compare(document.raw, reference.raw) for reference in self._state.references]
            if document is not None
            else []
        )
        self._apply_comparison()

    def _pins(self) -> list[ReferencePin]:
        """The pinned references paired with their comparisons and badge
        identity -- built here, once, and threaded outward, so no widget can
        disagree with another about which reference "Ch" is."""
        return build_pins(self._state.references, self._comparisons)

    def _apply_comparison(self) -> None:
        """Push the current comparisons to the tree/list/inspector -- the
        single fan-out point every comparison-state change goes through."""
        pins = self._pins()
        self._tree.set_comparison(self._comparisons)
        self._params.set_comparison(pins)
        self._inspector.set_comparison(pins)
        # The Source page re-renders here too: every route that changes what
        # it must show (edit, undo/redo, open/new, reference pin/remove)
        # already funnels through this method.
        session = self._state.active
        document = session.document if session is not None else None
        # The pane header names the file the way the title bar does: the
        # backing file once one exists, the document's own filename before.
        self._source.refresh(
            document.raw if document is not None else None,
            pins,
            main_name=self._fallback_filename(session) if session is not None else "",
            main_model=document.identity.model if document is not None else None,
            selected=self._source_reference_index,
        )

    def _check_reference_stale(self) -> None:
        """Compare the docked reference's recorded mtime against disk and
        show/hide the Source page's stale band accordingly.

        On notice only (Source page entry, window activation, reference
        dock/swap/reload) -- no file watching. A stat failure
        (file vanished, permissions) never conjures a band: the snapshot in
        the panes is still exactly what the user is reading, and Reload's
        own error path is where an unreadable file gets surfaced.
        """
        stale = []
        for reference in self._state.references:
            # A bundled library set has no file to go stale against.
            if reference.path is None:
                continue
            try:
                on_disk = reference.path.stat().st_mtime
            except OSError:
                continue
            if on_disk != reference.mtime:
                stale.append(reference.filename)
        # Every pin is checked, not just the one the Source page shows: a
        # reference going stale off screen is exactly the case a band that
        # only watched the first pin would miss in silence.
        self._source.set_stale_names(stale)

    def _on_source_reference_selected(self, index: int) -> None:
        """The Source page's selector chose a different pinned reference.

        Re-renders through the standard fan-out rather than poking the page:
        the pane rows, the stale band and the ← pull arrows all read the
        selection, so they must move together.
        """
        self._source_reference_index = index
        self._apply_comparison()
        self._check_reference_stale()

    def _on_reload_reference(self) -> None:
        """The stale band's Reload: re-snapshot the reference from disk and
        recompute -- never silently (the band's click is the consent).

        Reloads whichever reference the Source page is showing, not merely
        the first pinned. An unreadable file gets the standard "Cannot open
        file" error; the pinned snapshot and the band stay exactly as they
        were.
        """
        try:
            self._state.reload_reference(self._source.selected_reference_index())
        except (LoadError, OSError) as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))
            return
        self._recompute_comparison()
        self._check_reference_stale()
        self._update_workspace_info()

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Window activation is the second stale-notice point: coming back
        from another app is exactly when the file may have changed
        underneath the snapshot."""
        super().changeEvent(event)
        if event.type() == QEvent.ActivationChange and self.isActiveWindow():
            self._check_reference_stale()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        """Closing the window is the one document-losing exit that used to
        skip the discard guard entirely: Open, New and Make main all ask
        before replacing a dirty document, so the X button and Alt+F4 must
        too. ``_suppress_close_guard`` lets test teardown (and any other
        programmatic shutdown that has already made its own decision) close
        without a modal prompt.
        """
        if self._suppress_close_guard or self._confirm_discard_if_dirty():
            event.accept()
        else:
            event.ignore()

    def _on_source_pull(self, path, is_section: bool) -> None:
        """A ← gutter pull on the Source page: copy the reference's raw
        value at *path* into the main document, verbatim, via the shared
        commands -- one undo entry, undoable from any page.

        The pull stays on the Source page: its rhythm
        is next ›, pull, next ›, pull, so unlike ``_on_committed`` this
        never navigates -- confirmation is the row's transient "Pulled"
        tag plus a toast, and the Editor is opt-in via the toast's Show
        in Editor action (or a row double-click, as ever).
        """
        # The reference the Source page is showing, not merely the first
        # pinned: the ← arrows sit beside its pane, so they must pull from it.
        index = self._source.selected_reference_index()
        references = self._state.references
        reference = references[index] if 0 <= index < len(references) else None
        session = self._state.active
        if reference is None or session is None:
            return
        value = reference.raw
        for key in path:
            if not isinstance(value, dict) or key not in value:
                return  # stale click: the reference no longer has this path
            value = value[key]
        path = tuple(path)
        # Named, like every other write: the undo entry says which file the
        # value came from, so the Source page's pull is not the one write
        # path whose history is anonymous.
        command = (
            PullSection(path, value, source_label=reference.filename)
            if is_section
            else PullParameter(path, value, source_label=reference.filename)
        )
        session.execute_command(command)
        # Commands do not self-propagate: fan the commit out to every page
        # (recomputing the comparison, so this page re-renders the row as
        # equal) -- then confirm in place instead of navigating.
        self._refresh_all()
        self._source.flash_pulled(path)
        self._toast.show_message(
            f"Pulled {path[-1]}",
            action_text="Show in Editor",
            action=lambda: self._navigation.navigate(path),
        )

    def _on_ghost_selected(self, section_path: tuple, key: str) -> None:
        """A REF_ONLY ghost row was selected in the parameter list: show its
        read-only ghost card, bypassing ``NavigationService`` entirely (a
        ghost row names no real document parameter for it to resolve)."""
        self._inspector.show_ghost_parameter(tuple(section_path), key)

    def _on_file_dropped(self, path: str) -> None:
        """Open a file dropped onto the Workspace page.

        Routes through :meth:`_open_chosen_path`, exactly like the Open
        dialog.
        """
        self._open_chosen_path(Path(path))

    def _new(self, model: str) -> None:
        """Create a fresh incomplete document scaffold for *model*.

        Goes through :meth:`_confirm_new` before replacing the active
        session -- Save/Discard/Cancel when dirty, a replace confirm even
        when clean -- then lands on the Editor page so the user can start
        filling in the new document.
        """
        if not self._confirm_new():
            return
        self._state.new_document(model)
        self._params.reset_expansion_state()
        self._diagnostics.reset_view_state()
        self._refresh_all()
        self._show_page(_EDITOR_PAGE_INDEX)

    def _new_from_file(self) -> None:
        """New from an existing file: clone it into a fresh unsaved session and
        dock the origin as the read-only reference.

        Picker first, then the same guard as New -- nobody should answer a
        replace prompt before a file is even chosen. The state change is
        atomic (``AppState.new_from_file`` loads both files before touching
        state), so a load failure after the guard leaves the previous
        session open and any docked reference in place. Unlike New, the
        flow stays on the Workspace page: both role
        cards confirm at a glance what was just set up.
        """
        name, _ = QFileDialog.getOpenFileName(
            self, "New from Existing File", "", BPX_FILTER
        )
        if not name:
            return
        if not self._confirm_new():
            return
        path = Path(name)
        try:
            outcome = self._state.new_from_file(path)
        except (LoadError, OSError) as exc:
            QMessageBox.critical(self, "Cannot open file", str(exc))
            return
        self._params.reset_expansion_state()
        self._diagnostics.reset_view_state()
        self._refresh_all()
        # D2: the new document is created either way; only the pin can fail,
        # and the toast says which of the two happened rather than claiming a
        # pin that was refused.
        if outcome is PinReferenceOutcome.AT_CAP:
            self._toast.show_message(
                f"New document from {path.name} · not pinned ({AT_CAP_MESSAGE})"
            )
        else:
            self._toast.show_message(f"New document from {path.name} · pinned as reference")

    def _save(self) -> bool:
        """Write the document to its backing file.

        If no backing file is set (unsaved new document), a Save As dialog
        is shown first. Does not affect export copies. Returns True once the
        document has actually been written, False if there was nothing to
        save, the Save As dialog was cancelled, or the write failed -- used
        by :meth:`_confirm_discard_if_dirty` to decide whether it is safe to
        proceed with a destructive action.

        A card draft the user typed but never pressed Enter on is applied
        first, the way every spreadsheet and form commits its active editor
        on save: what is on screen is what reaches the file. The apply is an
        ordinary command, so Ctrl+Z takes it back.
        """
        if self._state.active is None:
            return False
        if not self._inspector.apply_pending_draft():
            # The draft cannot be written at all and the card says why
            # inline. Saving anyway would quietly write a file that does not
            # contain what the user is looking at.
            return False
        session = self._state.active
        adopted_backing = False
        if session.backing_file is None:
            # A never-saved main's Save As starts in the last Save As folder
            # this run, else Documents -- never wherever the app happens to run
            # from (which could be a bundled directory). The document's own
            # filename seeds the name.
            start_dir = self._save_dialog_dir or Path(
                QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
            )
            suggested = session.document.filename if session.document else ""
            name, _ = QFileDialog.getSaveFileName(
                self, "Save BPX",
                str(start_dir / suggested) if suggested else str(start_dir),
                BPX_FILTER,
            )
            if not name:
                return False
            session.backing_file = Path(name)
            adopted_backing = True
            self._save_dialog_dir = Path(name).parent
        try:
            session.save()
        except OSError as exc:
            # A backing file adopted by this very Save As must not outlive a
            # failed write: keeping it would make every later Save retry the
            # same broken path with no dialog (there is no separate Save As
            # action), leaving the document effectively un-savable.
            if adopted_backing:
                session.backing_file = None
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self._update_title()
        self._update_identity_label()
        self._update_workspace_info()
        # A first Save As gives the session its backing file, which renames
        # the Source page's pane header/file label too.
        self._apply_comparison()
        return True

    def _export_as(self, fmt: str) -> None:
        """Write a copy of the document to a user-chosen location in *fmt*
        ("json" or "yaml"), the format the user picked from the Export menu.

        Does not affect the backing file or dirty state. The default name
        and dialog filter both reflect the chosen format, not whatever the
        backing file happened to be saved as -- exporting a .json document
        as YAML proposes "foo (copy).yaml", not "foo (copy).json".

        A card draft the user typed but never pressed Enter on is applied
        first, exactly as :meth:`_save` does -- otherwise the export would
        silently omit what is on screen.
        """
        if self._state.active is None or self._state.active.document is None:
            return
        if not self._inspector.apply_pending_draft():
            # The draft cannot be written at all and the card says why
            # inline -- see _save. Exporting anyway would write a file that
            # does not contain what the user is looking at.
            return
        session = self._state.active
        suffix = ".yaml" if fmt == "yaml" else ".json"
        if session.backing_file is not None:
            backing = session.backing_file
            default = str(backing.with_name(f"{backing.stem} (copy){suffix}"))
        else:
            default = str(Path(session.document.filename).with_suffix(suffix))
        filt = export_filter(fmt)
        name, _ = QFileDialog.getSaveFileName(self, "Export BPX", default, filt)
        if not name:
            return
        try:
            Path(name).write_bytes(export.to_bytes(session.document.raw, fmt))
        except OSError as exc:
            QMessageBox.critical(self, "Export failed", str(exc))

    def _update_title(self) -> None:
        """Sync the OS window title and bottom status bar with session state.

        Shows only the backing file name and dirty/saved state -- the
        document's Title/Model/version identity lives in the top bar instead
        (see :meth:`_update_identity_label`), so no fact is duplicated.
        """
        session = self._state.active
        if session is None or session.document is None:
            self.setWindowTitle("ExploreBPX")
            self._status_label.setText("")
            return
        name = session.backing_file.name if session.backing_file else session.document.filename
        prefix = "* " if session.dirty else ""
        self.setWindowTitle(f"{prefix}{name} \u2014 ExploreBPX")
        state_text = "Modified" if session.dirty else "Saved"
        self._status_label.setText(f"{name}  |  {state_text}")

    def _fallback_filename(self, session: DocumentSession) -> str:
        """The file name to show when a document has no Header Title."""
        if session.backing_file is not None:
            return session.backing_file.name
        return session.document.filename if session.document else ""

    def _compose_identity_text(self) -> str:
        """Compose 'Title \u00b7 BPX vX.Y', omitting any empty field.

        Model is deliberately omitted here: it is edited in the Editor, via
        the normal ``Header.Model`` enum card, like any other parameter.
        """
        session = self._state.active
        if session is None or session.document is None:
            return _NO_DOCUMENT_TEXT
        identity = session.document.identity
        title = identity.title or self._fallback_filename(session)
        segments = [segment for segment in (title,) if segment]
        if identity.bpx_version:
            segments.append(f"BPX v{identity.bpx_version}")
        return " \u00b7 ".join(segments) if segments else _NO_DOCUMENT_TEXT

    def _update_identity_label(self) -> None:
        """Sync the top-bar identity label with the active document."""
        self._identity_label.set_full_text(self._compose_identity_text())

    def _update_workspace_info(self) -> None:
        """Sync the Workspace page's info panel with the active session.

        Error/warning counts come from ``self._workspace_error_count``/
        ``_workspace_warning_count``, cached by ``_refresh_all`` from the same
        ``PartitionedIssues`` the Diagnostics rail badge uses --
        never recomputed here and never read from ``document.error_count``/
        ``warning_count``, so the pill can't disagree with the rest of the app.
        """
        session = self._state.active
        document = session.document if session else None
        filename = self._fallback_filename(session) if document is not None else None
        dirty = session.dirty if session else False
        self._workspace.refresh(
            document,
            filename,
            dirty,
            self._workspace_error_count,
            self._workspace_warning_count,
            references=self._state.references,
        )

    def _update_actions_enabled(self) -> None:
        """Save/Export are only enabled once a document is loaded (a session
        alone is not enough: a session may exist with no document yet), and the
        Undo/Redo *buttons* only once that document has something to undo/redo.

        The ``Ctrl+Z``/``Ctrl+Y``/``Ctrl+Shift+Z`` shortcuts stay live
        regardless: with an empty document history they still have a focused
        text field's typing to undo/redo."""
        session = self._state.active
        has_document = session is not None and session.document is not None
        self._save_action.setEnabled(has_document)
        self._export_action.setEnabled(has_document)
        self._undo_action.setEnabled(has_document and session.can_undo)
        self._redo_action.setEnabled(has_document and session.can_redo)

    @staticmethod
    def _diagnostics_tooltip(errors: int, warnings: int) -> str:
        """Compose the Diagnostics button's tooltip from honest error/warning
        counts, e.g. 'Diagnostics - 2 errors, 1 warning'. A zero side is
        omitted; singular/plural is handled per side."""
        if not errors and not warnings:
            return "Diagnostics"
        parts = []
        if errors:
            parts.append(f"{errors} error" + ("" if errors == 1 else "s"))
        if warnings:
            parts.append(f"{warnings} warning" + ("" if warnings == 1 else "s"))
        return "Diagnostics - " + ", ".join(parts)

    def _refresh_all(self) -> None:
        """Refresh every view from one document snapshot.

        ``tasks``/``partition`` are computed exactly once here:
        the Diagnostics page's Outstanding section, the rail badge and the
        Workspace pill (via the cached ``_workspace_error_count``/
        ``_workspace_warning_count``) all derive from this single
        ``PartitionedIssues``, so they can never disagree about what counts
        as an error. Pre-absorption ``document.error_count``/``warning_count``
        is deliberately not used for any of them -- see
        ``core.completion.partition_issues``.
        """
        document = self._state.active.document if self._state.active else None
        # One derivation point, computed before anything renders: the tree's
        # dot and the parameter list's dot both carry *page-visible* truth,
        # so the partition must exist before set_root paints.
        raw = document.raw if document is not None else None
        model = structure.infer_model(raw) if raw is not None else None
        tasks = completion.document_completion(raw) if raw is not None else ()
        partition = completion.partition_issues(document, tasks) if document is not None else None

        self._editor_page.set_has_document(document is not None)
        if document is not None:
            self._tree.set_root(
                document.tree, completion.visible_error_section_paths(document, partition)
            )
        self._params.show_node(None)
        self._inspector.reset()

        # Stored before any subsequent show_node/reveal renders
        # real rows (those happen later, via a navigation reveal -- show_node
        # above is always called with None here) so the parameter list's dot
        # marker reflects *page-visible* issues, not the validator verbatim.
        self._params.set_visible_issue_severities(
            completion.visible_issue_severities(document, partition)
        )

        buckets = page_buckets.bucket_page_content(raw, model, partition, tasks) if document is not None else None
        self._diagnostics.refresh(buckets, partition, model)
        self._search.index_document(document)
        errors = partition.error_count if partition is not None else 0
        warnings = partition.warning_count if partition is not None else 0
        # Cached so _update_workspace_info (also called after Save, which
        # doesn't re-validate) reuses this one partition instead of deriving
        # its own count -- resets to 0/0 whenever there's no document.
        self._workspace_error_count = errors
        self._workspace_warning_count = warnings
        severity = "error" if errors else ("warning" if warnings else None)
        self._btn_diagnostics.set_badge(errors + warnings, severity)
        # Source is the one rail entry gated on an open document:
        # with none there is no raw JSON to show. If the document ever
        # goes away while Source is current, land on Workspace like startup.
        self._btn_source.setEnabled(document is not None)
        if document is None and self._stack.currentIndex() == _SOURCE_PAGE_INDEX:
            self._show_page(_WORKSPACE_PAGE_INDEX)
        self._btn_diagnostics.setToolTip(self._diagnostics_tooltip(errors, warnings))
        self._update_title()
        self._update_identity_label()
        self._update_workspace_info()
        self._update_actions_enabled()
        # Recompute once per document change (the
        # reference's own dock/undock/replace recomputes separately -- see
        # _open_reference_path/_on_remove_reference_requested).
        self._recompute_comparison()

