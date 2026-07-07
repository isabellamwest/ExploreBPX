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

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLineEdit, QSpinBox


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
        """Switch the workspace via the activity bar ("Editor"/"Validation")."""
        index = {"Editor": 0, "Validation": 1}[name]
        self._w._activity_bar.view_requested.emit(index)
        return self

    # ------------------------------------------------------------------
    # Readers -- user-visible state only
    # ------------------------------------------------------------------

    def has_document(self) -> bool:
        return self._w.windowTitle() != "ExploreBPX"

    def window_title(self) -> str:
        return self._w.windowTitle()

    def status_text(self) -> str:
        return self._w._status_label.text()

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

    def current_view_index(self) -> int:
        return self._w._stack.currentIndex()

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
