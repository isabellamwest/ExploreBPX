"""Global navigation search: jump to any object or parameter by name or path.

Search is navigation, not filtering: it never hides tree nodes or parameter
rows. The toolbar search box owns a custom :class:`SearchPopup` (rather than a
``QCompleter``) so results can reach objects as well as parameters, show a name
over its full path, and activate exclusively through the shared
``NavigationService`` on the owning window.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem

from core.document import BPXDocument
from core.tree_model import ParameterItem, TreeNode

from .dismissal import OutsideDismissFilter

_PATH_ROLE = Qt.UserRole
_MAX_RESULTS = 50
_MAX_VISIBLE_ROWS = 8


@dataclass(frozen=True)
class _Entry:
    """One searchable location: a navigable object or a direct parameter."""

    name: str
    path: tuple[str, ...]
    icon: str
    kind: str  # "object" or "parameter"

    @property
    def path_text(self) -> str:
        return " → ".join(self.path)

    def matches(self, needle: str) -> bool:
        return needle in self.name.lower() or needle in self.path_text.lower()


class SearchPopup(QListWidget):
    """A borderless, non-activating result list shown under the search box.

    The popup is display and mouse-selection only; all keyboard handling stays
    in :class:`SearchBar`, which keeps focus while the popup is visible.
    """

    def __init__(self, parent: QLineEdit) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setFocusPolicy(Qt.NoFocus)
        self.setUniformItemSizes(False)

    def populate(self, entries: list["_Entry"]) -> None:
        self.clear()
        for entry in entries:
            item = QListWidgetItem(f"{entry.icon}  {entry.name}\n{entry.path_text}")
            item.setData(_PATH_ROLE, entry.path)
            self.addItem(item)
        if self.count():
            self.setCurrentRow(0)

    def sized_height(self) -> int:
        rows = min(self.count(), _MAX_VISIBLE_ROWS)
        if rows == 0:
            return 0
        return self.sizeHintForRow(0) * rows + 2 * self.frameWidth()


class SearchBar(QLineEdit):
    """Search box that indexes objects and parameters and jumps on selection."""

    navigation_requested = Signal(tuple)
    dismissed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setPlaceholderText("Search objects and parameters…")
        self.setClearButtonEnabled(True)
        self._entries: list[_Entry] = []
        self._popup = SearchPopup(self)
        self._popup.itemClicked.connect(self._on_item_clicked)
        # The search box itself lives outside the popup's geometry (it's in
        # the top bar, the popup floats below it), so it must be registered
        # as "inside" -- otherwise clicking into it to place the caret would
        # be treated as an outside click and dismiss the popup.
        self._dismiss_filter = OutsideDismissFilter(self._popup, inside=(self,))
        self.textChanged.connect(self._on_text_changed)

    # -- indexing --------------------------------------------------------
    def index_document(self, document: BPXDocument | None) -> None:
        """Rebuild the object+parameter index from *document*."""
        self._entries = []
        self._popup.hide()
        if document is None:
            return
        self._collect(document.tree)

    def _collect(self, node: TreeNode) -> None:
        if node.path:
            self._entries.append(
                _Entry(node.label, tuple(node.path), node.icon, "object")
            )
        for parameter in node.parameters:
            self._entries.append(self._parameter_entry(parameter))
        for child in node.children:
            self._collect(child)

    @staticmethod
    def _parameter_entry(parameter: ParameterItem) -> "_Entry":
        return _Entry(parameter.label, tuple(parameter.path), parameter.icon, "parameter")

    # -- result flow -----------------------------------------------------
    def _on_text_changed(self, text: str) -> None:
        needle = text.strip().lower()
        if not needle:
            self._popup.hide()
            return
        results = [e for e in self._entries if e.matches(needle)][:_MAX_RESULTS]
        if not results:
            self._popup.hide()
            return
        self._popup.populate(results)
        self._show_popup()

    def _show_popup(self) -> None:
        self._popup.move(self.mapToGlobal(self.rect().bottomLeft()))
        self._popup.setFixedWidth(max(self.width(), 320))
        height = self._popup.sized_height()
        if height:
            self._popup.setFixedHeight(height)
        self._popup.show()
        self._dismiss_filter.install()

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        self._activate(item)

    def _activate(self, item: QListWidgetItem | None) -> None:
        if item is None:
            return
        path = item.data(_PATH_ROLE)
        self._popup.hide()
        self.clear()
        if path:
            self.navigation_requested.emit(tuple(path))

    # -- keyboard --------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        key = event.key()
        popup_open = self._popup.isVisible()
        if popup_open and key in (Qt.Key_Down, Qt.Key_Up):
            self._move_selection(1 if key == Qt.Key_Down else -1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            if popup_open:
                self._activate(self._popup.currentItem())
            return
        if key == Qt.Key_Escape:
            self._on_escape(popup_open)
            return
        super().keyPressEvent(event)

    def _move_selection(self, delta: int) -> None:
        count = self._popup.count()
        if not count:
            return
        row = (self._popup.currentRow() + delta) % count
        self._popup.setCurrentRow(row)

    def _on_escape(self, popup_open: bool) -> None:
        """Staged Escape: close popup, then clear text, then leave the search."""
        if popup_open:
            self._popup.hide()
        elif self.text():
            self.clear()
        else:
            self.dismissed.emit()

    # -- lifecycle -------------------------------------------------------
    def focusOutEvent(self, event) -> None:
        self._popup.hide()
        super().focusOutEvent(event)
