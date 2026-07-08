"""Add-parameter popup: the custom-add surface for the parameter-list header.

Anchored under the Parameter-list pane's "+ Add parameter" button, following
the frameless ``Qt.FramelessWindowHint | Qt.Tool`` pattern established by
:class:`~ui_qt.search.SearchPopup` and
:class:`~ui_qt.parameter_info_popover.ParameterInfoPopover`. This is a new,
self-contained widget -- it owns both its text input and its single
actionable row, takes keyboard focus itself (Down/Up to move, Enter to
activate, staged Escape to close) and dismisses on focus-out. It does not
subclass or reuse :class:`~ui_qt.search.SearchBar`, which owns navigation and
must not gain an authoring role.

This first increment offers only one action: creating a custom parameter with
the typed alias, using an honest empty value (``None``). Routing through
``core.commands.AddParameter`` and letting the validator judge legality is the
caller's responsibility, not this widget's. BPX-alias suggestions are a later
increment.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout, QWidget


class _PopupInput(QLineEdit):
    """The popup's own line edit; keeps key/focus handling local to the
    popup instead of reusing ``SearchBar``."""

    move_requested = Signal(int)
    activate_requested = Signal()
    escape_requested = Signal()
    focus_lost = Signal()

    def keyPressEvent(self, event) -> None:
        key = event.key()
        if key in (Qt.Key_Down, Qt.Key_Up):
            self.move_requested.emit(1 if key == Qt.Key_Down else -1)
            return
        if key in (Qt.Key_Return, Qt.Key_Enter):
            self.activate_requested.emit()
            return
        if key == Qt.Key_Escape:
            self.escape_requested.emit()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        self.focus_lost.emit()
        super().focusOutEvent(event)


class AddParameterPopup(QWidget):
    """Frameless popup offering to create a custom parameter in a section."""

    custom_parameter_requested = Signal(str)  # the typed alias

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("AddParameterPopup")
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setFixedWidth(320)

        self._existing_aliases: frozenset[str] = frozenset()

        self._input = _PopupInput()
        self._input.textChanged.connect(self._refresh_rows)
        self._input.move_requested.connect(self._move_selection)
        self._input.activate_requested.connect(self._activate)
        self._input.escape_requested.connect(self._on_escape)
        self._input.focus_lost.connect(self.hide)

        self._list = QListWidget()
        self._list.setFocusPolicy(Qt.NoFocus)
        self._list.itemClicked.connect(self._activate)

        layout = QVBoxLayout(self)
        layout.addWidget(self._input)
        layout.addWidget(self._list)

    # -- opening -----------------------------------------------------
    def open_for_section(
        self, anchor: QWidget, section_label: str, existing_aliases
    ) -> None:
        """Show the popup under *anchor*, scoped to *section_label*.

        *existing_aliases* is the set of parameter labels already present in
        the target section, so the custom-add row never offers to silently
        overwrite one.
        """
        self._existing_aliases = frozenset(existing_aliases)
        self._input.setPlaceholderText(f"Add parameter to {section_label}…")
        self._input.clear()
        self._refresh_rows("")
        bottom_left = anchor.mapToGlobal(anchor.rect().bottomLeft())
        self.move(bottom_left)
        self.show()
        self._input.setFocus(Qt.PopupFocusReason)

    # -- rows --------------------------------------------------------
    def _refresh_rows(self, text: str) -> None:
        self._list.clear()
        typed = text.strip()
        if typed and typed not in self._existing_aliases:
            item = QListWidgetItem(f"Create custom parameter: '{typed}'")
            self._list.addItem(item)
            self._list.setCurrentRow(0)

    def _activate(self, *_args) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        typed = self._input.text().strip()
        if not typed or typed in self._existing_aliases:
            return
        self.hide()
        self.custom_parameter_requested.emit(typed)

    # -- keyboard ------------------------------------------------------
    def _move_selection(self, delta: int) -> None:
        count = self._list.count()
        if not count:
            return
        row = (self._list.currentRow() + delta) % count
        self._list.setCurrentRow(row)

    def _on_escape(self) -> None:
        """Staged Escape: clear typed text first, then close the popup."""
        if self._input.text():
            self._input.clear()
        else:
            self.hide()
