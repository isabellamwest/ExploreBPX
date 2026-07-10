"""Main application window: activity bar and workspace stack.

This is wiring only: it owns the single :class:`AppState`, connects panel
signals to state mutations, and refreshes views. No BPX logic lives here.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QSizePolicy,
    QStackedWidget,
    QStatusBar,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import export, structure
from core.bpx_gateway import BPX_VERSION, LoadError
from core.commands import AddParameter, RemoveParameter
from state.app_state import AppState
from state.document_session import DocumentSession

from . import icons
from .activity_bar import ActivityBar
from .editor_page import EditorPage
from .inspector import InspectorPanel
from .navigation import NavigationService, NavigationTarget
from .page_header import PageHeader
from .parameter_list import ParameterListPanel
from .search import SearchBar
from .style import STYLESHEET
from .tree_panel import TreePanel
from .validation_panel import ValidationPanel
from .workspace_panel import WorkspacePanel

_NO_DOCUMENT_TEXT = "No document"
_EDITOR_PAGE_INDEX = 0  # QStackedWidget page hosting the tree/params/inspector
_VALIDATION_PAGE_INDEX = 1
_WORKSPACE_PAGE_INDEX = 2


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
        self.setStyleSheet(STYLESHEET)
        self.resize(1200, 760)
        self._state = AppState()
        self._navigation = NavigationService(self._state)

        self._tree = TreePanel()
        self._params = ParameterListPanel()
        self._inspector = InspectorPanel(self._state)
        self._validation = ValidationPanel()
        self._workspace = WorkspacePanel()
        self._search = SearchBar()
        self._activity_bar = ActivityBar()
        self._identity_label = _IdentityLabel()
        self._status_label = QLabel()

        self._build_toolbar()
        self._build_central()
        self._build_statusbar()
        self._connect()
        self._refresh_all()

    def _build_toolbar(self) -> None:
        """Build the fixed top bar: identity on the left, actions on the right.

        Opening a file lives on the Workspace page's "Open File" button now, so
        the top bar carries no Open action -- only document identity, Save,
        Export and search.
        """
        bar = self.addToolBar("Main")
        bar.addWidget(self._identity_label)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        bar.addWidget(spacer)

        self._save_action = bar.addAction("Save", self._save)
        self._export_action = bar.addAction("Export", self._export)

        # The button is a document command, like its neighbours Save and
        # Export: it never edits whatever widget happens to hold focus. The
        # *keyboard* shortcut lives on a separate QShortcut precisely because
        # it must be focus-aware -- see _undo. Binding the sequence to the
        # action instead would make one indistinguishable from the other.
        self._undo_action = bar.addAction("Undo", self._undo_document)
        undo_keys = QKeySequence(QKeySequence.Undo).toString(QKeySequence.NativeText)
        self._undo_action.setToolTip(f"Undo ({undo_keys})")
        self._undo_shortcut = QShortcut(QKeySequence.Undo, self, activated=self._undo)

        bar.addSeparator()
        bar.addWidget(self._search)
        for sequence in (QKeySequence.Find, QKeySequence("Ctrl+P")):
            QShortcut(sequence, self, activated=self._focus_search)

    def _focus_search(self) -> None:
        """Focus the search box and select its text so it can be replaced."""
        self._search.setFocus()
        self._search.selectAll()

    def _build_central(self) -> None:
        # Editor view: three-panel splitter, plus its own empty-state hint
        # when no document is open (EditorPage owns that rendering).
        self._editor_page = EditorPage(self._tree, self._params, self._inspector)

        # Workspace stack pages. Page indices are fixed by add order (Editor
        # then Validation then Workspace) so _EDITOR_PAGE_INDEX stays valid;
        # the activity bar's add_view order below controls only the VISUAL
        # order of the left-rail entries, which is Workspace, Editor,
        # Validation.
        self._stack = QStackedWidget()
        self._stack.addWidget(self._editor_page)  # _EDITOR_PAGE_INDEX
        self._stack.addWidget(self._validation)  # _VALIDATION_PAGE_INDEX
        self._stack.addWidget(self._workspace)   # _WORKSPACE_PAGE_INDEX

        self._btn_workspace = self._activity_bar.add_view(
            "Workspace", page_index=_WORKSPACE_PAGE_INDEX, icon=icons.activity_icon(icons.WORKSPACE)
        )
        self._btn_editor = self._activity_bar.add_view(
            "Editor", page_index=_EDITOR_PAGE_INDEX, icon=icons.activity_icon(icons.EDITOR)
        )
        self._btn_validation = self._activity_bar.add_view(
            "Validation", page_index=_VALIDATION_PAGE_INDEX, icon=icons.activity_icon(icons.VALIDATION)
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
        self.setStatusBar(bar)

    def _connect(self) -> None:
        # All navigation flows through the single NavigationService: object and
        # parameter clicks, validation issues, the Issues tab and search all
        # request navigation, and the views reveal the resolved target.
        self._navigation.navigated.connect(self._on_navigated)
        self._tree.node_selected.connect(self._navigation.navigate)
        self._params.parameter_selected.connect(self._navigation.navigate)
        self._params.add_parameter_requested.connect(self._on_add_parameter_requested)
        self._params.remove_parameter_requested.connect(self._on_remove_parameter_requested)
        self._validation.issue_activated.connect(self._navigation.navigate)
        self._inspector.issue_activated.connect(self._navigation.navigate)
        self._search.navigation_requested.connect(self._navigation.navigate)
        self._search.dismissed.connect(self._tree.focus_tree)
        self._inspector.committed.connect(self._on_committed)
        self._activity_bar.view_requested.connect(self._on_view_changed)
        self._workspace.open_requested.connect(self._open)
        self._workspace.new_requested.connect(self._new)
        self._workspace.file_dropped.connect(self._on_file_dropped)

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

    def _on_add_parameter_requested(self, section_path: tuple, alias: str) -> None:
        """Add a custom parameter to *section_path* and reveal it.

        Routes through the existing ``AddParameter`` command with an honest
        empty value (``None``); the validator, not the UI, judges whether the
        resulting alias/value is legal. Refresh-then-navigate mirrors
        ``_on_committed``: the document is rebuilt first, then the new
        parameter is revealed through the single ``NavigationService``.
        """
        session = self._state.active
        if session is None or session.document is None:
            return
        session.execute_command(AddParameter(tuple(section_path), alias, None))
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
        at, with no redo to recover it. In that state ``Ctrl+Z`` does nothing --
        exactly as it does in a native spin box. Escape reverts the draft, and
        the toolbar's Undo button remains available for the document.

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
        self._refresh_all()
        self._show_page(_EDITOR_PAGE_INDEX)

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
        if session is None or not session.dirty:
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

    def _open(self) -> None:
        if not self._confirm_discard_if_dirty():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Open BPX", "", "BPX (*.json *.yaml *.yml)")
        if not name:
            return
        self._open_path(name)

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

    def _on_file_dropped(self, path: str) -> None:
        """Open a file dropped onto the Workspace page.

        Goes through the same discard guard as Open before replacing the
        active session.
        """
        if not self._confirm_discard_if_dirty():
            return
        self._open_path(path)

    def _new(self, model: str) -> None:
        """Create a fresh incomplete document scaffold for *model*.

        Goes through the same discard guard as Open before replacing the
        active session, then lands on the Editor page so the user can start
        filling in the new document.
        """
        if not self._confirm_discard_if_dirty():
            return
        self._state.new_document(model)
        self._refresh_all()
        self._show_page(_EDITOR_PAGE_INDEX)

    def _save(self) -> bool:
        """Write the document to its backing file.

        If no backing file is set (unsaved new document), a Save As dialog
        is shown first. Does not affect export copies. Returns True once the
        document has actually been written, False if there was nothing to
        save, the Save As dialog was cancelled, or the write failed -- used
        by :meth:`_confirm_discard_if_dirty` to decide whether it is safe to
        proceed with a destructive action.
        """
        if self._state.active is None:
            return False
        session = self._state.active
        if session.backing_file is None:
            name, _ = QFileDialog.getSaveFileName(
                self, "Save BPX",
                session.document.filename if session.document else "",
                "BPX (*.json *.yaml *.yml)",
            )
            if not name:
                return False
            session.backing_file = Path(name)
        try:
            session.save()
        except OSError as exc:
            QMessageBox.critical(self, "Save failed", str(exc))
            return False
        self._update_title()
        self._update_identity_label()
        self._update_workspace_info()
        return True

    def _export(self) -> None:
        """Write a copy of the document to a user-chosen location.

        Does not affect the backing file or dirty state.
        """
        if self._state.active is None or self._state.active.document is None:
            return
        session = self._state.active
        default = str(session.backing_file) if session.backing_file else session.document.filename
        name, _ = QFileDialog.getSaveFileName(
            self, "Export BPX", default, "BPX (*.json *.yaml *.yml)"
        )
        if not name:
            return
        fmt = "yaml" if name.lower().endswith((".yml", ".yaml")) else "json"
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
        """Compose 'Title \u00b7 Model \u00b7 BPX vX.Y', omitting any empty field."""
        session = self._state.active
        if session is None or session.document is None:
            return _NO_DOCUMENT_TEXT
        identity = session.document.identity
        title = identity.title or self._fallback_filename(session)
        segments = [segment for segment in (title, identity.model) if segment]
        if identity.bpx_version:
            segments.append(f"BPX v{identity.bpx_version}")
        return " \u00b7 ".join(segments) if segments else _NO_DOCUMENT_TEXT

    def _update_identity_label(self) -> None:
        """Sync the top-bar identity label with the active document."""
        self._identity_label.set_full_text(self._compose_identity_text())

    def _update_workspace_info(self) -> None:
        """Sync the Workspace page's info panel with the active session."""
        session = self._state.active
        document = session.document if session else None
        filename = self._fallback_filename(session) if document is not None else None
        dirty = session.dirty if session else False
        self._workspace.refresh(document, filename, dirty)

    def _update_actions_enabled(self) -> None:
        """Save/Export are only enabled once a document is loaded (a session
        alone is not enough: a session may exist with no document yet), and the
        Undo *button* only once that document has something to undo.

        The ``Ctrl+Z`` shortcut stays live regardless: with an empty document
        history it still has a focused text field's typing to undo."""
        session = self._state.active
        has_document = session is not None and session.document is not None
        self._save_action.setEnabled(has_document)
        self._export_action.setEnabled(has_document)
        self._undo_action.setEnabled(has_document and session.can_undo)

    @staticmethod
    def _validation_tooltip(errors: int, warnings: int) -> str:
        """Compose the Validation button's tooltip from honest error/warning
        counts, e.g. 'Validation — 2 errors, 1 warning'. A zero side is
        omitted; singular/plural is handled per side."""
        if not errors and not warnings:
            return "Validation"
        parts = []
        if errors:
            parts.append(f"{errors} error" + ("" if errors == 1 else "s"))
        if warnings:
            parts.append(f"{warnings} warning" + ("" if warnings == 1 else "s"))
        return "Validation — " + ", ".join(parts)

    def _refresh_all(self) -> None:
        document = self._state.active.document if self._state.active else None
        self._editor_page.set_has_document(document is not None)
        if document is not None:
            self._tree.set_root(document.tree)
        self._params.show_node(None)
        self._inspector.reset()
        self._validation.refresh(document)
        self._search.index_document(document)
        errors = document.error_count if document else 0
        warnings = document.warning_count if document else 0
        severity = "error" if errors else ("warning" if warnings else None)
        self._btn_validation.set_badge(errors + warnings, severity)
        self._btn_validation.setToolTip(self._validation_tooltip(errors, warnings))
        self._update_title()
        self._update_identity_label()
        self._update_workspace_info()
        self._update_actions_enabled()
