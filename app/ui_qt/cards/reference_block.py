"""ReferenceLedger: the card's reference section for N pinned references
(multi-reference track, design rule 3), shared by ``ParameterCard`` (see
``ParameterCard.set_reference_groups``) and ``GhostParameterCard`` -- one
widget so the two can never drift apart.

One row per distinct reference value: references sharing a value group into
a single row (``core.compare.group_reference_values``), whose badge cluster
stacks every member's badge in pin order. The cluster sits in the fixed
role-label column (``style.ROLE_LABEL_WIDTH``, shared with
``ParameterCard``'s own "Main" label) so every reference value starts at
the same x as the main editor and the eye compares values vertically. The
only words a row ever adds are the design's two: a muted "same" when the
group's value equals the main document's, or a quiet "Pull" button when it
differs. A reference lacking the key contributes nothing -- no row (and
the MAIN_ONLY case is filtered before specs are built).

Rows are plain ``QLabel``s and a button, rebuilt wholesale on every
``set_rows`` -- deliberately outside any editor's draft/commit machinery
(known Qt pitfall), and wholesale so no Pull connection can outlive the
pin list that created it. The owning card prepares one
:class:`LedgerRowSpec` per group (the ledger renders, it never classifies
values or reads comparisons itself).

For a differing, table-representable value the one-line summary gives way
to :class:`ReferenceTableGrid` -- a small read-only x/y grid in the same
washed box. For a ``str`` expression, the box shows the full text rather
than the truncated one-line preview every other kind uses -- both cases in
the app's monospace convention (:func:`typography.mono`), not a fresh font
choice.
"""

from __future__ import annotations

from dataclasses import dataclass

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
from ..reference_identity import ReferencePin, badge_label

#: "No maximum": Qt's QWIDGETSIZE_MAX, restored when the row is not narrow.
_NO_MAX_WIDTH = 16777215

#: Data rows shown before ``ReferenceTableGrid`` scrolls -- a compact glance,
#: not a second full editor.
_VISIBLE_ROWS = 6


def _monospace_font():
    return typography.mono()


class ReferenceTableGrid(QWidget):
    """A read-only ``x``/``y`` grid of a differing reference table's rows.

    Shown inside a ledger row's washed value box in place of the one-line
    ``table · N points`` summary, once the group's value is
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


@dataclass(frozen=True)
class LedgerRowSpec:
    """Everything one ledger row renders, prepared by the owning card.

    ``table`` is ``(rows, matches)`` for a differing table-representable
    group -- shown as a :class:`ReferenceTableGrid` in place of ``text`` --
    or ``None`` for the one-line form. ``group`` is the opaque payload
    (:class:`core.compare.ValueGroup`) handed back verbatim through
    ``pull_requested``; the ledger never reads it.
    """

    pins: tuple[ReferencePin, ...]
    text: str
    monospace: bool
    same: bool
    unit: str
    width: int | None
    table: tuple[list[list[object]], list[bool]] | None
    group: object


class _LedgerRow(QFrame):
    """One value group's row: badge cluster, value, and "same" or Pull.

    The built widgets are kept as attributes (``spec``, ``_value``,
    ``_grid``, ``_unit_label``, ``_same_label``, ``_pull`` -- absent parts
    ``None``) purely as the headless test driver's read seam; nothing in
    the app reads them back.
    """

    pull_requested = Signal()

    def __init__(self, spec: LedgerRowSpec) -> None:
        super().__init__()
        self.setObjectName("ReferenceLedgerRow")
        self.spec = spec
        self._value: QLabel | None = None
        self._grid: ReferenceTableGrid | None = None
        self._unit_label: QLabel | None = None
        self._same_label: QLabel | None = None
        self._pull: QPushButton | None = None
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        # Must equal ParameterCard's editor-row spacing: the cluster shares
        # the fixed label column, and equal spacing is what lines the value
        # columns up.
        layout.setSpacing(style.ROLE_ROW_SPACING)

        cluster = QWidget()
        cluster.setObjectName("ReferenceLedgerCluster")
        cluster_layout = QHBoxLayout(cluster)
        cluster_layout.setContentsMargins(0, 0, 0, 0)
        cluster_layout.setSpacing(3)
        for pin in spec.pins:
            cluster_layout.addWidget(badge_label(pin, small=True))
        cluster_layout.addStretch(1)
        # Auto-width cluster: at least the shared label column, growing only
        # if four badges genuinely need more.
        cluster.setMinimumWidth(style.ROLE_LABEL_WIDTH)
        cluster.setToolTip(", ".join(pin.name for pin in spec.pins))
        layout.addWidget(cluster, 0, Qt.AlignTop)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(8)

        value_box = QFrame()
        value_box.setObjectName("ReferenceValueBox")
        box_layout = QHBoxLayout(value_box)
        box_layout.setContentsMargins(8, 4, 8, 4)
        if spec.table is not None:
            self._grid = ReferenceTableGrid()
            self._grid.set_rows(*spec.table)
            box_layout.addWidget(self._grid, 1)
        else:
            self._value = QLabel(spec.text)
            self._value.setObjectName("ReferenceBlockValue")
            self._value.setWordWrap(True)
            if spec.monospace:
                self._value.setFont(_monospace_font())
            self._value.setProperty("same", spec.same)
            box_layout.addWidget(self._value)
            value_box.setMaximumWidth(spec.width if spec.width is not None else _NO_MAX_WIDTH)
        row.addWidget(value_box, 1)

        if spec.table is None and spec.unit:
            self._unit_label = QLabel(spec.unit)
            self._unit_label.setObjectName("ReferenceUnitLabel")
            row.addWidget(self._unit_label)

        if spec.same:
            self._same_label = QLabel("same")
            self._same_label.setObjectName("LedgerSameLabel")
            row.addWidget(self._same_label, 0, Qt.AlignTop)
        else:
            self._pull = QPushButton("Pull")
            self._pull.setObjectName("LedgerPullButton")
            self._pull.setCursor(Qt.PointingHandCursor)
            self._pull.clicked.connect(self.pull_requested)
            row.addWidget(self._pull, 0, Qt.AlignTop)

        # Zero-stretch spacer: inert while the (stretch-1) value box may grow,
        # but when the box is capped (*narrow*) it soaks up the slack so the
        # action sits right after the value instead of at the row's far edge.
        row.addStretch(0)

        layout.addLayout(row, 1)


class ReferenceLedger(QFrame):
    """The rows column -- see the module docstring."""

    #: Emitted with the clicked row's ``group`` payload. The owning card
    #: re-exposes it; ``InspectorPanel`` turns it into a source-named
    #: ``PullParameter``.
    pull_requested = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ReferenceLedger")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._rows: list[_LedgerRow] = []

    def set_rows(self, specs: list[LedgerRowSpec]) -> None:
        """Rebuild the ledger's rows wholesale from *specs* (one per value
        group, in first-pinned order)."""
        for row in self._rows:
            self._layout.removeWidget(row)
            # Hidden before deleteLater: a removed widget keeps painting at
            # its old geometry until deferred deletion runs.
            row.hide()
            row.deleteLater()
        self._rows = []
        for spec in specs:
            row = _LedgerRow(spec)
            row.pull_requested.connect(
                lambda group=spec.group: self.pull_requested.emit(group)
            )
            self._layout.addWidget(row)
            self._rows.append(row)
