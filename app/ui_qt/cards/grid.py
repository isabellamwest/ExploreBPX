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

- inside an open cell editor, they are the cell's: Enter confirms it, Escape
  cancels it. Neither reaches the document;
- on the grid itself, they are the app-wide contract from
  :class:`~.base.EditorCard`: Enter commits the draft to the document, Escape
  reverts it.

Three things keep that split legible rather than a trap:

- the card's filter **stands aside while a cell editor is open**
  (``base._sub_editor_owns_keys``). Qt does not consume Enter in the
  delegate -- it queues the cell's commit-and-close and lets the key travel
  on to the view, where the filter sits -- so without that check a
  cell-level Enter wrote the whole draft to the document;
- confirming a cell **steps the selection down a row** (:class:`_GridView`),
  so the spreadsheet habit of "Enter, Enter, Enter" walks down the column
  rather than stopping dead on the row just typed;
- a dirty grid shows an **"Unsaved edits" bar** (:class:`_PendingBar`) naming
  both halves of the contract -- Apply (Enter) and Discard (Esc) -- as
  clickable buttons. The grid never decides when: the owning card drives
  :meth:`NumericGrid.set_pending` from its real ``is_dirty`` state (see
  ``EditorCard._bind_grid_pending``), so the bar shows exactly when Enter
  would actually write the file.

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
    QAbstractItemDelegate,
    QAbstractItemView,
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QSizePolicy,
    QTableView,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.csv_import import positional_map, read_csv_file
from core.paste import parse_clipboard
from core.values import format_value, parse_value, values_equal

from ..style import ACCENT, BORDER, ERROR_TINT, MUTED, NEUTRAL_TINT
from .csv_dialog import CsvImportDialog
from .paste_dialog import PastePreviewDialog, PastePreviewResult

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
        #: ``{(row, column): validator message}``, editable cells only. The
        #: model never judges a cell; the Inspector pushes what the validator
        #: said (see ``cell_issues``) through :meth:`set_issues`.
        self._issues: dict[tuple[int, int], str] = {}

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
        cell = (row, column)
        if role == Qt.BackgroundRole and cell in self._issues:
            return QBrush(QColor(ERROR_TINT))
        if role == Qt.ToolTipRole and cell in self._issues:
            return self._issues[cell]
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
        self.set_issues({})  # stale tints would misattribute (see set_issues)

    def issues(self) -> dict[tuple[int, int], str]:
        return dict(self._issues)

    def set_issues(self, issues: dict[tuple[int, int], str]) -> None:
        """Re-tint from the validator's own diagnostics.

        A no-op when nothing changed, so a live-preview refresh that reports
        the same issues neither repaints nor -- via ``NumericGrid`` -- marks
        the card touched on every keystroke.

        Called with ``{}`` after any structural edit (insert/remove/replace
        rows): the map is keyed by row index, and a row shift or wholesale
        replacement invalidates every key without moving it, so a stale entry
        would silently tint whatever cell now sits at that index rather than
        the one the validator meant. Clearing is honest, not judgment -- an
        empty map asserts nothing -- and the real answer returns as soon as
        the debounced live validation (or a commit) calls this again.
        """
        if issues == self._issues:
            return
        self._issues = dict(issues)
        if not self._rows:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(len(self._rows) - 1, self._editable - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole, Qt.ToolTipRole])

    def insert_row(self, at: int) -> None:
        if self._context:
            # With context columns the display row count is a max() over
            # independent lengths, so an insert may not add a display row at
            # all (the phantom region shrinks by one instead). A reset is the
            # one notification that is correct in every case.
            self.beginResetModel()
            self._rows.insert(at, [None] * self._editable)
            self.endResetModel()
            self.set_issues({})  # stale tints would misattribute (see set_issues)
            return
        self.beginInsertRows(QModelIndex(), at, at)
        self._rows.insert(at, [None] * self._editable)
        self.endInsertRows()
        self.set_issues({})  # stale tints would misattribute (see set_issues)

    def append_row(self, cells) -> int:
        at = len(self._rows)
        if self._context:
            self.beginResetModel()
            self._rows.append(list(cells))
            self.endResetModel()
            self.set_issues({})  # stale tints would misattribute (see set_issues)
            return at
        self.beginInsertRows(QModelIndex(), at, at)
        self._rows.append(list(cells))
        self.endInsertRows()
        self.set_issues({})  # stale tints would misattribute (see set_issues)
        return at

    def remove_row(self, at: int) -> None:
        if self._context:
            self.beginResetModel()
            del self._rows[at]
            self.endResetModel()
            self.set_issues({})  # stale tints would misattribute (see set_issues)
            return
        self.beginRemoveRows(QModelIndex(), at, at)
        del self._rows[at]
        self.endRemoveRows()
        self.set_issues({})  # stale tints would misattribute (see set_issues)


class _GridView(QTableView):
    """A table view whose cell-editor Enter confirms the cell *and steps down*.

    Qt's default leaves the just-edited cell current, so "Enter to confirm,
    Enter to move on" would type over the row just finished. Stepping down
    gives that spreadsheet habit the column walk it expects, clamped at the
    last display row.

    This is convenience, not the safety guard: what stops a cell-level Enter
    from committing the document is the card's filter standing aside while
    an editor is open (``base._sub_editor_owns_keys``).

    Escape and Tab keep Qt's behaviour: only the delegate's *submit* close
    (``SubmitModelCache``, what its editor emits for Enter) is redirected.
    """

    def closeEditor(self, editor, hint) -> None:  # noqa: N802
        if hint == QAbstractItemDelegate.SubmitModelCache:
            super().closeEditor(editor, QAbstractItemDelegate.NoHint)
            index = self.currentIndex()
            if index.isValid() and index.row() + 1 < self.model().rowCount():
                self.setCurrentIndex(self.model().index(index.row() + 1, index.column()))
            return
        super().closeEditor(editor, hint)


class _PendingBar(QWidget):
    """The "Unsaved edits · Apply · Discard" strip under a dirty grid.

    The grid's draft/commit cycle used to be invisible: Enter-to-apply and
    Esc-to-discard existed only in a collapsed hint. This bar is the visible
    face of that state -- a small dot, the words, and the two halves of the
    keyboard contract as clickable buttons with their keys named.

    Display and mouse access only: the bar owns no commit logic. The owning
    card shows/hides it from its real dirty state and wires the buttons back
    into the exact keyboard paths (``commit_requested`` / ``_reset_draft``),
    so clicking Apply is Enter and clicking Discard is Esc, nothing more.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("GridPendingBar")
        # A stylesheet background on a plain QWidget needs this attribute to
        # actually paint.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet(
            f"#GridPendingBar {{ background: {NEUTRAL_TINT}; "
            f"border: 1px solid {BORDER}; border-radius: 4px; }}"
        )

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 2, 6, 2)
        layout.setSpacing(6)

        # The unified dot language's small (8px) mark, in the accent colour:
        # "edited, not yet written" is a document state, never a severity, so
        # it must not read as a validator warning.
        dot = QLabel("●")
        dot.setStyleSheet(f"color: {ACCENT}; font-size: 8px;")
        layout.addWidget(dot)
        label = QLabel("Unsaved edits")
        label.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(label)
        layout.addStretch(1)

        self.apply_button = QToolButton()
        self.apply_button.setText("Apply (Enter)")
        self.apply_button.setToolTip("Write these edits to the file")
        self.apply_button.setAccessibleName("Apply edits")
        self.apply_button.setAutoRaise(True)
        self.apply_button.setStyleSheet(f"color: {ACCENT}; font-weight: 600;")
        layout.addWidget(self.apply_button)

        self.discard_button = QToolButton()
        self.discard_button.setText("Discard (Esc)")
        self.discard_button.setToolTip("Revert to the file's value")
        self.discard_button.setAccessibleName("Discard edits")
        self.discard_button.setAutoRaise(True)
        layout.addWidget(self.discard_button)


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

    #: Emitted when the pending bar's Apply button is clicked. The owning card
    #: routes it into the same path as Enter on the grid (``commit_requested``);
    #: the grid itself commits nothing.
    apply_clicked = Signal()
    #: Emitted when the pending bar's Discard button is clicked -- the mouse
    #: twin of Escape, routed by the card into ``_reset_draft``.
    discard_clicked = Signal()

    def __init__(
        self,
        headers: tuple[str, ...],
        text_columns: frozenset[int] = frozenset(),
        bulk: bool = True,
        context_columns: tuple[tuple[str, tuple[object, ...]], ...] = (),
        csv_import: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = _GridModel(headers, text_columns, context_columns, self)
        #: Bulk affordances (expand + clipboard paste) suit a numeric array, not
        #: the tiny key/value material map -- which passes ``bulk=False``.
        self._bulk = bulk
        self._expanded = False

        self._view = _GridView()
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

        # Opt-in via ``csv_import``: a grid whose value is *only* what it
        # holds -- the x/y table -- can fill itself from a file directly (see
        # :meth:`import_csv`). A grid that would need to reach sibling
        # parameters (the Validation series) must not sprout a second import
        # button here; that surface stays on the card that owns those paths.
        self._import_button = None
        if csv_import:
            self._import_button = self._row_button(
                "Import CSV…", "Fill this table from the columns of a file", self.import_csv
            )
            self.add_toolbar_widget(self._import_button)

        # Hidden until the owning card reports a real dirty draft (see
        # ``set_pending``); the buttons only re-enter the keyboard paths.
        self._pending_bar = _PendingBar()
        self._pending_bar.hide()
        self._pending_bar.apply_button.clicked.connect(self.apply_clicked)
        self._pending_bar.discard_button.clicked.connect(self.discard_clicked)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)
        layout.addLayout(self._buttons)
        layout.addWidget(self._pending_bar)

        # Cell edits arrive via ``dataChanged``. Row additions/removals emit
        # ``changed`` from the grid methods below instead of from the model's
        # insert/remove signals: with context columns the model notifies
        # structural changes as resets, and a reset is deliberately silent
        # (``set_values`` seeds through it).
        self._model.dataChanged.connect(self._on_data_changed)
        self._model.modelReset.connect(self._refresh_buttons)
        self.changed.connect(self._refresh_buttons)
        self._refresh_buttons()

    def _on_data_changed(self, _top_left, _bottom_right, roles=()) -> None:
        """A cell edit marks the card dirty; a validator re-tint does not.

        ``set_cell_issues`` repaints through this same ``dataChanged`` signal,
        but with only ``BackgroundRole``/``ToolTipRole`` in its role list.
        Treating that as a change would mark the card touched -- and kick live
        validation -- on every validator refresh, not just on a real edit.
        """
        if roles and Qt.EditRole not in roles and Qt.DisplayRole not in roles:
            return
        self.changed.emit()

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
            # The grid *widget* must expand too, not just its inner view: the
            # card's layout sizes this NumericGrid, and if it stays Preferred
            # the leftover pane height lands as a gap above the grid rather
            # than growing it.
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        else:
            self._view.setFixedHeight(self._compact_height())
            self._view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
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

    def import_csv(self) -> None:
        """Pick a file and, after mapping + preview, write it into this grid.

        Only reachable when the constructor's ``csv_import`` flag is set. The
        proposal is :func:`~.csv_import.positional_map`, not ``auto_map``:
        this grid's own headers (``x``/``y``) are exactly the short, generic
        names ``auto_map``'s substring rule is unsafe for -- "x" would match
        an unrelated header like "Extraction". Every target must be mapped
        (``require_all_targets``): the columns together are *one* value, so a
        half-mapped import would blank the other column, which is data loss,
        not a skip. Replace/Append (``offer_append``) is offered because,
        unlike a freshly-added parameter, this grid may already hold rows.

        This writes only what this grid holds, so it is a draft exactly like
        a paste: :meth:`apply_paste` is the terminal step, ``changed`` marks
        the card dirty, and Escape reverts it like any other unwritten edit --
        no command is involved. Contrast the series card's own CSV import,
        which fills *sibling* parameters this grid does not own: a card has
        no draft for a value it does not hold, so that import must commit
        through a command instead.
        """
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CSV",
            "",
            "CSV files (*.csv *.tsv *.txt);;All files (*)",
        )
        if not path:
            return
        data = read_csv_file(path)
        if data.row_count == 0:
            return
        headers = self._model.headers[: self._model.editable_column_count]
        dialog = CsvImportDialog(
            data,
            headers,
            self,
            proposed=positional_map(data.column_count, len(headers)),
            require_all_targets=True,
            offer_append=True,
        )
        dialog.exec()
        if dialog.accepted_mapping is not None:
            self._apply_csv_mapping(data, dialog.accepted_mapping, dialog.accepted_mode)

    def _apply_csv_mapping(self, data, mapping, mode: str) -> None:
        """Turn a confirmed column *mapping* into rows for :meth:`apply_paste`.

        An unmapped target reads as a column of ``None``s rather than raising
        -- ``require_all_targets`` already stops the dialog from confirming a
        partial mapping, so this only needs to be safe, not re-enforce it.
        """
        columns = [data.columns[index] if index is not None else () for index in mapping]
        row_count = max((len(column) for column in columns), default=0)
        rows = [
            [column[r] if r < len(column) else None for column in columns]
            for r in range(row_count)
        ]
        self.apply_paste(rows, mode)

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

    def set_cell_issues(self, issues: dict[tuple[int, int], str]) -> None:
        """Tint the cells the validator blamed, with its message on hover.

        The grid never decides this: it renders exactly what it is told (see
        ``cell_issues``), so the validator stays the source of truth. Passing
        an empty map clears every tint.
        """
        self._model.set_issues(issues)

    def set_pending(self, pending: bool) -> None:
        """Show or hide the "Unsaved edits" bar.

        The grid never decides this itself -- its ``changed`` signal fires on
        edits that may cancel out (retyping the original value) -- so the
        owning card drives it from its real ``is_dirty`` state, and the bar
        shows exactly when Enter would actually write the file.
        """
        self._pending_bar.setVisible(pending)

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


class _MultiColumnGridModel(QAbstractTableModel):
    """N independently-lengthed columns, every one of them editable.

    Each column maps to one BPX array, so a length mismatch between columns
    is the ordinary case -- bpx alone judges whether it's an error -- and the
    model never pads a shorter column or truncates a longer one.
    ``rowCount`` is simply the longest column. A cell past its own column's
    end is a blank "no value here" placeholder, muted the same way
    ``_GridModel`` mutes its read-only context columns -- except the cell
    immediately past the end, which is where typing appends a new item to
    that column (see :meth:`setData`). A cell further beyond that (a longer
    sibling column's reach) is display only, exactly like ``_GridModel``'s
    phantom rows.
    """

    def __init__(
        self,
        headers: tuple[str, ...],
        read_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._headers = tuple(headers)
        #: Gates ``setData``/``flags`` only, for a future card that renders
        #: the whole grid read-only (e.g. a diagnostics view of a run's
        #: arrays); seeding through :meth:`set_column_values` still works.
        self._read_only = read_only
        #: One independent list per column -- each maps to one BPX array, so
        #: a length mismatch between columns is the normal case (see the
        #: class docstring), never padded or equalised.
        self._columns: list[list[object]] = [[] for _ in self._headers]
        #: ``{(row, column): validator message}`` -- see ``_GridModel``.
        self._issues: dict[tuple[int, int], str] = {}

    # --- Qt model interface -------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return max((len(column) for column in self._columns), default=0)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._headers)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid():
            return None
        row, column = index.row(), index.column()
        cells = self._columns[column]
        if role in (Qt.DisplayRole, Qt.EditRole):
            return format_value(cells[row]) if row < len(cells) else ""
        if role == Qt.ForegroundRole and row >= len(cells):
            # Past this column's own data: "no value here", not a value
            # under edit.
            return QBrush(QColor(MUTED))
        cell = (row, column)
        if role == Qt.BackgroundRole and cell in self._issues:
            return QBrush(QColor(ERROR_TINT))
        if role == Qt.ToolTipRole and cell in self._issues:
            return self._issues[cell]
        if role == Qt.TextAlignmentRole:
            return int(Qt.AlignRight | Qt.AlignVCenter)
        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole) -> bool:  # noqa: N802
        """Write an existing cell, or append past that column's own end.

        A valid *index* is only ever handed out for ``row < rowCount()``
        (Qt's own bounds check in :meth:`index`), so a column can only ever
        be caught up to a *longer sibling*'s reach by typing -- becoming the
        outright longest column still needs the "+" button (see
        ``MultiColumnGrid.insert_cell``), exactly as growing ``NumericGrid``'s
        sole editable column always has. A cell strictly beyond the append
        position is a deeper phantom cell and is never writable. Typing
        nothing at the append position invents nothing -- exactly like a
        no-op re-type of an existing cell, it is simply not a change.
        """
        if not index.isValid() or role != Qt.EditRole or self._read_only:
            return False
        row, column = index.row(), index.column()
        cells = self._columns[column]
        if row > len(cells):
            return False  # deeper phantom cell: never writable
        parsed = parse_value(str(value))
        if row == len(cells):
            if parsed is None:
                return False  # nothing typed: no cell invented
            cells.append(parsed)
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
            self.set_issues({})  # stale tints would misattribute (see set_issues)
            return True
        current = cells[row]
        if values_equal(parsed, current):
            return False  # a no-op re-type is not a change
        cells[row] = parsed
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole])
        return True

    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        if not index.isValid():
            return Qt.NoItemFlags
        if self._read_only:
            # Read-only whole grid: selectable (so it can be inspected/
            # copied) but never editable -- same as _GridModel's context
            # columns.
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
        row, column = index.row(), index.column()
        if row > len(self._columns[column]):
            return Qt.ItemIsEnabled  # deeper phantom cell
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
    def column_count(self) -> int:
        return len(self._headers)

    def column_length(self, column: int) -> int:
        """How many real cells *column* holds -- not the display row count,
        which is the longest sibling column."""
        return len(self._columns[column])

    def column_values(self, column: int) -> list[object]:
        return list(self._columns[column])

    def set_column_values(self, column: int, values) -> None:
        self.beginResetModel()
        self._columns[column] = list(values)
        self.endResetModel()
        self.set_issues({})  # stale tints would misattribute (see set_issues)

    def issues(self) -> dict[tuple[int, int], str]:
        return dict(self._issues)

    def set_issues(self, issues: dict[tuple[int, int], str]) -> None:
        """Re-tint from the validator's own diagnostics -- see
        ``_GridModel.set_issues``: the no-op-when-unchanged check and the
        post-structural-edit clear both matter here for the same reasons.
        """
        if issues == self._issues:
            return
        self._issues = dict(issues)
        row_count = self.rowCount()
        if not row_count:
            return
        top_left = self.index(0, 0)
        bottom_right = self.index(row_count - 1, len(self._headers) - 1)
        self.dataChanged.emit(top_left, bottom_right, [Qt.BackgroundRole, Qt.ToolTipRole])

    def insert_cell(self, column: int, at: int) -> None:
        """Insert a blank cell into *column* alone, at row *at*.

        Always a reset: this column's own rows shift below *at*, but its
        siblings don't, and the display row count is a max() over
        independent lengths -- exactly what ``_GridModel`` documents for its
        context columns, so a reset is the one notification that's correct
        here too.
        """
        if self._read_only:
            return
        self.beginResetModel()
        self._columns[column].insert(at, None)
        self.endResetModel()
        self.set_issues({})  # stale tints would misattribute (see set_issues)

    def remove_cell(self, column: int, at: int) -> None:
        """Remove the cell at row *at* from *column* alone."""
        if self._read_only:
            return
        self.beginResetModel()
        del self._columns[column][at]
        self.endResetModel()
        self.set_issues({})  # stale tints would misattribute (see set_issues)


class MultiColumnGrid(QWidget):
    """Multiple independently-lengthed columns, every one of them editable.

    Unlike ``NumericGrid`` -- one edited column, optionally flanked by
    read-only context columns -- every column here is a value in its own
    right, each mapping to one BPX array. A length mismatch between columns
    is the ordinary case, so the grid never pads a shorter column or
    truncates a longer one; ``rowCount`` is simply the longest column (see
    ``_MultiColumnGridModel``).

    Add/remove act on the column of the current cell only: there is no
    single shared row to insert or remove across every column, because the
    columns do not share a length.
    """

    #: Emitted on a user edit: a cell changed, or a cell was inserted,
    #: removed, or appended (by typing past a column's own end) in some
    #: column. Not emitted by :meth:`set_column_values`, which seeds or
    #: restores one column -- see ``NumericGrid.changed``.
    changed = Signal()

    #: Emitted when the user toggles the expand (⤢) affordance -- the exact
    #: contract ``NumericGrid.expand_toggled`` documents (``True`` takes over
    #: the pane, the grid grows itself, a host may additionally react).
    expand_toggled = Signal(bool)

    #: Apply/Discard from the pending bar -- the exact contract
    #: ``NumericGrid.apply_clicked``/``discard_clicked`` document. Never
    #: emitted by a read-only grid, whose bar is not built at all.
    apply_clicked = Signal()
    discard_clicked = Signal()

    def __init__(
        self,
        headers: tuple[str, ...],
        read_only: bool = False,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._model = _MultiColumnGridModel(headers, read_only, self)
        self._read_only = read_only
        self._expanded = False

        self._view = _GridView()
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._view)

        # A read-only grid (a future card's display-only view) has nothing to
        # add or remove, so the button row simply doesn't exist for it --
        # the same absent-not-disabled convention as NumericGrid's
        # ``_import_button``/``_expand_button``. Kept as ``self._buttons`` (not
        # a local) so a caller (``ExperimentCard``'s "+ Temperature [K]"
        # button, its length-mismatch chip) can append into the same row via
        # :meth:`add_toolbar_widget`, exactly like ``NumericGrid``.
        self._add_button = None
        self._remove_button = None
        self._expand_button = None
        self._buttons = None
        self._pending_bar = None
        if not read_only:
            self._add_button = self._row_button("+", "Add cell", self.insert_cell)
            self._remove_button = self._row_button("−", "Remove cell", self.remove_cell)
            self._buttons = QHBoxLayout()
            self._buttons.setContentsMargins(0, 0, 0, 0)
            self._buttons.addWidget(self._add_button)
            self._buttons.addWidget(self._remove_button)
            self._buttons.addStretch(1)
            # Expand/Collapse, same named-action convention and placement
            # (after the stretch) as ``NumericGrid``'s -- see its own
            # constructor -- so an ``ExperimentCard``'s long grid can take
            # over the pane exactly like a series card's could.
            self._expand_button = self._row_button(
                "Expand", "Grow the editor to fill the panel", self._toggle_expanded
            )
            self._buttons.addWidget(self._expand_button)
            layout.addLayout(self._buttons)
            # Hidden until the owning card reports a real dirty draft (see
            # ``set_pending``) -- same contract as ``NumericGrid``'s bar.
            self._pending_bar = _PendingBar()
            self._pending_bar.hide()
            self._pending_bar.apply_button.clicked.connect(self.apply_clicked)
            self._pending_bar.discard_button.clicked.connect(self.discard_clicked)
            layout.addWidget(self._pending_bar)
            self._install_context_menu()

        # A cell edit -- including an in-place append past a column's own
        # end -- arrives via ``dataChanged`` (see the model's setData).
        # insert_cell/remove_cell go through a reset instead, deliberately
        # silent so set_column_values can seed through it, so those two
        # methods emit ``changed`` themselves.
        self._model.dataChanged.connect(self._on_data_changed)

    def _on_data_changed(self, _top_left, _bottom_right, roles=()) -> None:
        """A cell edit marks the card dirty; a validator re-tint does not --
        see ``NumericGrid._on_data_changed``."""
        if roles and Qt.EditRole not in roles and Qt.DisplayRole not in roles:
            return
        self.changed.emit()

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

    # --- bulk affordance: per-column clipboard paste --------------------
    def _install_context_menu(self) -> None:
        """Right-click offers Paste plus the row actions -- see
        ``NumericGrid._install_context_menu`` for why a real ``QAction`` (not
        a hand-rolled ``QMenu.exec()``) is what makes both the menu entry and
        the live ``Ctrl+V`` shortcut work from one binding."""
        from PySide6.QtGui import QAction

        self._paste_action = QAction("Paste", self._view)
        self._paste_action.setShortcut(QKeySequence.Paste)
        self._paste_action.setShortcutContext(Qt.WidgetShortcut)
        self._paste_action.triggered.connect(self.paste)
        add = QAction("Add cell", self._view)
        add.triggered.connect(self.insert_cell)
        remove = QAction("Remove cell", self._view)
        remove.triggered.connect(self.remove_cell)
        self._view.addActions([self._paste_action, add, remove])
        self._view.setContextMenuPolicy(Qt.ActionsContextMenu)

    def _toggle_expanded(self) -> None:
        self.set_expanded(not self._expanded)
        self.expand_toggled.emit(self._expanded)

    def set_expanded(self, expanded: bool) -> None:
        """Grow the grid to fill the pane (expanded) or return to compact
        height -- identical mechanics to ``NumericGrid.set_expanded``."""
        self._expanded = expanded
        if expanded:
            self._view.setMinimumHeight(self._compact_height())
            self._view.setMaximumHeight(16_777_215)  # Qt's QWIDGETSIZE_MAX
            self._view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        else:
            self._view.setFixedHeight(self._compact_height())
            self._view.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
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
        """Parse the clipboard into the focused column and preview it.

        Unlike ``NumericGrid`` -- one editable column, so a paste always
        targets it -- every column here is independently editable, so a paste
        must name which one: the focused column (the current cell), mirroring
        ``insert_cell``/``remove_cell``. Always parsed as a single column
        (``parse_clipboard(text, 1)``): a Validation run's arrays are pasted
        one at a time, matching ``SeriesCard``'s existing per-column
        convention -- pasting several columns at once is what CSV import is
        for.
        """
        if self._read_only:
            return
        text = QApplication.clipboard().text()
        if not text.strip():
            return
        parsed = parse_clipboard(text, 1)
        if parsed.row_count == 0:
            return
        column = self._focused_column()
        dialog = PastePreviewDialog(parsed, (self._model.headers[column],), self)
        dialog.exec()
        if dialog.choice is not None:
            self.apply_paste(column, [row[0] for row in parsed.rows], dialog.choice)

    def apply_paste(self, column: int, values, mode: str) -> None:
        """Write parsed *values* into *column* alone; a paste is a real edit.

        ``set_column_values`` is silent by design (it seeds), so this emits
        ``changed`` itself -- see ``NumericGrid.apply_paste``.
        """
        existing = self._model.column_values(column) if mode == PastePreviewResult.APPEND else []
        self._model.set_column_values(column, existing + list(values))
        self.changed.emit()

    # --- API ------------------------------------------------------------
    @property
    def column_count(self) -> int:
        return self._model.column_count

    def focus_widget(self) -> QWidget:
        """The widget that takes keyboard focus, for the card's key handler."""
        return self._view

    def column_length(self, column: int) -> int:
        """How many real cells *column* holds -- see ``_MultiColumnGridModel``."""
        return self._model.column_length(column)

    def column_values(self, column: int) -> list[object]:
        """*column*'s cells verbatim: ``int``, ``float``, ``str`` or ``None``."""
        return self._model.column_values(column)

    def set_column_values(self, column: int, values) -> None:
        """Replace one column's contents. Does not emit ``changed`` (seeding)."""
        self._model.set_column_values(column, values)

    def set_cell_issues(self, issues: dict[tuple[int, int], str]) -> None:
        """Tint the cells the validator blamed -- see ``NumericGrid.set_cell_issues``."""
        self._model.set_issues(issues)

    def set_pending(self, pending: bool) -> None:
        """Show or hide the "Unsaved edits" bar -- see
        ``NumericGrid.set_pending``. A no-op on a read-only grid, whose bar
        is never built."""
        if self._pending_bar is not None:
            self._pending_bar.setVisible(pending)

    def focus_column(self, column: int) -> None:
        """Give the view's current-cell ring to *column*'s first cell.

        Used when a card opens with one column already resolved by navigation
        (e.g. ``ExperimentCard`` revealed on one array), so the initial focus
        ring -- and hence +/-'s and paste's target -- lands there rather than
        column 0. A no-op for an out-of-range column or an empty grid (there
        is no cell to land on yet).
        """
        if not 0 <= column < self.column_count:
            return
        if self._model.rowCount() == 0:
            return
        self._view.setCurrentIndex(self._model.index(0, column))

    def add_toolbar_widget(self, widget: QWidget) -> None:
        """Place *widget* in the +/− button row, before the trailing stretch.

        Mirrors ``NumericGrid.add_toolbar_widget``; absent (not disabled) when
        the grid is read-only, since that row is never built at all then (see
        the constructor).
        """
        if self._buttons is None:
            return
        self._buttons.insertWidget(self._buttons.count() - 1, widget)

    def _focused_column(self) -> int:
        index = self._view.currentIndex()
        return index.column() if index.isValid() else 0

    def insert_cell(self) -> None:
        """Add a blank cell below the current row, in the focused column only.

        Clamped to that column's own length, mirroring
        ``NumericGrid.insert_row``: a current cell sitting in that column's
        own "no value here" region must never create a cell beyond its end.
        """
        if self._read_only:
            return
        column = self._focused_column()
        length = self._model.column_length(column)
        index = self._view.currentIndex()
        at = min(index.row() + 1, length) if index.isValid() else length
        self._model.insert_cell(column, at)
        self._view.setCurrentIndex(self._model.index(at, column))
        self.changed.emit()

    def remove_cell(self) -> None:
        """Remove a cell from the focused column: the current row, or the
        last one when nothing in that column is selected."""
        if self._read_only:
            return
        column = self._focused_column()
        length = self._model.column_length(column)
        if not length:
            return
        index = self._view.currentIndex()
        at = min(index.row(), length - 1) if index.isValid() else length - 1
        self._model.remove_cell(column, at)
        self.changed.emit()
