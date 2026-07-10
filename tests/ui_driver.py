"""Test-side UI driver: the single home for "how to drive the app" knowledge.

The workflow tests describe *what the user does and sees* in domain terms
(open a file, go to a parameter, edit the field, commit, read the validity
badge). This driver translates those intentions into concrete widget
interactions.

Design rules:
  - Tests never touch widgets directly; they only call driver methods.
  - The driver drives through the outermost surface available: the public
    ``MainWindow`` operations (``open_document``, ``navigate_to``), the panels'
    public signals, and real Qt events via ``qtbot``. Where it must reach a
    concrete widget (to type into the active card or read a visible label),
    that knowledge is confined to this file.
  - Readers return *user-visible* state (badge text, tab labels, list counts,
    window title) so assertions survive internal refactors.

If a UI refactor moves a widget or renames an attribute, only this driver
changes -- the workflow tests keep expressing the same behaviour.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QSpinBox


class AppDriver:
    """Drives a live :class:`MainWindow` the way a user would."""

    def __init__(self, window, qtbot) -> None:
        self._w = window
        self._qtbot = qtbot

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def open(self, path: Path | str) -> "AppDriver":
        """Open a document by path (equivalent to File > Open)."""
        self._w.open_document(Path(path))
        return self

    def select_object(self, path: tuple[str, ...]) -> "AppDriver":
        """Click an object node in the structure tree."""
        self._w._tree.node_selected.emit(tuple(path))
        return self

    def select_parameter(self, path: tuple[str, ...]) -> "AppDriver":
        """Click a parameter in the parameter list."""
        self._w._params.parameter_selected.emit(tuple(path))
        return self

    def go_to(self, path: tuple[str, ...]) -> "AppDriver":
        """Navigate straight to a parameter (owning object + parameter)."""
        self._w.navigate_to(tuple(path))
        return self

    def edit_field(self, value) -> "AppDriver":
        """Type/set *value* into the active card's editor."""
        widget = self._editor_widget()
        if isinstance(widget, QLineEdit):
            widget.clear()
            self._qtbot.keyClicks(widget, str(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QComboBox):
            index = widget.findText(str(value))
            if index >= 0:
                widget.setCurrentIndex(index)
            else:
                widget.setEditText(str(value))
        else:  # pragma: no cover - defensive
            raise AssertionError(f"No editable widget for the active card: {widget!r}")
        return self

    def commit(self) -> "AppDriver":
        """Press Enter to commit the current draft to the document."""
        self._qtbot.keyClick(self._editor_widget(), Qt.Key_Return)
        return self

    def escape(self) -> "AppDriver":
        """Press Escape to discard the current draft."""
        self._qtbot.keyClick(self._editor_widget(), Qt.Key_Escape)
        return self

    def wait_for_live_validation(self) -> "AppDriver":
        """Wait for the Inspector's debounce so live validation can settle."""
        self._qtbot.wait(260)  # slightly longer than the 200ms debounce
        return self

    def click_issues_tab(self) -> "AppDriver":
        """Click the Issues tab button in the secondary workspace."""
        button = self._w._inspector._secondary._buttons["issues"]
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def activate_first_validation_issue(self) -> "AppDriver":
        """Activate the first issue in the document-wide Validation view.

        Emits ``itemActivated`` -- the signal the panel actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the panel does
        not listen to.
        """
        lst = self._w._validation._list
        lst.itemActivated.emit(lst.item(0))
        return self

    def activate_validation_issue(self, path: tuple[str, ...]) -> "AppDriver":
        """Emit the Validation view's own activation signal for *path*.

        Drives through the panel's public ``issue_activated`` signal directly
        (the same entry point a real double-click or Enter/Return uses
        internally), bypassing ``QListWidget``'s ``itemDoubleClicked`` --
        which is a distinct Qt signal from ``itemActivated`` and, unlike a
        genuine mouse event, does not trigger it when emitted manually.
        """
        self._w._validation.issue_activated.emit(tuple(path))
        return self

    def activate_first_parameter_issue(self) -> "AppDriver":
        """Activate the first issue in the Inspector's Issues tab.

        Emits ``itemActivated`` -- the signal the tab actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the tab does
        not listen to.
        """
        lst = self._w._inspector._issues_tab._list
        lst.itemActivated.emit(lst.item(0))
        return self

    def choose_search_result(self, path: tuple[str, ...]) -> "AppDriver":
        """Type a query, then pick the matching result from the SearchPopup."""
        from PySide6.QtCore import Qt

        search = self._w._search
        search.setFocus()
        search.clear()
        self._qtbot.keyClicks(search, path[-1])
        popup = search._popup
        for row in range(popup.count()):
            if popup.item(row).data(Qt.UserRole) == tuple(path):
                popup.setCurrentRow(row)
                popup.itemClicked.emit(popup.item(row))
                return self
        raise AssertionError(f"No search result for {path!r}")

    def show_view(self, name: str) -> "AppDriver":
        """Switch the workspace via the activity bar ("Workspace"/"Editor"/"Validation")."""
        index = {"Editor": 0, "Validation": 1, "Workspace": 2}[name]
        self._w._activity_bar.view_requested.emit(index)
        return self

    def click_workspace_open(self) -> "AppDriver":
        """Click the Open File button on the Workspace page."""
        self._qtbot.mouseClick(self._w._workspace._open_button, Qt.LeftButton)
        return self

    def drop_file_on_workspace(self, path: Path | str) -> "AppDriver":
        """Simulate the user dropping *path* onto the Workspace page.

        Dispatches a real ``QDropEvent`` straight to the panel, exercising
        its own extension filtering as well as MainWindow's discard-guard
        and open/error-handling wiring -- the same as a genuine OS-level
        drop. If *path* is not a supported BPX file, the panel ignores the
        event and nothing happens.
        """
        panel = self._w._workspace
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        panel.dropEvent(event)
        return self

    def open_add_parameter_popup(self) -> "AppDriver":
        """Click the Parameter list's "+ Add parameter" header button."""
        self._qtbot.mouseClick(self._w._params._add_button, Qt.LeftButton)
        return self

    def type_new_parameter_alias(self, text: str) -> "AppDriver":
        """Type *text* into the add-parameter popup's input."""
        popup = self._w._params._popup
        popup._input.clear()
        self._qtbot.keyClicks(popup._input, text)
        return self

    def activate_selected_add_parameter_row(self) -> "AppDriver":
        """Activate whichever row is currently highlighted in the
        add-parameter popup -- a BPX-alias suggestion or the "Create custom
        parameter" fallback, whichever the popup currently has selected."""
        self._w._params._popup._activate()
        return self

    def right_click_parameter_row(self, index: int) -> "AppDriver":
        """Right-click the parameter row at *index*: select it and open its
        context menu.

        Emits the list's own ``customContextMenuRequested`` at the row's
        on-screen position -- the same entry point a real right-click
        delivers. ``QMenu.exec()`` is a genuinely blocking native call (a
        Python-level monkeypatch of it does not intercept the underlying
        C++ modal loop), so a zero-delay timer closes the menu the instant
        its event loop starts, letting ``exec()`` return immediately -- the
        standard Qt-test idiom for driving a blocking popup without a real
        user dismissing it.
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        def _close_open_popup() -> None:
            popup = QApplication.instance().activePopupWidget()
            if popup is not None:
                popup.close()

        panel = self._w._params
        item = panel._list.item(index)
        assert item is not None, f"No parameter row at index {index}"
        pos = panel._list.visualItemRect(item).center()
        QTimer.singleShot(0, _close_open_popup)
        panel._list.customContextMenuRequested.emit(pos)
        return self

    def activate_remove_parameter_action(self) -> "AppDriver":
        """Activate the parameter list's "Remove parameter" context-menu
        action -- the equivalent of clicking it while the menu is showing."""
        self._w._params._remove_action.trigger()
        return self

    def press_delete_in_parameter_list(self) -> "AppDriver":
        """Press the Delete key with the parameter list focused -- the
        row-removal accelerator."""
        self._qtbot.keyClick(self._w._params._list, Qt.Key_Delete)
        return self

    def undo(self) -> "AppDriver":
        """Click the toolbar's Undo button: a document command.

        ``QAction.trigger()`` is ignored by a disabled action exactly as a
        click on it would be, so this faithfully reproduces "Undo is currently
        unavailable" too. It does bypass one thing a real mouse click meets
        first: an open popup's ``OutsideDismissFilter`` swallows the click that
        dismisses it, so in the running app a click with the search popup open
        closes the popup and a second click reaches Undo. That is the app's
        dismissal convention (shared by Save and Export), tested in
        ``test_dismissal.py``, and orthogonal to what Undo does.
        """
        self._w._undo_action.trigger()
        return self

    def press_undo_shortcut(self) -> "AppDriver":
        """Press ``Ctrl+Z``: focus-aware undo (see ``MainWindow._undo``).

        Emits the real ``QShortcut``'s ``activated`` signal rather than a
        ``Ctrl+Z`` key event, because ``QTest`` delivers key events straight to
        the target widget and never consults the window's shortcut map -- so a
        synthesised key press would silently exercise nothing.
        """
        self._w._undo_shortcut.activated.emit()
        return self

    def focus_search(self) -> "AppDriver":
        """Give the top-bar search box keyboard focus within the window."""
        self._focus(self._w._search)
        return self

    def type_in_search(self, text: str) -> "AppDriver":
        self._qtbot.keyClicks(self._w._search, str(text))
        return self

    def search_text(self) -> str:
        return self._w._search.text()

    def _focus(self, widget) -> None:
        """Give *widget* keyboard focus within the window.

        The window must be shown first: ``setFocus`` on a hidden widget only
        propagates as far as its first non-hidden ancestor, so a toolbar widget
        in an unshown window never becomes the window's focus widget. That is
        real Qt behaviour, not a test artefact -- a hidden widget cannot hold
        the keyboard.
        """
        self._w.show()
        widget.setFocus()
        assert self._w.focusWidget() is widget, f"{widget!r} did not take focus"

    def focus_field(self) -> "AppDriver":
        """Give the active card's editor keyboard focus within the window."""
        self._focus(self._editor_widget())
        return self

    def type_in_field(self, text: str) -> "AppDriver":
        """Type into the active card's editor without clearing it first, so the
        widget accumulates its own undo history."""
        self._qtbot.keyClicks(self._editor_widget(), str(text))
        return self

    def field_text(self) -> str:
        """The raw text currently shown in the active card's editor."""
        widget = self._editor_widget()
        assert isinstance(widget, QLineEdit), f"{type(widget).__name__} has no text()"
        return widget.text()

    def click_workspace_new(self, model: str) -> "AppDriver":
        """Click the New button for *model* on the Workspace page's inline chooser."""
        button = self._w._workspace.findChild(QPushButton, f"NewButton_{model}")
        assert button is not None, f"No New button for model {model!r}"
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def workspace_new_model_options(self) -> list[str]:
        """The model names currently offered as buttons by the inline New chooser."""
        prefix = "NewButton_"
        return [
            button.objectName()[len(prefix):]
            for button in self._w._workspace.findChildren(QPushButton)
            if button.objectName().startswith(prefix)
        ]

    # ------------------------------------------------------------------
    # Readers -- user-visible state only
    # ------------------------------------------------------------------

    def has_document(self) -> bool:
        return self._w.windowTitle() != "ExploreBPX"

    def window_title(self) -> str:
        return self._w.windowTitle()

    def status_text(self) -> str:
        return self._w._status_label.text()

    def identity_text(self) -> str:
        """Full (untruncated) top-bar identity string.

        Reads the label's tooltip rather than its rendered ``text()``: the
        label elides its visible text to the widget's current width, which is
        unreliable off-screen, but the tooltip always holds the full string.
        """
        return self._w._identity_label.toolTip()

    def save_enabled(self) -> bool:
        return self._w._save_action.isEnabled()

    def export_enabled(self) -> bool:
        return self._w._export_action.isEnabled()

    def undo_enabled(self) -> bool:
        return self._w._undo_action.isEnabled()

    def undo_shortcut(self) -> str:
        return self._w._undo_shortcut.key().toString()

    def inspector_title(self) -> str:
        return self._w._inspector._card._title.text()

    def validity(self) -> str:
        """The Inspector validity badge: '', 'Valid', 'Warning' or 'Invalid'."""
        return self._w._inspector._card._badge.text()

    def field_value(self):
        return self._w._inspector._card.value()

    def card_is_editable(self) -> bool:
        card = self._w._inspector._card
        return card is not None and card.is_editable

    def card_is_dirty(self) -> bool:
        """True when the active card holds an uncommitted draft."""
        card = self._w._inspector._card
        return card is not None and card.is_dirty

    def shown_parameter_path(self) -> tuple[str, ...] | None:
        """Path of the parameter the Inspector is currently showing."""
        card = self._w._inspector._card
        return tuple(card.parameter.path) if card is not None else None

    def showing_placeholder(self) -> bool:
        """True when the Inspector shows its 'select an object' placeholder."""
        return self._w._inspector._card is None

    def parameter_labels(self) -> list[str]:
        lst = self._w._params._list
        return [lst.item(i).text() for i in range(lst.count())]

    def add_parameter_button_enabled(self) -> bool:
        return self._w._params._add_button.isEnabled()

    def add_parameter_row_count(self) -> int:
        """Number of rows currently shown in the add-parameter popup's list,
        including group headers. The custom-add fallback is a pinned footer,
        not a list row -- see :meth:`add_parameter_can_create_custom`."""
        return self._w._params._popup._list.count()

    def add_parameter_can_create_custom(self) -> bool:
        """True when the popup's pinned "Create custom parameter" footer is
        offered for the currently typed text."""
        return self._w._params._popup._footer_shown

    def add_parameter_alias_texts(self) -> list[str]:
        """The visible text of every real (non-header) parameter row currently
        listed in the add-parameter popup."""
        popup = self._w._params._popup
        lst = popup._list
        return [
            lst.item(i).text()
            for i in range(lst.count())
            if lst.item(i).data(popup._TIER_ROLE) != "header"
        ]

    def editor_kind(self) -> str:
        """Class name of the active card's per-kind editor (e.g.
        'ScalarCard', 'RawCard'), so tests can assert a known BPX alias opens
        its proper metadata-driven editor rather than the raw fallback."""
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        return type(card._editor).__name__

    def issues_tab_label(self) -> str:
        return self._w._inspector._secondary._buttons["issues"].text()

    def issues_tab_count(self) -> int:
        return self._w._inspector._issues_tab._list.count()

    def issues_tab_message(self) -> str | None:
        """Visible placeholder text when the Issues tab shows one, else None."""
        tab = self._w._inspector._issues_tab
        if tab._stack.currentWidget() is tab._placeholder:
            return tab._placeholder.text()
        return None

    def secondary_expanded(self) -> bool:
        return self._w._inspector._secondary.is_expanded

    def validation_issue_count(self) -> int:
        return self._w._validation._list.count()

    def validation_message(self) -> str | None:
        """Visible placeholder text on the Validation page, else None when
        the issue list itself is showing."""
        panel = self._w._validation
        if panel._stack.currentWidget() is panel._placeholder:
            return panel._placeholder.text()
        return None

    def editor_showing_empty_state(self) -> bool:
        """True when the Editor page shows its no-document hint rather than
        the tree/params/inspector splitter."""
        page = self._w._editor_page
        return page._stack.currentWidget() is page._placeholder

    def editor_empty_state_text(self) -> str:
        return self._w._editor_page._placeholder.text()

    def current_view_index(self) -> int:
        return self._w._stack.currentIndex()

    def validation_badge_count(self) -> int:
        """The Validation activity-bar entry's badge count (0 = no badge)."""
        return self._w._btn_validation.badge_count

    def validation_badge_severity(self) -> str | None:
        """The Validation entry's badge severity: 'error', 'warning' or None."""
        return self._w._btn_validation.badge_severity

    def validation_tooltip(self) -> str:
        """The Validation activity-bar entry's tooltip text."""
        return self._w._btn_validation.toolTip()

    def page_header_title(self) -> str:
        """The page header's current (raw, non-upper-cased) title."""
        return self._w._page_header.title()

    def activity_bar_selected_label(self) -> str | None:
        """Accessible name of whichever activity bar button is checked."""
        for btn in self._w._activity_bar._buttons:
            if btn.isChecked():
                return btn.accessibleName()
        return None

    def workspace_info_text(self) -> str:
        """Text shown in the Workspace page's current-document info panel."""
        return self._w._workspace._info.text()

    def tree_selection_label(self) -> str | None:
        """Label of the node currently selected in the structure tree, if any."""
        index = self._w._tree._view.currentIndex()
        if not index.isValid():
            return None
        return index.internalPointer().label

    def tree_path_is_expanded(self, path: tuple[str, ...]) -> bool:
        """True when the tree node at *path* is expanded."""
        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        return index.isValid() and view.isExpanded(index)

    # ------------------------------------------------------------------
    # Internals -- the one place that knows card widget structure
    # ------------------------------------------------------------------

    def _editor_widget(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        for attr in ("_edit", "_fallback", "_spin", "_combo"):
            widget = getattr(editor, attr, None)
            if widget is not None:
                return widget
        raise AssertionError(f"Card {type(editor).__name__} exposes no editor widget.")
