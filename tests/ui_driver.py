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
        """Double-click the first issue in the document-wide Validation view."""
        lst = self._w._validation._list
        lst.itemDoubleClicked.emit(lst.item(0))
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
        """Double-click the first issue in the Inspector's Issues tab."""
        lst = self._w._inspector._issues_tab._list
        lst.itemDoubleClicked.emit(lst.item(0))
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

    def inspector_title(self) -> str:
        return self._w._inspector._title.text()

    def validity(self) -> str:
        """The Inspector validity badge: '', 'Valid', 'Warning' or 'Invalid'."""
        return self._w._inspector._badge.text()

    def field_value(self):
        return self._w._inspector._card.value()

    def card_is_editable(self) -> bool:
        card = self._w._inspector._card
        return card is not None and card.is_editable

    def showing_placeholder(self) -> bool:
        """True when the Inspector shows its 'select an object' placeholder."""
        return self._w._inspector._card is None

    def parameter_labels(self) -> list[str]:
        lst = self._w._params._list
        return [lst.item(i).text() for i in range(lst.count())]

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

    def validation_badge_text(self) -> str:
        """Text of the activity bar's Validation entry (e.g. 'Validation' or
        'Validation (2)')."""
        return self._w._btn_validation.text()

    def activity_bar_selected_label(self) -> str | None:
        """Text of whichever activity bar button is currently checked."""
        buttons = (
            ("Workspace", self._w._btn_workspace),
            ("Editor", self._w._btn_editor),
            ("Validation", self._w._btn_validation),
        )
        for label, btn in buttons:
            if btn.isChecked():
                return label
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
        for attr in ("_edit", "_fallback", "_spin", "_combo"):
            widget = getattr(card, attr, None)
            if widget is not None:
                return widget
        raise AssertionError(f"Card {type(card).__name__} exposes no editor widget.")
