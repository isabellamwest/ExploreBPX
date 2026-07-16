"""ExperimentCard: the unified editor for one BPX Validation run.

A Validation run (``Validation/<run>``) is not one parameter -- it is a small
group of co-located ``SERIES`` arrays (``Time [s]``, ``Current [A]``,
``Voltage [V]``, optionally ``Temperature [K]``) that only make sense read and
edited together (a row is one sample of the experiment). This card replaces
the four separate per-array ``SeriesCard``s the Inspector used to open one at
a time -- ``SeriesCard`` itself is unchanged and still exists (``cards/series.py``),
but the Inspector's routing (``inspector.py``) no longer reaches it for
anything under a Validation run; this card takes over instead.

Keyed on the run's own object node (a :class:`~core.tree_model.TreeNode`), not
on a single :class:`~core.tree_model.ParameterItem`: every column is a
first-class value in its own right, so there is no one "the parameter" for
this card to wrap. This is why it does not subclass ``EditorCard`` (whose
whole contract -- ``parameter``, ``value()``, one committed original -- is
shaped around exactly one parameter); it re-implements the small slice of
that contract (Enter commits, Escape reverts) that still applies, adapted to
several independently-dirty columns.

**Commit path.** All columns are always editable (decision D1a); a navigated-
to array only changes which column starts focused. Enter compares every
column's current grid contents against its own committed baseline and commits
*only the ones that changed* as one :class:`~core.commands.SetValues` --
named ``bulk_commit_requested``, the same signal (and the same
``InspectorPanel._on_bulk_commit`` handler) every other card's multi-parameter
commit (CSV import) already uses. A typed single-cell edit therefore commits
exactly one path; editing two columns before pressing Enter commits both, in
one undo step.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.commands import AddParameter, SetValues
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode

from .cell_issues import experiment_cells
from .csv_dialog import CsvImportDialog
from .csv_import import read_csv_file
from .grid import MultiColumnGrid
from .values import values_equal

#: The known Experiment array aliases, in ``bpx.schema.Experiment``'s own
#: field order. Time/Current/Voltage are schema-required; Temperature alone
#: is declared optional (confirmed against ``bpx.schema`` -- its ``Field``
#: default is ``None``, the other three have none), which is why it is the
#: only column offered a "+" affordance below.
KNOWN_ALIASES = ("Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]")

#: The sole optional column -- see ``KNOWN_ALIASES``.
_OPTIONAL_ALIAS = "Temperature [K]"


def is_validation_run_path(path: tuple[str, ...]) -> bool:
    """Whether *path* names a Validation run's own object node.

    Mirrors the exact predicate ``core.tree_model._seed_sibling_series`` uses
    to find a run node (``len(path) == 2 and path[0] == "Validation"``) and
    ``core.structure.can_rename``'s Validation branch. Defined once here --
    core is closed to this phase, and ``structure.py`` has no single-purpose
    helper for it yet -- and reused by both this card and the Inspector's
    routing, rather than inlined a third time.
    """
    return len(path) == 2 and path[0] == "Validation"


class ExperimentCard(QWidget):
    """Edits every array of one Validation run in one multi-column grid."""

    #: Emitted with a ready-made :class:`core.commands.Command` (a
    #: ``SetValues`` for an edit/CSV import, an ``AddParameter`` for
    #: "+ Temperature [K]") for the Inspector's existing
    #: ``_on_bulk_commit`` to execute as one undo step -- see the module
    #: docstring.
    bulk_commit_requested = Signal(object)

    def __init__(
        self,
        run: TreeNode,
        focused_alias: str | None = None,
        read_only: bool = False,
    ) -> None:
        super().__init__()
        self.run_path = tuple(run.path)
        self._read_only = read_only

        by_alias = {
            parameter.label: parameter
            for parameter in run.parameters
            if parameter.kind is ParameterKind.SERIES
        }
        #: The run's known columns, present-only, in schema order.
        self._columns: list[ParameterItem] = [
            by_alias[alias] for alias in KNOWN_ALIASES if alias in by_alias
        ]
        #: Snapshot of each column's committed value, normalised to the grid's
        #: own display shape -- also the reference :meth:`_dirty_updates`
        #: diffs a draft against, so an untouched column (even one whose real
        #: stored value is malformed, e.g. a string) is never mistaken for an
        #: edit merely because the grid renders it as empty.
        self._originals: list[list[object]] = [
            self._baseline(parameter.value) for parameter in self._columns
        ]

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        header = QHBoxLayout()
        self._title = QLabel(f"Experiment · {run.label}")
        self._title.setObjectName("CardTitle")
        header.addWidget(self._title)
        header.addStretch(1)
        self._import_button = None
        if not read_only:
            self._import_button = QToolButton()
            self._import_button.setText("Import CSV…")
            self._import_button.setToolTip(
                "Fill this run's arrays from the columns of a CSV file"
            )
            self._import_button.setAutoRaise(True)
            self._import_button.clicked.connect(self._import_csv)
            header.addWidget(self._import_button)
        layout.addLayout(header)

        headers = tuple(parameter.label for parameter in self._columns)
        self._grid = MultiColumnGrid(headers, read_only=read_only)
        for index, values in enumerate(self._originals):
            self._grid.set_column_values(index, values)
        self._grid.set_cell_issues(experiment_cells(self._all_issues(), headers))
        layout.addWidget(self._grid, 1)

        # "+ Temperature [K]" only while it is genuinely absent: present-but-
        # malformed still counts as present, so this never offers to add a
        # column that already exists.
        self._add_temperature_button = None
        if not read_only and _OPTIONAL_ALIAS not in by_alias:
            self._add_temperature_button = QToolButton()
            self._add_temperature_button.setText(f"+ {_OPTIONAL_ALIAS}")
            self._add_temperature_button.setToolTip(
                f"Add an empty {_OPTIONAL_ALIAS} column to this run"
            )
            self._add_temperature_button.setAutoRaise(True)
            self._add_temperature_button.clicked.connect(self._add_temperature_column)
            self._grid.add_toolbar_widget(self._add_temperature_button)

        # A run-level diagnostic (attached to the run's own node rather than
        # to one column -- see ``core.document._attach_issues``'s ancestor
        # fallback) shown as a quiet chip. Never computed here: today's
        # ``bpx.schema.Experiment`` has no cross-array length check at all
        # (verified against the schema), so this chip is wired but will stay
        # silent unless/until bpx actually reports something at the run
        # level -- "no diagnostic, no chip", kept honest rather than
        # inventing the check ourselves.
        self._chip = None
        chip_text = self._run_level_message(run)
        if chip_text:
            self._chip = QLabel(chip_text)
            self._chip.setObjectName("LengthMismatchChip")
            self._chip.setWordWrap(True)
            self._grid.add_toolbar_widget(self._chip)

        # Focus the resolved column, if any -- a bare run-node reveal
        # (``focused_alias is None``) leaves the grid's default focus alone
        # (decision D1a). All columns stay editable regardless.
        if focused_alias in headers:
            self._grid.focus_column(headers.index(focused_alias))

        self._install_keyboard_handler(self._grid.focus_widget())

    # ------------------------------------------------------------------
    # Keyboard contract: Enter commits, Escape reverts (see module docstring)
    # ------------------------------------------------------------------

    def _install_keyboard_handler(self, widget: QWidget) -> None:
        widget.installEventFilter(self)

    def eventFilter(self, obj, event) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self._commit_dirty_columns()
                return True
            if key == Qt.Key_Escape:
                self._revert()
                return True
        return super().eventFilter(obj, event)

    def _commit_dirty_columns(self) -> None:
        updates = self._dirty_updates()
        if not updates:
            return  # no-op Enter: nothing actually changed
        self.bulk_commit_requested.emit(SetValues(updates, label="Edit experiment"))

    def _revert(self) -> None:
        for index, original in enumerate(self._originals):
            self._grid.set_column_values(index, original)

    # ------------------------------------------------------------------
    # Dirty tracking: per-column, diffed against each column's own baseline
    # ------------------------------------------------------------------

    @property
    def is_dirty(self) -> bool:
        """Whether any column's draft differs from its committed baseline.

        Used by the Inspector's undo guard (``has_focused_draft``), exactly
        like every other card's ``is_dirty``.
        """
        return bool(self._dirty_updates())

    def _dirty_updates(self) -> tuple[tuple[tuple[str, ...], object], ...]:
        updates = []
        for index, parameter in enumerate(self._columns):
            current = self._grid.column_values(index)
            if not self._columns_equal(current, self._originals[index]):
                updates.append((parameter.path, current))
        return tuple(updates)

    @staticmethod
    def _columns_equal(a: list, b: list) -> bool:
        return len(a) == len(b) and all(values_equal(x, y) for x, y in zip(a, b))

    @staticmethod
    def _baseline(value: object) -> list:
        """The grid-displayable form of a column's committed value: a real
        list verbatim, or an empty list for ``None``/anything else -- the
        same "no value here yet" convention ``SeriesCard._rows`` uses,
        generalised to any non-list value so a malformed stored value never
        blocks the column from opening (see the constructor's docstring)."""
        return list(value) if isinstance(value, list) else []

    def _all_issues(self) -> list:
        issues: list = []
        for parameter in self._columns:
            issues.extend(parameter.issues)
        return issues

    @staticmethod
    def _run_level_message(run: TreeNode) -> str | None:
        messages = list(dict.fromkeys(
            issue.message for issue in run.issues if getattr(issue, "message", "")
        ))
        return "; ".join(messages) if messages else None

    # ------------------------------------------------------------------
    # "+ Temperature [K]"
    # ------------------------------------------------------------------

    def _add_temperature_column(self) -> None:
        """Add the optional column with an empty array, via the same
        ``AddParameter`` command the parameter list's "fields to add" group
        uses (``_on_add_parameter_requested``) -- reached here through
        ``bulk_commit_requested`` since that handler accepts any ``Command``,
        not only a ``SetValues``.
        """
        self.bulk_commit_requested.emit(AddParameter(self.run_path, _OPTIONAL_ALIAS, []))

    # ------------------------------------------------------------------
    # CSV import -- carries over SeriesCard's pipeline (series.py), targeting
    # every column this card owns instead of one array plus its siblings.
    # ------------------------------------------------------------------

    def _csv_targets(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        return tuple((parameter.label, parameter.path) for parameter in self._columns)

    def _import_csv(self) -> None:
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
        targets = self._csv_targets()
        dialog = CsvImportDialog(data, tuple(label for label, _ in targets), self)
        dialog.exec()
        if dialog.accepted_mapping is not None:
            self._apply_csv_import(data, dialog.accepted_mapping)

    def _apply_csv_import(self, data, mapping: tuple[int | None, ...]) -> None:
        """Turn a confirmed *mapping* into one atomic ``SetValues`` commit --
        see ``SeriesCard._apply_csv_import``: an unmapped target is not
        touched, never blanked."""
        updates = tuple(
            (path, list(data.columns[column]))
            for (_, path), column in zip(self._csv_targets(), mapping)
            if column is not None
        )
        if updates:
            self.bulk_commit_requested.emit(SetValues(updates, label="Import CSV"))
