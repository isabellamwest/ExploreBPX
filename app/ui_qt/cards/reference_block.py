"""ReferenceValueBlock: the "Reference file" heading + read-only value row
shared by ``ParameterCard`` (its reference section, multi-file track M2/M3;
see ``ParameterCard.set_reference``) and ``GhostParameterCard`` (which shows
it unconditionally) -- one widget so the two can never drift apart.

Plain ``QLabel``s and a button only -- deliberately outside any editor's
draft/commit machinery (known Qt pitfall): populating it can never trip
``_touched``, since it wires no signal into an editor at all. The block owns
no identity of its own any more (the comparison strip owns the reference
filename); it shows only the value and a "Copy up" action.

For a differing, table-representable reference, the one-line summary gives
way to :class:`ReferenceTableGrid` -- a small read-only x/y grid in the same
purple-box chrome (:meth:`ReferenceValueBlock.set_table_rows`). For a ``str``
expression, the box shows the full text rather than the truncated one-line
preview every other kind uses (:meth:`ReferenceValueBlock.set_content`'s
*monospace* flag) -- both cases use the app's own fixed-pitch convention
(``QFontDatabase.systemFont(QFontDatabase.FixedFont)``, the same one the
Source page's raw-JSON panes use), not a fresh font choice.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontDatabase
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.values import format_value

from .. import style
from ..style import VALUE_INPUT_MAX_WIDTH

#: "No maximum": Qt's QWIDGETSIZE_MAX, restored when the row is not narrow.
_NO_MAX_WIDTH = 16777215

#: Data rows shown before ``ReferenceTableGrid`` scrolls -- a compact glance,
#: not a second full editor.
_VISIBLE_ROWS = 6


def _monospace_font():
    return QFontDatabase.systemFont(QFontDatabase.FixedFont)


class ReferenceTableGrid(QWidget):
    """A read-only ``x``/``y`` grid of a differing reference table's rows.

    Shown inside :class:`ReferenceValueBlock`'s purple value box in place of
    the one-line ``table · N points`` summary, once the reference is
    table-representable and does not equal main (:meth:`set_rows`). A row
    that has no exactly-matching ``(x, y)`` pair in the main draft -- see
    ``core.compare.matching_table_rows`` -- renders both its cells in
    reference purple; a row that happens to coincide with a main row reads
    as ordinary text, the same restraint the rest of the app gives an
    EQUAL row.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceTableGrid")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 2)
        self._table.setHorizontalHeaderLabels(("x", "y"))
        self._table.verticalHeader().setVisible(False)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.setSelectionMode(QAbstractItemView.NoSelection)
        self._table.setFocusPolicy(Qt.NoFocus)
        self._table.setShowGrid(False)
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self._table.setFixedHeight(self._capped_height())
        layout.addWidget(self._table)

    def _capped_height(self) -> int:
        header = self._table.horizontalHeader().sizeHint().height()
        row = self._table.verticalHeader().defaultSectionSize()
        return header + row * _VISIBLE_ROWS + 2 * self._table.frameWidth()

    def set_rows(self, rows: list[list[object]], matches: list[bool]) -> None:
        """Populate from *rows* (each an ``(x, y)`` pair); *matches* marks,
        row for row, whether that pair already exists in the main draft."""
        font = _monospace_font()
        purple = QBrush(QColor(style.REFERENCE))
        self._table.setRowCount(len(rows))
        for row_index, ((x, y), matched) in enumerate(zip(rows, matches)):
            x_item = QTableWidgetItem(format_value(x))
            y_item = QTableWidgetItem(format_value(y))
            for item in (x_item, y_item):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setFont(font)
                if not matched:
                    item.setForeground(purple)
            self._table.setItem(row_index, 0, x_item)
            self._table.setItem(row_index, 1, y_item)


class ReferenceValueBlock(QFrame):
    """The "Reference file" heading plus its read-only value row: a purple-
    framed value box, an optional unit label (mirroring the main editor's
    own, for the kinds that show one), and a "Copy up" button."""

    #: Emitted when "Copy up" is clicked. Purely informational at this
    #: milestone -- the owning card re-exposes it verbatim; nothing wires it
    #: any further yet.
    copy_up_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceBlock")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 6, 0, 0)
        layout.setSpacing(4)

        self._heading = QLabel("Reference file")
        self._heading.setObjectName("ReferenceFileHeading")
        layout.addWidget(self._heading)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._value_box = QFrame()
        self._value_box.setObjectName("ReferenceValueBox")
        box_layout = QHBoxLayout(self._value_box)
        box_layout.setContentsMargins(8, 4, 8, 4)
        self._value = QLabel()
        self._value.setObjectName("ReferenceBlockValue")
        self._value.setWordWrap(True)
        #: Captured once, before any monospace switch, so ``set_content``
        #: can always restore the ordinary (stylesheet-driven) font -- a
        #: parameter with no full-expression reference must never inherit a
        #: fixed-pitch look left over from a previous one shown in this same,
        #: reused widget.
        self._default_font = self._value.font()
        box_layout.addWidget(self._value)

        self._table_grid = ReferenceTableGrid()
        self._table_grid.hide()
        box_layout.addWidget(self._table_grid, 1)
        row.addWidget(self._value_box, 1)

        #: Hidden by default -- shown only for the kinds whose main editor
        #: shows a unit label too (see ``set_content``).
        self._unit_label = QLabel()
        self._unit_label.setObjectName("ReferenceUnitLabel")
        self._unit_label.hide()
        row.addWidget(self._unit_label)

        # Zero-stretch spacer: inert while the (stretch-1) value box may grow,
        # but when the box is capped (*narrow*) it soaks up the slack so the
        # button keeps its natural width instead of inheriting the row's.
        row.addStretch(0)

        self._copy_up = QPushButton("Copy up")
        self._copy_up.setObjectName("CopyUpButton")
        self._copy_up.clicked.connect(self.copy_up_requested)
        row.addWidget(self._copy_up)

        layout.addLayout(row)

    def set_content(
        self,
        value_text: str,
        unit: str,
        same_as_main: bool,
        *,
        narrow: bool = False,
        monospace: bool = False,
    ) -> None:
        """Show the reference's *value_text* (and *unit*, if any) as the
        one-line/plain-text row, replacing any table grid the box may have
        been showing (:meth:`set_table_rows`).

        *same_as_main* (an EQUAL row) appends " · same" and renders the value
        in the faint "same" style rather than the loud one, and disables
        "Copy up" -- there is nothing to copy. An empty *unit* hides the unit
        label entirely, the same as the main editor's own unit label.

        *narrow* mirrors the main editor's input width (structured-page
        layout): the kinds whose main input is capped at
        ``VALUE_INPUT_MAX_WIDTH`` cap this box the same, so the two value
        columns align; every other kind's value (a series, a table preview)
        keeps the full row.

        *monospace* is set for a full function/expression string -- shown in
        full, word-wrapped and multiline-preserved, in the app's fixed-pitch
        convention rather than the ordinary proportional one.
        """
        self._table_grid.hide()
        self._value.show()
        self._value_box.setMaximumWidth(
            VALUE_INPUT_MAX_WIDTH if narrow else _NO_MAX_WIDTH
        )
        self._value.setText(f"{value_text} · same" if same_as_main else value_text)
        self._value.setFont(_monospace_font() if monospace else self._default_font)
        self._value.setProperty("same", same_as_main)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        self._unit_label.setText(unit)
        self._unit_label.setVisible(bool(unit))
        self._copy_up.setEnabled(not same_as_main)

    def set_table_rows(self, rows: list[list[object]], matches: list[bool]) -> None:
        """Show a differing, table-representable reference as a read-only
        grid instead of the one-line summary (:meth:`set_content`).

        Only ever called for a non-EQUAL row -- ``ParameterCard`` keeps the
        compact one-liner for an EQUAL table -- so "Copy up" always stays
        enabled here; there is no *narrow*/unit affordance, matching the
        main table editor's own kind, which shows neither.
        """
        self._value.hide()
        self._value_box.setMaximumWidth(_NO_MAX_WIDTH)
        self._table_grid.set_rows(rows, matches)
        self._table_grid.show()
        self._unit_label.setText("")
        self._unit_label.hide()
        self._copy_up.setEnabled(True)
