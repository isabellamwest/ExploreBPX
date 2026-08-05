"""Global navigation search: jump to any object or parameter by name or path.

Search is navigation, not filtering: it never hides tree nodes or parameter
rows. The toolbar search box owns a custom :class:`SearchPopup` (rather than a
``QCompleter``) so results can reach objects as well as parameters, show a name
over its full path, and activate exclusively through the shared
``NavigationService`` on the owning window.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QWidget,
)

from core.document import BPXDocument
from core.tree_model import ParameterItem, TreeNode

from . import icons, parameter_row, style, typography
from .dismissal import OutsideDismissFilter
from .floating_card import SHADOW_MARGIN as _SHADOW_MARGIN
from .floating_card import floating_card
from .parameter_row import ParameterRowDelegate

_PATH_ROLE = Qt.UserRole
_MAX_RESULTS = 50
_MAX_VISIBLE_ROWS = 8


def _entry_html(entry: "_Entry") -> str:
    """A result row's rich-text fragment: a muted monochrome glyph (folder =
    object, sliders = parameter -- the activity bar's outline family, not
    emoji), the bold name, then the muted full path beneath -- the same
    name-over-secondary language the Diagnostics page's rows use, so search
    results read as part of the same system."""
    glyph = icons.html_img(
        icons.SECTION if entry.kind == "object" else icons.PARAMETER
    )
    name = (
        f'<span style="{typography.semibold_qss()} color:{style.DEFAULT_TEXT};">'
        f"{_html.escape(entry.name)}</span>"
    )
    path = (
        f'<span style="color:{style.MUTED}; {typography.size_qss(typography.META)}">'
        f"{_html.escape(entry.path_text)}</span>"
    )
    return f"{glyph}&nbsp;&nbsp;{name}<br>{path}"


@dataclass(frozen=True)
class _Entry:
    """One searchable location: a navigable object or a direct parameter."""

    name: str
    path: tuple[str, ...]
    kind: str  # "object" or "parameter"

    @property
    def path_text(self) -> str:
        return " → ".join(self.path)

    def matches(self, needle: str) -> bool:
        return needle in self.name.lower() or needle in self.path_text.lower()


class SearchPopup(QWidget):
    """A floating, non-activating results card shown under the search box:
    a rounded, shadowed card over a translucent top-level -- the same visual
    treatment as :class:`~ui_qt.add_parameter_popup.AddParameterPopup`, so
    the app's two floating palettes read as one family.

    The popup is display and mouse-selection only; all keyboard handling
    stays in :class:`SearchBar`, which keeps focus while the popup is
    visible. The list's small query surface (``count``/``item``/
    ``currentItem``/``currentRow``/``setCurrentRow`` and the ``itemClicked``
    signal) is forwarded so :class:`SearchBar` and the tests need not know a
    card wrapper exists.
    """

    def __init__(self, parent: QLineEdit) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFocusPolicy(Qt.NoFocus)

        self._list = QListWidget()
        self._list.setObjectName("SearchPopupList")
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setWordWrap(True)
        self._list.setTextElideMode(Qt.ElideNone)
        self._list.setUniformItemSizes(False)
        # Rich rows (glyph + bold name over muted path) via the shared
        # delegate; a plain two-line string stays as each item's .text()
        # fallback.
        self._list.setItemDelegate(ParameterRowDelegate(self._list))
        self.itemClicked = self._list.itemClicked

        _, card_layout = floating_card(self, "SearchPopupCard")
        card_layout.addWidget(self._list)

    # -- forwarded list surface ---------------------------------------
    def count(self) -> int:
        return self._list.count()

    def item(self, row: int) -> QListWidgetItem:
        return self._list.item(row)

    def currentItem(self) -> QListWidgetItem | None:
        return self._list.currentItem()

    def currentRow(self) -> int:
        return self._list.currentRow()

    def setCurrentRow(self, row: int) -> None:
        self._list.setCurrentRow(row)

    # -- content -------------------------------------------------------
    def populate(self, entries: list["_Entry"]) -> None:
        self._list.clear()
        for entry in entries:
            item = QListWidgetItem(f"{entry.name}\n{entry.path_text}")
            item.setData(_PATH_ROLE, entry.path)
            item.setData(parameter_row.HTML_ROLE, _entry_html(entry))
            self._list.addItem(item)
        if self._list.count():
            self._list.setCurrentRow(0)

    def sized_height(self) -> int:
        rows = min(self._list.count(), _MAX_VISIBLE_ROWS)
        if rows == 0:
            return 0
        # Sum the visible rows' own hints: delegate-painted rows wrap, so
        # heights vary and row 0 is not representative of the rest. The
        # card's layout margins and the shadow's transparent margins sit on
        # top of the list's own height.
        list_height = sum(self._list.sizeHintForRow(i) for i in range(rows))
        list_height += 2 * self._list.frameWidth()
        return list_height + 2 * 8 + 2 * _SHADOW_MARGIN


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
                _Entry(node.label, tuple(node.path), "object")
            )
        for parameter in node.parameters:
            self._entries.append(self._parameter_entry(parameter))
        for child in node.children:
            self._collect(child)

    @staticmethod
    def _parameter_entry(parameter: ParameterItem) -> "_Entry":
        return _Entry(parameter.label, tuple(parameter.path), "parameter")

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
        self._popup.setFixedWidth(max(self.width(), 320) + 2 * _SHADOW_MARGIN)
        height = self._popup.sized_height()
        if height:
            self._popup.setFixedHeight(height)
        # Offset by the shadow margin so the visible card -- not its
        # transparent shadow bed -- aligns with the search box's left edge,
        # a small gap below it.
        anchor = self.mapToGlobal(self.rect().bottomLeft())
        self._popup.move(anchor.x() - _SHADOW_MARGIN, anchor.y() - _SHADOW_MARGIN + 4)
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
