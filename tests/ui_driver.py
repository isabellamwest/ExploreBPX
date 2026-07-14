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
        """Activate the first Issues-section row in the document-wide
        Validation view (skipping the "Issues"/"Outstanding" page headers and
        any Outstanding rows -- Phase 5 restructured the page into two
        always-present sections sharing one QListWidget).

        Emits ``itemActivated`` -- the signal the panel actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the panel does
        not listen to.
        """
        items = self._validation_rows("issue")
        assert items, "No issue row in the Validation list."
        self._w._validation._list.itemActivated.emit(items[0])
        return self

    def activate_validation_row(self, item) -> "AppDriver":
        """Emit ``itemActivated`` for one already-located ``QListWidgetItem``
        (e.g. from :meth:`validation_rows`) -- the low-level primitive
        :meth:`activate_first_validation_issue`/:meth:`activate_outstanding_task`
        build on."""
        self._w._validation._list.itemActivated.emit(item)
        return self

    def activate_outstanding_task(self, task) -> "AppDriver":
        """Activate the Outstanding row for *task* (a ``CompletionTask``, as
        returned by :meth:`outstanding_tasks`)."""
        from ui_qt import validation_panel as vp

        for item in self._validation_rows("task"):
            if item.data(vp._TASK_ROLE) == task:
                self._w._validation._list.itemActivated.emit(item)
                return self
        raise AssertionError(f"No Outstanding row for {task!r}")

    def outstanding_tasks(self) -> list:
        """Every ``CompletionTask`` currently rendered as an Outstanding row,
        in on-screen order."""
        from ui_qt import validation_panel as vp

        return [item.data(vp._TASK_ROLE) for item in self._validation_rows("task")]

    def outstanding_task_row_text(self, task) -> str:
        """Plain text of the Outstanding row for *task* -- includes any
        absorbed validator messages appended as secondary text (decision O)."""
        from ui_qt import validation_panel as vp

        for item in self._validation_rows("task"):
            if item.data(vp._TASK_ROLE) == task:
                return item.text()
        raise AssertionError(f"No Outstanding row for {task!r}")

    def validation_group_headers(self) -> list[str]:
        """Text of every Outstanding group subheader, in order (e.g.
        "Cell — 2 of 5 remaining", "Separator — section absent")."""
        return [item.text() for item in self._validation_rows("group_header")]

    def validation_task_row_count_under_header(self, header_text: str) -> int:
        """Number of "task" rows directly beneath the group/page header whose
        text is *header_text*, up to (not including) the next header row
        (decision R's ratio-integrity check: a required group's stated N must
        equal this count exactly, never an optional row sitting in between)."""
        from ui_qt import validation_panel as vp

        lst = self._w._validation._list
        start = None
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(vp._KIND_ROLE) in ("group_header", "page_header") and item.text() == header_text:
                start = i
                break
        assert start is not None, f"No header row with text {header_text!r}."
        count = 0
        for i in range(start + 1, lst.count()):
            item = lst.item(i)
            kind = item.data(vp._KIND_ROLE)
            if kind in ("group_header", "page_header"):
                break
            if kind == "task":
                count += 1
        return count

    def validation_page_headers(self) -> list[str]:
        """Text of the two always-present page-section headers ("Issues",
        "Outstanding")."""
        return [item.text() for item in self._validation_rows("page_header")]

    def validation_issue_texts(self) -> list[str]:
        """Text of every Issues-section row, in order."""
        return [item.text() for item in self._validation_rows("issue")]

    def activate_validation_group_header(self, index: int = 0) -> "AppDriver":
        """Activate a group subheader row directly -- proves it is a
        structural no-op (decision L: only issue/task rows act)."""
        return self.activate_validation_row(self._validation_rows("group_header")[index])

    def activate_validation_page_header(self, index: int = 0) -> "AppDriver":
        """Activate a page-section header row directly ("Issues"/
        "Outstanding") -- proves it is a structural no-op."""
        return self.activate_validation_row(self._validation_rows("page_header")[index])

    def fields_to_add_current_alias(self) -> str | None:
        """The alias of the parameter list's currently-selected "fields to
        add" suggestion row, or None if the current row isn't one (used to
        assert a MISSING_FIELD Outstanding activation landed on the right
        synthetic row via ``reveal_missing_alias``)."""
        panel = self._w._params
        item = panel._list.currentItem()
        if item is None or item.data(panel._GROUP_ROW_KIND_ROLE) != "suggestion":
            return None
        return item.data(panel._GROUP_ROW_ALIAS_ROLE)

    def validation_issues_empty_text(self) -> str | None:
        """Text of the Issues section's own inline empty-state row (e.g.
        "✓ No issues"), or None if the section holds real issue rows."""
        return self._section_message_text("Issues")

    def validation_outstanding_empty_text(self) -> str | None:
        """Text of the Outstanding section's own inline empty-state row
        (e.g. "✓ Nothing outstanding", or the Partial-model notice), or None
        if the section holds real task rows."""
        return self._section_message_text("Outstanding")

    def _section_message_text(self, page_header_text: str) -> str | None:
        from ui_qt import validation_panel as vp

        lst = self._w._validation._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(vp._KIND_ROLE) == "page_header" and item.text() == page_header_text:
                nxt = lst.item(i + 1)
                if nxt is not None and nxt.data(vp._KIND_ROLE) == "message":
                    return nxt.text()
                return None
        return None

    def _validation_rows(self, kind: str) -> list:
        from ui_qt import validation_panel as vp

        lst = self._w._validation._list
        return [
            lst.item(i)
            for i in range(lst.count())
            if lst.item(i).data(vp._KIND_ROLE) == kind
        ]

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

    def fields_to_add_header_text(self) -> str | None:
        """Text of the parameter list's "fields to add" group header row
        (e.g. "▸ 2 fields to add"), or None if the group isn't shown at all
        (no missing fields, or the model doesn't qualify -- decision C)."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "header":
                return item.text()
        return None

    def toggle_fields_to_add_group(self) -> "AppDriver":
        """Click the "fields to add" group's header row."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "header":
                lst.itemClicked.emit(item)
                return self
        raise AssertionError("No fields-to-add group header is currently shown.")

    def fields_to_add_suggestion_aliases(self) -> list[str]:
        """The aliases currently listed under the (expanded) "fields to add"
        group, in list order."""
        panel = self._w._params
        lst = panel._list
        return [
            lst.item(i).data(panel._GROUP_ROW_ALIAS_ROLE)
            for i in range(lst.count())
            if lst.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
        ]

    def click_fields_to_add_suggestion(self, alias: str) -> "AppDriver":
        """Click one "fields to add" suggestion row -- the same
        ``add_parameter_requested`` path the add-parameter popup's own
        Suggested rows use."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if (
                item.data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
                and item.data(panel._GROUP_ROW_ALIAS_ROLE) == alias
            ):
                lst.itemClicked.emit(item)
                return self
        raise AssertionError(f"No fields-to-add suggestion row for {alias!r}.")

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

    def redo(self) -> "AppDriver":
        """Click the toolbar's Redo button: a document command.

        Mirrors ``undo()`` -- see its docstring for why a disabled action and
        an open popup are handled the way they are.
        """
        self._w._redo_action.trigger()
        return self

    def press_redo_shortcut(self) -> "AppDriver":
        """Press ``Ctrl+Y``: focus-aware redo (see ``MainWindow._redo``).

        Emits the real ``QShortcut``'s ``activated`` signal -- see
        ``press_undo_shortcut`` for why a synthesised key press would not do.
        """
        self._w._redo_shortcut.activated.emit()
        return self

    def press_redo_shortcut_alt(self) -> "AppDriver":
        """Press ``Ctrl+Shift+Z``: the alternate focus-aware redo shortcut."""
        self._w._redo_shortcut_alt.activated.emit()
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

    def redo_enabled(self) -> bool:
        return self._w._redo_action.isEnabled()

    def redo_shortcut(self) -> str:
        return self._w._redo_shortcut.key().toString()

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

    def parameter_row_is_grey(self, label: str) -> bool:
        """True when the real parameter row starting with *label*'s rich-text
        (decision P: a committed-null value renders grey/muted) colours its
        *name* span (the first, bold one) with the muted colour rather than
        the normal one. Checking only the leading span matters: the unit
        suffix is always muted regardless (``build_parameter_row_html``), so
        a naive "is MUTED anywhere in the html" check is always true for any
        row with a unit. Real rows only -- matched by role-256 path presence.
        """
        from ui_qt import parameter_row, style

        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                html = item.data(parameter_row.HTML_ROLE)
                assert html is not None, f"Row {label!r} carries no rich-text data."
                name_span_prefix = f'<span style="font-weight:600; color:{style.MUTED};">'
                return html.startswith(name_span_prefix)
        raise AssertionError(f"No real parameter row starting with {label!r}.")

    def parameter_row_has_warning_marker(self, label: str) -> bool:
        """True when the real parameter row starting with *label* shows the
        ⚠ marker (decision P: page-visible issues only, not validator-
        verbatim)."""
        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                return "⚠" in item.text()
        raise AssertionError(f"No real parameter row starting with {label!r}.")

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

    def issues_tab_badge_count(self) -> int:
        """The secondary Issues tab's badge NUMBER, parsed from its button
        text (e.g. 'Issues (1)' -> 1; 'Issues' with no suffix -> 0).

        Deliberately distinct from :meth:`issues_tab_count` (which reads the
        tab's own row *list*) -- the two are set by different code paths
        (``SecondaryWorkspace.set_count`` vs ``IssuesTab.show_parameter``'s
        row-building) and must always agree. M1 (reviewed defect): two
        Inspector call-sites (``_validate_draft``, ``_on_reset``) used to push
        the *unmerged* diagnostic count into this badge while the list stayed
        merged, so this reader exists specifically to catch that class of bug
        -- a test using only ``issues_tab_count()`` cannot see it.
        """
        text = self._w._inspector._secondary._buttons["issues"].text()
        if "(" not in text:
            return 0
        return int(text.rsplit("(", 1)[1].rstrip(")"))

    def issues_tab_count(self) -> int:
        return self._w._inspector._issues_tab._list.count()

    def issues_tab_texts(self) -> list[str]:
        """Text of every row currently listed in the Issues tab (decision Q:
        a null/bad FloatInt value's float_type+int_type pair displays merged
        to one row here)."""
        lst = self._w._inspector._issues_tab._list
        return [lst.item(i).text() for i in range(lst.count())]

    def issues_tab_message(self) -> str | None:
        """Visible placeholder text when the Issues tab shows one, else None."""
        tab = self._w._inspector._issues_tab
        if tab._stack.currentWidget() is tab._placeholder:
            return tab._placeholder.text()
        return None

    def secondary_expanded(self) -> bool:
        return self._w._inspector._secondary.is_expanded

    def validation_issue_count(self) -> int:
        """Count of Issues-section rows only (the page also always renders
        two section headers plus the Outstanding section -- Phase 5)."""
        return len(self._validation_rows("issue"))

    def validation_outstanding_count(self) -> int:
        """Count of Outstanding-section task rows only."""
        return len(self._validation_rows("task"))

    def validation_message(self) -> str | None:
        """Visible full-page placeholder text ("No document open"), or None
        once a document is open -- the page then always shows its list (the
        two sections carry their own inline empty-state rows instead)."""
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
        """Text of the Workspace page's current-document card, flattened.

        Composed from the card's title, validity badge and field rows into the
        ``Key: value`` lines the workspace assertions read, so a layout change
        (single label -> formatted card) does not ripple into every test.
        """
        ws = self._w._workspace
        title = ws._info_title.text()
        if title == "No document open":
            return title
        lines = [f"Title: {title}"]
        if ws._info_badge.text():
            lines.append(f"Validity: {ws._info_badge.text()}")
        for key in ("Model", "BPX version", "File", "State", "Contents"):
            lines.append(f"{key}: {ws._info_fields[key].text()}")
        return "\n".join(lines)

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
    # Grid cards (SeriesCard, and later interpolated tables)
    # ------------------------------------------------------------------

    def grid_values(self) -> list[list[object]]:
        """Every row of the active card's grid, as raw cell objects."""
        return self._grid().values()

    def set_grid_cell(self, row: int, column: int, text) -> "AppDriver":
        """Type *text* into one grid cell (what the cell delegate commits).

        Drives the model's ``setData`` -- the same entry point the cell editor
        uses on confirm -- so the lenient parse and no-coercion contract are
        exercised without opening a per-cell editor widget.
        """
        from PySide6.QtCore import Qt

        grid = self._grid()
        grid._model.setData(grid._model.index(row, column), str(text), Qt.EditRole)
        return self

    def add_grid_row(self) -> "AppDriver":
        self._grid().insert_row()
        return self

    def remove_grid_row(self, row: int | None = None) -> "AppDriver":
        grid = self._grid()
        if row is not None:
            grid._view.setCurrentIndex(grid._model.index(row, 0))
        grid.remove_row()
        return self

    def open_grid_cell_editor(self, row: int, column: int) -> "AppDriver":
        """Open the real per-cell editor widget for one grid cell.

        Types a digit into the cell -- the ``AnyKeyPressed`` trigger -- so the
        delegate opens its ``QLineEdit``, exactly as a user editing a cell does.
        The window is shown first: an item delegate opens and commits its editor
        against a live view, and in an unshown window it never leaves the edit
        state. Use with :meth:`press_in_cell_editor` to exercise the cell-level
        (vs grid-level) Enter/Escape layer.
        """
        from PySide6.QtCore import Qt

        grid = self._grid()
        view = grid.focus_widget()
        self._w.show()
        view.setFocus()
        view.setCurrentIndex(grid._model.index(row, column))
        self._qtbot.keyClick(view, Qt.Key_1)
        return self

    def grid_cell_editor_open(self) -> bool:
        from PySide6.QtWidgets import QAbstractItemView

        return self._grid().focus_widget().state() == QAbstractItemView.State.EditingState

    def press_in_cell_editor(self, key) -> "AppDriver":
        """Send a key to the open cell editor widget (not the grid).

        Waits for Qt to deliver the delegate's commit/close after the key, so
        the caller observes the settled state rather than a mid-transition one.
        """
        from PySide6.QtWidgets import QLineEdit

        editor = self._grid().focus_widget().findChild(QLineEdit)
        assert editor is not None, "No cell editor is open."
        self._qtbot.keyClick(editor, key)
        self._qtbot.wait(10)
        return self

    def commit_grid(self) -> "AppDriver":
        """Press Enter on the grid itself to commit the draft to the document."""
        from PySide6.QtCore import Qt

        self._qtbot.keyClick(self._grid().focus_widget(), Qt.Key_Return)
        return self

    def revert_grid(self) -> "AppDriver":
        """Press Escape on the grid itself to discard the draft."""
        from PySide6.QtCore import Qt

        self._qtbot.keyClick(self._grid().focus_widget(), Qt.Key_Escape)
        return self

    def _grid(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        grid = getattr(editor, "_grid", None)
        if grid is None:
            # A ModalCard's grid lives inside its active table body.
            body = getattr(editor, "_body", None)
            grid = getattr(body, "_grid", None)
        assert grid is not None, f"Card {type(editor).__name__} has no grid."
        return grid

    # ------------------------------------------------------------------
    # Modal cards (mode strip)
    # ------------------------------------------------------------------

    def mode_labels(self) -> tuple[str, ...]:
        """The strip's mode names, in verbatim bpx.schema vocabulary."""
        return self._modal().mode_labels

    def current_mode(self) -> str:
        return self._modal().current_mode

    def select_mode(self, label: str) -> "AppDriver":
        """Click a mode button on the strip."""
        modal = self._modal()
        index = list(modal.mode_labels).index(label)
        self._qtbot.mouseClick(modal._strip._buttons[index], Qt.LeftButton)
        return self

    def mode_strip_visible(self) -> bool:
        """False for a kind with a single representation (no strip is built)."""
        return self._modal()._strip is not None

    def commit_blocked_reason(self) -> str | None:
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        return card.commit_blocked_reason()

    def set_raw_json(self, text: str) -> "AppDriver":
        """Replace the Raw mode body's JSON text wholesale."""
        modal = self._modal()
        assert modal.current_mode == "Raw", f"Not in Raw mode ({modal.current_mode})."
        modal._body._edit.setPlainText(text)
        return self

    def _modal(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        assert hasattr(editor, "mode_labels"), (
            f"Card {type(editor).__name__} is not a ModalCard."
        )
        return editor

    # ------------------------------------------------------------------
    # Internals -- the one place that knows card widget structure
    # ------------------------------------------------------------------

    def _editor_widget(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        # A ModalCard has no single input widget: it delegates to whichever
        # mode body is showing.
        focus_widget = getattr(editor, "focus_widget", None)
        if callable(focus_widget):
            return focus_widget()
        for attr in ("_edit", "_fallback", "_spin", "_combo"):
            widget = getattr(editor, attr, None)
            if widget is not None:
                return widget
        raise AssertionError(f"Card {type(editor).__name__} exposes no editor widget.")
