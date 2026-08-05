"""ReferenceValueBlock: the "Reference" role label + read-only value row
shared by ``ParameterCard`` (its reference section, multi-file track M2/M3;
see ``ParameterCard.set_reference``) and ``GhostParameterCard`` (which shows
it unconditionally) -- one widget so the two can never drift apart.

Aligned-rows layout: the label sits in a fixed-width column
(``style.ROLE_LABEL_WIDTH``, shared with ``ParameterCard``'s own "Main"
label) so the reference value starts at the same x as the main editor and
the eye compares the two vertically. The value itself is a flat neutral
wash, deliberately not styled like an input -- it is not editable -- and
not purple: purple stays on the label, differing grid cells and the chart
overlay.

Plain ``QLabel``s and a button only -- deliberately outside any editor's
draft/commit machinery (known Qt pitfall): populating it can never trip
``_touched``, since it wires no signal into an editor at all. The block owns
no identity of its own any more (the comparison strip owns the reference
filename); it shows only the value and a quiet "Copy up" text action.

For a differing, table-representable reference, the one-line summary gives
way to :class:`ReferenceTableGrid` -- a small read-only x/y grid in the same
washed box (:meth:`ReferenceValueBlock.set_table_rows`). For a ``str``
expression, the box shows the full text rather than the truncated one-line
preview every other kind uses (:meth:`ReferenceValueBlock.set_content`'s
*monospace* flag) -- both cases use the app's own monospace convention
(:func:`typography.mono`, the same one the Source page's raw-JSON panes
use), not a fresh font choice.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
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

from .. import style, typography

#: "No maximum": Qt's QWIDGETSIZE_MAX, restored when the row is not narrow.
_NO_MAX_WIDTH = 16777215

#: Data rows shown before ``ReferenceTableGrid`` scrolls -- a compact glance,
#: not a second full editor.
_VISIBLE_ROWS = 6


def _monospace_font():
    return typography.mono()


class ReferenceTableGrid(QWidget):
    """A read-only ``x``/``y`` grid of a differing reference table's rows.

    Shown inside :class:`ReferenceValueBlock`'s washed value box in place of
    the one-line ``table · N points`` summary, once the reference is
    table-representable and does not equal main (:meth:`set_rows`). A row
    that has no exactly-matching ``(x, y)`` pair in the main draft -- see
    ``core.compare.matching_table_rows`` -- renders both its cells in
    reference purple; a row that happens to coincide with a main row reads
    as quiet muted text, the same restraint the rest of the app gives an
    EQUAL row.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceTableGrid")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._table = QTableWidget(0, 2)
        self._table.setObjectName("ReferenceTableGridTable")
        self._table.setHorizontalHeaderLabels(("x", "y"))
        self._table.verticalHeader().setVisible(False)
        # Dense glance rows: this is a comparison aid, not a second editor,
        # so it packs tighter than the main grid's editable rows.
        self._table.verticalHeader().setDefaultSectionSize(20)
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
        muted = QBrush(QColor(style.MUTED))
        self._table.setRowCount(len(rows))
        for row_index, ((x, y), matched) in enumerate(zip(rows, matches)):
            x_item = QTableWidgetItem(format_value(x))
            y_item = QTableWidgetItem(format_value(y))
            for item in (x_item, y_item):
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setFont(font)
                item.setForeground(purple if not matched else muted)
            self._table.setItem(row_index, 0, x_item)
            self._table.setItem(row_index, 1, y_item)


class ReferenceValueBlock(QFrame):
    """The "Reference" role label beside its read-only value row: a flat
    washed value box, an optional unit label (mirroring the main editor's
    own, for the kinds that show one), and a quiet "Copy up" text button."""

    #: Emitted when "Copy up" is clicked. Purely informational at this
    #: milestone -- the owning card re-exposes it verbatim; nothing wires it
    #: any further yet.
    copy_up_requested = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceBlock")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Must equal ParameterCard's editor-row spacing: the two rows share
        # the fixed label column, and equal spacing is what lines the value
        # columns up.
        layout.setSpacing(style.ROLE_ROW_SPACING)

        self._heading = QLabel("Reference")
        self._heading.setObjectName("ReferenceFileHeading")
        self._heading.setFixedWidth(style.ROLE_LABEL_WIDTH)
        layout.addWidget(self._heading, 0, Qt.AlignTop)

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

        self._copy_up = QPushButton("Copy up")
        self._copy_up.setObjectName("CopyUpButton")
        self._copy_up.setCursor(Qt.PointingHandCursor)
        self._copy_up.clicked.connect(self.copy_up_requested)
        row.addWidget(self._copy_up, 0, Qt.AlignTop)

        # Zero-stretch spacer: inert while the (stretch-1) value box may grow,
        # but when the box is capped (*narrow*) it soaks up the slack so the
        # button sits right after the value instead of at the row's far edge.
        row.addStretch(0)

        layout.addLayout(row, 1)

    def set_content(
        self,
        value_text: str,
        unit: str,
        same_as_main: bool,
        *,
        width: int | None = None,
        monospace: bool = False,
    ) -> None:
        """Show the reference's *value_text* (and *unit*, if any) as the
        one-line/plain-text row, replacing any table grid the box may have
        been showing (:meth:`set_table_rows`).

        *same_as_main* (an EQUAL row) appends " · same" and renders the value
        in the faint "same" style rather than the loud one, and hides
        "Copy up" -- there is nothing to copy. An empty *unit* hides the unit
        label entirely, the same as the main editor's own unit label.

        *width* mirrors the main editor's input width
        (:meth:`~.base.EditorCard.reference_value_width`): a capped main
        input caps this box at the same width, so the two values align
        exactly; ``None`` (a series, an expression, a table preview) keeps
        the full row.

        *monospace* is set for a full function/expression string -- shown in
        full, word-wrapped and multiline-preserved, in the app's fixed-pitch
        convention rather than the ordinary proportional one.
        """
        self._table_grid.hide()
        self._value.show()
        self._value_box.setMaximumWidth(width if width is not None else _NO_MAX_WIDTH)
        self._value.setText(f"{value_text} · same" if same_as_main else value_text)
        self._value.setFont(_monospace_font() if monospace else self._default_font)
        self._value.setProperty("same", same_as_main)
        self._value.style().unpolish(self._value)
        self._value.style().polish(self._value)
        self._unit_label.setText(unit)
        self._unit_label.setVisible(bool(unit))
        # Hidden, not disabled: an EQUAL row has nothing to copy, and a
        # greyed button would still claim visual weight beside the value.
        # Disabled too, so the guard holds even if something clicks it
        # programmatically.
        self._copy_up.setEnabled(not same_as_main)
        self._copy_up.setVisible(not same_as_main)

    def set_table_rows(self, rows: list[list[object]], matches: list[bool]) -> None:
        """Show a differing, table-representable reference as a read-only
        grid instead of the one-line summary (:meth:`set_content`).

        Only ever called for a non-EQUAL row -- ``ParameterCard`` keeps the
        compact one-liner for an EQUAL table -- so "Copy up" always stays
        shown and enabled here; there is no *narrow*/unit affordance,
        matching the main table editor's own kind, which shows neither.
        """
        self._value.hide()
        self._value_box.setMaximumWidth(_NO_MAX_WIDTH)
        self._table_grid.set_rows(rows, matches)
        self._table_grid.show()
        self._unit_label.setText("")
        self._unit_label.hide()
        self._copy_up.setEnabled(True)
        self._copy_up.setVisible(True)
