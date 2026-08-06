"""ReferenceLedger: the card's per-reference value rows.

Shared by ``ParameterCard`` (its reference section; see
``ParameterCard.set_reference``) and ``GhostParameterCard`` (which shows it
unconditionally, for a key no reference-free main document has) -- one
widget so the two can never drift apart.

**One row per distinct reference value.** Pinned references whose value at
this key is identical share a single row, their badges stacked in a
cluster (``core.compare.group_reference_values`` decides the grouping -- the
UI paints, it never decides equality). The cluster is its own auto-width
column, so four badges never push the value column out of alignment with
the main editor's input above; the value column itself starts at the same x
as that input (``style.ROLE_LABEL_WIDTH``), so the eye compares vertically.

A row says exactly one thing beyond its value: **same** when the value
equals the main document's, or a **Pull** button when it differs. Pull's
presence *is* the differs signal -- there is no third word, no severity
colour, and no styling that could read as validation. A reference lacking
the key contributes no row at all rather than an empty placeholder.

For a differing, table-representable reference the rows are followed by
:class:`ReferenceTableGrid` -- a small read-only x/y grid of the
first-pinned reference that has the key, labelled with that pin's badge so
it is never ambiguous whose numbers are on screen. (Phase 2 of the
multi-reference track turns that label into a selector over every pin.)

Plain ``QLabel``s and buttons only -- deliberately outside any editor's
draft/commit machinery (known Qt pitfall): populating this can never trip
``_touched``, since it wires no signal into an editor at all.
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

from core.compare import ValueGroup
from core.values import format_value

from .. import badges, style, typography
from ..reference_identity import ReferencePin

#: "No maximum": Qt's QWIDGETSIZE_MAX, restored when the row is not narrow.
_NO_MAX_WIDTH = 16777215

#: Data rows shown before ``ReferenceTableGrid`` scrolls -- a compact glance,
#: not a second full editor.
_VISIBLE_ROWS = 6


def _monospace_font():
    return typography.mono()


class ReferenceTableGrid(QWidget):
    """A read-only ``x``/``y`` grid of a differing reference table's rows.

    Shown beneath the ledger rows once a reference is table-representable and
    does not equal main (:meth:`ReferenceLedger.set_table_rows`). A row that
    has no exactly-matching ``(x, y)`` pair in the main draft -- see
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


class _LedgerRow(QWidget):
    """One distinct reference value: its badge cluster, the value, and either
    "same" or a Pull button."""

    #: Emitted with the *first-pinned* index in this row's group. First
    #: pinned, not "the one clicked": the row is one value shared by several
    #: references, and the earliest pin is the stable, explainable name for
    #: it in the undo entry.
    pull_requested = Signal(int)

    def __init__(
        self,
        group: ValueGroup,
        pins: list[ReferencePin],
        value_text: str,
        *,
        width: int | None = None,
        monospace: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("LedgerRow")
        self._source_index = group.indices[0]

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Must equal ParameterCard's editor-row spacing: the rows share the
        # fixed label column, and equal spacing is what lines the value
        # columns up.
        layout.setSpacing(style.ROLE_ROW_SPACING)

        cluster = QWidget()
        cluster.setObjectName("LedgerBadgeCluster")
        cluster_layout = QHBoxLayout(cluster)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(2)
        for index in group.indices:
            pin = pins[index]
            cluster_layout.addWidget(
                badges.make_reference_badge(pin.letters, pin.colour, pin.name)
            )
        # The cluster owns at least the label column's width so a one-badge
        # row and a four-badge row start their value at the same x -- and
        # that x is the main editor's own.
        cluster.setMinimumWidth(style.ROLE_LABEL_WIDTH)
        layout.addWidget(cluster, 0, Qt.AlignTop)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        self._value_box = QFrame()
        self._value_box.setObjectName("ReferenceValueBox")
        box_layout = QHBoxLayout(self._value_box)
        box_layout.setContentsMargins(8, 4, 8, 4)
        self._value = QLabel(value_text)
        self._value.setObjectName("ReferenceBlockValue")
        self._value.setWordWrap(True)
        if monospace:
            self._value.setFont(_monospace_font())
        self._value.setProperty("same", group.equals_main)
        box_layout.addWidget(self._value)
        self._value_box.setMaximumWidth(width if width is not None else _NO_MAX_WIDTH)
        row.addWidget(self._value_box, 1)

        if group.equals_main:
            # One quiet word. Not a tick, not a colour: "same" is the whole
            # of what there is to say, and a mark here would compete with
            # the validity language everywhere else in the app.
            same = QLabel("same")
            same.setObjectName("LedgerSameLabel")
            row.addWidget(same, 0, Qt.AlignTop)
        else:
            pull = QPushButton("Pull")
            pull.setObjectName("PullButton")
            pull.setCursor(Qt.PointingHandCursor)
            pull.setToolTip(f"Pull this value from {pins[self._source_index].name}")
            pull.clicked.connect(self._emit_pull)
            row.addWidget(pull, 0, Qt.AlignTop)

        # Zero-stretch spacer: inert while the (stretch-1) value box may grow,
        # but when the box is capped (*width*) it soaks up the slack so the
        # button sits right after the value instead of at the row's far edge.
        row.addStretch(0)
        layout.addLayout(row, 1)

    def _emit_pull(self) -> None:
        self.pull_requested.emit(self._source_index)


class ReferenceLedger(QFrame):
    """The card's reference section: one row per distinct reference value,
    optionally followed by a table grid."""

    #: Emitted with the first-pinned index of whichever row's Pull was
    #: clicked. The owning card re-exposes it verbatim.
    pull_requested = Signal(int)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceLedger")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(2)

        self._rows: list[_LedgerRow] = []

        self._grid_caption = QWidget()
        caption_layout = QHBoxLayout(self._grid_caption)
        caption_layout.setContentsMargins(0, 6, 0, 2)
        caption_layout.setSpacing(6)
        self._grid_badge_slot = QHBoxLayout()
        self._grid_badge_slot.setContentsMargins(0, 0, 0, 0)
        caption_layout.addLayout(self._grid_badge_slot)
        caption_label = QLabel("Reference values")
        caption_label.setObjectName("LedgerGridCaption")
        caption_layout.addWidget(caption_label)
        caption_layout.addStretch(1)
        self._grid_caption.hide()
        self._layout.addWidget(self._grid_caption)

        self._table_grid = ReferenceTableGrid()
        self._table_grid.hide()
        self._layout.addWidget(self._table_grid)

    def set_rows(
        self,
        groups: tuple[ValueGroup, ...],
        pins: list[ReferencePin],
        value_texts: list[str],
        *,
        width: int | None = None,
        monospace: bool = False,
    ) -> None:
        """Rebuild the ledger's value rows.

        *value_texts* is positional against *groups* -- the caller formats
        each group's value, since only it knows the parameter's kind. Rows
        are rebuilt wholesale rather than updated in place: pin order decides
        every badge, so a removal has to re-derive the rows or one would keep
        a stale Pull connection and a stale identity.
        """
        for row in self._rows:
            self._layout.removeWidget(row)
            row.setParent(None)
            row.deleteLater()
        self._rows = []

        for position, group in enumerate(groups):
            row = _LedgerRow(
                group,
                pins,
                value_texts[position],
                width=width,
                monospace=monospace,
            )
            row.pull_requested.connect(self.pull_requested)
            self._rows.append(row)
            self._layout.insertWidget(position, row)

    def set_table_rows(
        self,
        rows: list[list[object]],
        matches: list[bool],
        pin: ReferencePin | None,
    ) -> None:
        """Show *pin*'s table beneath the rows, badge-labelled so it is never
        ambiguous whose numbers these are. ``None`` hides the grid."""
        for index in reversed(range(self._grid_badge_slot.count())):
            item = self._grid_badge_slot.takeAt(index)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        if pin is None:
            self._grid_caption.hide()
            self._table_grid.hide()
            return
        self._grid_badge_slot.addWidget(
            badges.make_reference_badge(pin.letters, pin.colour, pin.name)
        )
        self._table_grid.set_rows(rows, matches)
        self._grid_caption.show()
        self._table_grid.show()
