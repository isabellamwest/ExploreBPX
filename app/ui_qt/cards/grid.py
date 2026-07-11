"""``NumericGrid``: the tabular editor shared by series and interpolated tables.

A ``QTableView`` over a small ``QAbstractTableModel`` rather than a
``QTableWidget``: a validation experiment's arrays run to thousands of rows, and
a per-cell widget tree would be paid for on every one of them.

**Cells hold objects, not floats.** A cell the user types ``oops`` into keeps
the string ``"oops"``; an empty cell is ``None``. ``values()`` returns those
objects verbatim. This is the same contract every other card honours: the card
emits raw input and never judges validity, and the BPX validator reports the
type error. A bad cell is *never* coerced to ``0``, and a blank one is never
coerced to ``""`` -- either would silently invent data.

**Keyboard.** Enter and Escape mean different things depending on where they
land, and the two layers do not collide:

- inside an open cell editor, Qt's delegate consumes them: Enter confirms the
  cell, Escape cancels it. Neither reaches the card;
- on the grid itself, they are the app-wide contract from
  :class:`~.base.EditorCard`: Enter commits the draft to the document, Escape
  reverts it.

The load-bearing mechanism for the grid-level case is the card's event filter
on the view (installed by ``SeriesCard`` via ``_install_keyboard_handler``): it
consumes Return and Escape before the view acts on them. ``EditKeyPressed`` is
additionally left out of the view's edit triggers, so even without that filter
Enter would not open a cell editor -- belt and suspenders, not the guard itself.
Typing a character still opens an editor (``AnyKeyPressed``), as does a
double-click, which is how a cell is edited.
"""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QHBoxLayout,
    QHeaderView,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from ..style import MUTED
from .paste import parse_clipboard
from .paste_dialog import PastePreviewDialog, PastePreviewResult
from .values import format_value, parse_value, values_equal

#: Rows shown before the grid scrolls. The grid keeps this height whatever it
#: holds, so adding a row never reflows the Inspector around it.
VISIBLE_ROWS = 8


class _GridModel(QAbstractTableModel):
    """Rows of raw cell objects behind a fixed set of columns.

    Optionally carries *context columns*: read-only columns appended after the
    editable ones, each with its own independent length (a Validation run's
    sibling arrays beside the one being edited). Context cells are display
    only -- ``rows()`` never includes them and their length never pads the
    editable rows, so a sibling longer than the edited column shows *phantom*
    rows (visible, disabled) that no commit can ever pick up as invented data.
    """

    def __init__(
        self,
        headers: tuple[str, ...],
        text_columns: frozenset[int] = frozenset(),
        context_columns: tuple[tuple[str, tuple[object, ...]], ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        #: Columns whose cells are verbatim text, not lenient-parsed numbers
        #: (a material map's key column). Empty by default, so a numeric grid
        #: (series, x/y table) is unchanged.
        self._text_columns = frozenset(text_columns)
        self._editable = len(headers)
        self._context = tuple(
            (str(label), tuple(cells)) for label, cells in context_columns
        )
        self._headers = tuple(headers) + tuple(label for label, _ in self._context)
        self._rows: list[list[object]] = []

    def _context_rows(self) -> int:
        return max((len(cells) for _, cells in self._context), default=0)

    # --- Qt model interface -------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return max(len(self._rows), self._context_rows())

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        if role in (Qt.DisplayRole, Qt.EditRole):
            if column >= self._editable:
                cells = self._context[column - self._editable][1]
                return format_value(cells[row]) if row < len(cells) else ""
            if row >= len(self._rows):
                return ""  # phantom row: a longer sibling, not a value
            return format_value(self._rows[row][column])
        if role == Qt.ForegroundRole and column >= self._editable:
            # Context columns read as background material, not as the value
            # under edit.
            return QBrush(QColor(MUTED))
        if role == Qt.TextAlignmentRole:
            # Text columns (map keys) read left-aligned like the words they
            # hold; numeric columns stay right-aligned under their header.
            if column in self._text_columns:
                return int(Qt.AlignLeft | Qt.AlignVCenter)
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:  # noqa: N802
        """Store the typed text as a raw object, never as a coerced number."""
        if not index.isValid() or role != Qt.EditRole:
            return False
        if index.column() >= self._editable or index.row() >= len(self._rows):
            return False  # context or phantom cell: never writable
        parsed = self._parse_cell(index.column(), str(value))
        current = self._rows[index.row()][index.column()]
        if values_equal(parsed, current):
            return False  # a no-op re-type is not a change
        self._rows[index.row()][index.column()] = parsed
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def _parse_cell(self, column: int, text: str) -> object:
        """Turn typed *text* into a stored cell object.

        A text column keeps the string verbatim (empty is ``None``), never
        coercing a key like ``"1"`` into a number. A numeric column uses the
        app-wide lenient convention (:func:`parse_value`).
        """
        if column in self._text_columns:
            return text.strip() or None
        return parse_value(text)

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        if index.column() >= self._editable:
            # Read-only context: selectable (so it can be inspected/copied)
            # but never editable.
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.row() >= len(self._rows):
            return Qt.ItemIsEnabled  # phantom row below the edited column's end
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self._headers[section]
        return str(section + 1)  # 1-based row-number gutter

    # --- content ------------------------------------------------------
    @property
    def headers(self) -> tuple[str, ...]:
        return self._headers

    @property
    def editable_column_count(self) -> int:
        return self._editable

    def editable_row_count(self) -> int:
        """How many rows the edited value actually has -- phantom rows shown
        under a longer context column do not count."""
        return len(self._rows)

    def rows(self) -> list[list[object]]:
        """The editable rows only, each ``editable_column_count`` cells wide.

        Context cells are never included and a longer context column never
        pads the result: the value that reads back is exactly the value the
        user edited.
        """
        return [list(row) for row in self._rows]

    def set_rows(self, rows) -> None:
        self.beginResetModel()
        self._rows = [list(row) for row in rows]
        self.endResetModel()

    def insert_row(self, at: int) -> None:
        if self._context:
            # With context columns the display row count is a max() over
            # independent lengths, so an insert may not add a display row at
            # all (the phantom region shrinks by one instead). A reset is the
            # one notification that is correct in every case.
            self.beginResetModel()
            self._rows.insert(at, [None] * self._editable)
            self.endResetModel()
            return
        self.beginInsertRows(QModelIndex(), at, at)
        self._rows.insert(at, [None] * self._editable)
        self.endInsertRows()

    def append_row(self, cells) -> int:
        at = len(self._rows)
        if self._context:
            self.beginResetModel()
            self._rows.append(list(cells))
            self.endResetModel()
            return at
        self.beginInsertRows(QModelIndex(), at, at)
        self._rows.append(list(cells))
        self.endInsertRows()
        return at

    def remove_row(self, at: int) -> None:
        if self._context:
            self.beginResetModel()
            del self._rows[at]
            self.endResetModel()
            return
        self.beginRemoveRows(QModelIndex(), at, at)
        del self._rows[at]
        self.endRemoveRows()


class NumericGrid(QWidget):
    """A compact, scrolling table of raw cell values with add/remove row."""

    #: Emitted on a user edit: a cell changed, or a row was added or removed.
    #: Deliberately *not* emitted by :meth:`set_values`, which seeds or restores
    #: the grid -- a card populates its editor before wiring the change signal,
    #: so seeding must never mark the card touched (see ``EditorCard``).
    changed = Signal()

    #: Emitted when the user toggles the expand (⤢) affordance: ``True`` to take
    #: over the pane, ``False`` to collapse. The grid grows itself; a host (the
    #: Inspector) may additionally react -- hiding the secondary workspace -- but
    #: the grid works standalone when nobody listens.
    expand_toggled = Signal(bool)

    def __init__(
        self,
        headers: tuple[str, ...],
        text_columns: frozenset[int] = frozenset(),
        bulk: bool = True,
        context_columns: tuple[tuple[str, tuple[object, ...]], ...] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = _GridModel(headers, text_columns, context_columns, self)
        #: Bulk affordances (expand + clipboard paste) suit a numeric array, not
        #: the tiny key/value material map -- which passes ``bulk=False``.
        self._bulk = bulk
        self._expanded = False

        self._view = QTableView()
        self._view.setModel(self._model)
        self._view.setSelectionMode(QAbstractItemView.SingleSelection)
        self._view.setSelectionBehavior(QAbstractItemView.SelectItems)
        self._view.setEditTriggers(
            QAbstractItemView.DoubleClicked
            | QAbstractItemView.SelectedClicked
            | QAbstractItemView.AnyKeyPressed
        )
        self._view.setCornerButtonEnabled(False)
        self._view.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._view.setFixedHeight(self._compact_height())

        self._add_button = self._row_button("+", "Add row", self.insert_row)
        self._remove_button = self._row_button("−", "Remove row", self.remove_row)

        self._buttons = QHBoxLayout()
        self._buttons.setContentsMargins(0, 0, 0, 0)
        self._buttons.addWidget(self._add_button)
        self._buttons.addWidget(self._remove_button)
        self._buttons.addStretch(1)

        # Paste needs no button: Ctrl+V works whenever the grid has focus, and
        # the same action sits in the grid's right-click menu -- spreadsheet
        # muscle memory, with no chrome on the card. Expand/Collapse is a text
        # action, the app's convention for named actions (Save, Export, Undo).
        self._expand_button = None
        if self._bulk:
            self._expand_button = self._row_button(
                "Expand", "Grow the editor to fill the panel", self._toggle_expanded
            )
            self._buttons.addWidget(self._expand_button)
            self._view.installEventFilter(self)
            self._install_context_menu()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        layout.addLayout(self._buttons)

        # Cell edits arrive via ``dataChanged``. Row additions/removals emit
        # ``changed`` from the grid methods below instead of from the model's
        # insert/remove signals: with context columns the model notifies
        # structural changes as resets, and a reset is deliberately silent
        # (``set_values`` seeds through it).
        self._model.dataChanged.connect(lambda *_: self.changed.emit())
        self._model.modelReset.connect(self._refresh_buttons)
        self.changed.connect(self._refresh_buttons)
        self._refresh_buttons()

    def _row_button(self, text: str, tooltip: str, slot) -> QToolButton:
        button = QToolButton()
        button.setText(text)
        button.setToolTip(tooltip)
        button.setAccessibleName(tooltip)
        button.setAutoRaise(True)
        button.clicked.connect(slot)
        return button

    def _compact_height(self) -> int:
        header = self._view.horizontalHeader().sizeHint().height()
        row = self._view.verticalHeader().defaultSectionSize()
        return header + row * VISIBLE_ROWS + 2 * self._view.frameWidth()

    # --- bulk affordances: expand + clipboard paste -------------------
    def _install_context_menu(self) -> None:
        """Right-click on the grid offers Paste and the row actions.

        ``ActionsContextMenu`` lets Qt own the popup (no ``QMenu.exec()`` of our
        own -- see the remove-parameter tests for why that matters offscreen).
        The Paste action's ``WidgetShortcut`` is also what makes Ctrl+V work
        while the grid has focus: one action, reachable both ways, showing its
        shortcut in the menu.
        """
        from PySide6.QtGui import QAction

        self._paste_action = QAction("Paste", self._view)
        self._paste_action.setShortcut(QKeySequence.Paste)
        self._paste_action.setShortcutContext(Qt.WidgetShortcut)
        self._paste_action.triggered.connect(self.paste)
        add = QAction("Add row", self._view)
        add.triggered.connect(self.insert_row)
        remove = QAction("Remove row", self._view)
        remove.triggered.connect(self.remove_row)
        self._view.addActions([self._paste_action, add, remove])
        self._view.setContextMenuPolicy(Qt.ActionsContextMenu)

    def _toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)
        self.expand_toggled.emit(self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Grow the grid to fill the pane (expanded) or return to compact height.

        Expanding reveals the Paste button and lets the view stretch; collapsing
        restores the fixed eight-row height so the surrounding card is unchanged.
        """
        self._expanded = expanded
        if expanded:
            self._view.setMinimumHeight(self._compact_height())
            self._view.setMaximumHeight(16_777_215)  # Qt's QWIDGETSIZE_MAX
            self._view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        else:
            self._view.setFixedHeight(self._compact_height())
            self._view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        if self._expand_button is not None:
            self._expand_button.setText("Collapse" if expanded else "Expand")
            self._expand_button.setToolTip(
                "Return the editor to its compact size"
                if expanded
                else "Grow the editor to fill the panel"
            )

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    def paste(self) -> None:
        """Parse the clipboard, preview it, and (on confirm) replace or append."""
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        parsed = parse_clipboard(text, self._model.editable_column_count)
        if parsed.row_count == 0:
            return
        dialog = PastePreviewDialog(parsed, self._model.headers, self)
        dialog.exec()
        if dialog.choice is not None:
            self.apply_paste(parsed.rows, dialog.choice)

    def apply_paste(self, rows, mode: str) -> None:
        """Write parsed *rows* into the grid; a paste is a real user edit.

        ``set_rows`` is silent by design (it seeds), so this emits ``changed``
        itself -- a paste must mark the card dirty and kick live validation.
        """
        existing = self._model.rows() if mode == PastePreviewResult.APPEND else []
        self._model.set_rows(existing + [list(row) for row in rows])
        self.changed.emit()

    def _refresh_buttons(self) -> None:
        """Greying an inapplicable action is the app's convention; hiding is for
        unbuilt ones. With no rows there is nothing to remove."""
        self._remove_button.setEnabled(self.row_count > 0)

    # --- API ----------------------------------------------------------
    @property
    def row_count(self) -> int:
        """Rows of the *edited value*; phantom rows under a longer read-only
        sibling column are display only and never counted."""
        return self._model.editable_row_count()

    def focus_widget(self) -> QWidget:
        """The widget that takes keyboard focus, for the card's key handler."""
        return self._view

    def values(self) -> list[list[object]]:
        """Every row's cells, verbatim: ``int``, ``float``, ``str`` or ``None``."""
        return self._model.rows()

    def set_values(self, rows) -> None:
        """Replace the contents. Does not emit ``changed`` (see the signal)."""
        self._model.set_rows(rows)

    def insert_row(self) -> None:
        """Add an empty row below the current one, or at the end.

        The insertion point is clamped to the edited value's length: with a
        longer sibling column alongside, the current cell can sit in the
        phantom region, and a row must never be created beyond the value's
        end (the gap would read back as invented ``None`` items).
        """
        index = self._view.currentIndex()
        at = min(index.row() + 1, self.row_count) if index.isValid() else self.row_count
        self._model.insert_row(at)
        self._view.setCurrentIndex(self._model.index(at, 0))
        self.changed.emit()

    def append_row(self, cells) -> None:
        """Append a row pre-filled with *cells* and select its first cell.

        Used to add a keyed row from a suggestion (a material map's ``+ ▾``),
        where the row is not blank but carries a known key. Emits ``changed``
        like any other user-initiated row addition.
        """
        at = self._model.append_row(cells)
        self._view.setCurrentIndex(self._model.index(at, 0))
        self.changed.emit()

    def add_toolbar_widget(self, widget: QWidget) -> None:
        """Place *widget* in the +/− button row, before the trailing stretch.

        Lets a specialised card (the material map) add its own affordance --
        a suggestions dropdown -- alongside the shared add/remove buttons
        without the grid needing to know what it is.
        """
        self._buttons.insertWidget(self._buttons.count() - 1, widget)

    def remove_row(self) -> None:
        """Remove the current row, or the last one when nothing is selected.

        Clamped like :meth:`insert_row`: a current cell in the phantom region
        under a longer sibling column removes the value's last row.
        """
        if not self.row_count:
            return
        index = self._view.currentIndex()
        at = min(index.row(), self.row_count - 1) if index.isValid() else self.row_count - 1
        self._model.remove_row(at)
        self.changed.emit()
