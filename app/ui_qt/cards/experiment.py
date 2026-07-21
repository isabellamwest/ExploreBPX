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

from pathlib import Path

from PySide6.QtCore import QEvent, QMimeData, Qt, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import expected_fields
from core.commands import AddParameter, SetValues
from core.csv_import import read_csv_file
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from core.values import values_equal

from ..style import MUTED
from .cell_issues import experiment_cells
from .csv_dialog import CsvImportDialog
from .database_examples_dialog import DatabaseExamplesDialog
from .grid import MultiColumnGrid

#: The Experiment array aliases in the schema's own field order, derived
#: live through the gateway (every Validation run is typed ``Experiment``,
#: so any run-name path resolves it) rather than restated here.
_EXPERIMENT_FIELDS = expected_fields(("Validation", "<run>"))

KNOWN_ALIASES = tuple(f.alias for f in _EXPERIMENT_FIELDS)

#: The sole schema-optional column (currently ``Temperature [K]``), the only
#: one offered a "+" affordance below. This card's layout assumes exactly one
#: such column; :mod:`tests.test_spec_literals_contract` pins that soleness.
_OPTIONAL_ALIAS = next(f.alias for f in _EXPERIMENT_FIELDS if not f.required)


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


def _short_alias(alias: str) -> str:
    """"Time [s]" -> "Time" -- the unit-stripped name the sample-count
    footer chip uses (see :meth:`ExperimentCard._sample_count_text`)."""
    return alias.split(" [")[0]


#: Extensions the CSV pipeline actually reads (matches the ``QFileDialog``
#: filter this card and ``_CsvDropzone`` both use), so a drag-and-drop only
#: ever accepts a file the pipeline can do something with.
_CSV_EXTENSIONS = (".csv", ".tsv", ".txt")


def _first_csv_file(mime_data: QMimeData) -> Path | None:
    """The first local file in *mime_data* with a CSV-shaped extension, or
    ``None`` -- same idiom as ``WorkspacePanel``'s own drop filter for BPX
    files, applied to the extensions this card's own CSV import accepts."""
    for url in mime_data.urls():
        if not url.isLocalFile():
            continue
        path = Path(url.toLocalFile())
        if path.suffix.lower() in _CSV_EXTENSIONS:
            return path
    return None


class _CsvDropzone(QFrame):
    """Import-first affordance shown above an empty run's grid (Phase 3).

    One "Upload data…" button on a frame that also accepts a dropped file;
    both funnel into the same file path: this widget's whole job is obtaining
    *a path*, never reading or mapping the file itself -- that stays in
    ``ExperimentCard``'s existing CSV pipeline (``read_csv_file`` ->
    ``auto_map`` -> ``CsvImportDialog`` -> one ``SetValues``), so mapping
    logic lives in exactly one place. Getting data in is this widget's ONLY
    job (redesign 2026-07-20): comparison lives solely behind the card
    toolbar's always-visible "Compare…" button, which handles an empty run
    with a plain notice instead of a second, confusing entry point here.
    """

    #: A file the user picked (Browse) or dropped.
    csv_path_chosen = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("ExperimentDropzone")
        self.setAcceptDrops(True)

        layout = QVBoxLayout(self)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        upload = QPushButton("Upload data…")
        upload.setObjectName("ExperimentDropzoneUpload")
        upload.clicked.connect(self._browse)
        buttons.addWidget(upload)
        buttons.addStretch(1)
        layout.addLayout(buttons)

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CSV",
            "",
            "CSV files (*.csv *.tsv *.txt);;All files (*)",
        )
        if path:
            self.csv_path_chosen.emit(path)

    # --- drag-and-drop --------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if _first_csv_file(event.mimeData()) is not None:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        path = _first_csv_file(event.mimeData())
        if path is None:
            event.ignore()
            return
        event.acceptProposedAction()
        self.csv_path_chosen.emit(str(path))


class ExperimentCard(QWidget):
    """Edits every array of one Validation run in one multi-column grid."""

    #: Emitted with a ready-made :class:`core.commands.Command` (a
    #: ``SetValues`` for an edit/CSV import, an ``AddParameter`` for
    #: "+ Temperature [K]") for the Inspector's existing
    #: ``_on_bulk_commit`` to execute as one undo step -- see the module
    #: docstring.
    bulk_commit_requested = Signal(object)
    #: Forwarded verbatim from the grid's own ``expand_toggled`` (see
    #: ``MultiColumnGrid``), the same contract every other card's grid-
    #: takeover uses (``InspectorPanel._on_card_expanded``).
    expand_toggled = Signal(bool)

    def __init__(
        self,
        run: TreeNode,
        focused_alias: str | None = None,
        read_only: bool = False,
        document_name: str = "",
    ) -> None:
        super().__init__()
        self.run_path = tuple(run.path)
        self._read_only = read_only
        #: The run's own display name (the same value :attr:`_title` is built
        #: from) and the document's file name -- together they label this
        #: run's own series in :meth:`_open_database_examples`.
        self._run_label = run.label
        self._document_name = document_name

        by_alias = {
            parameter.label: parameter
            for parameter in run.parameters
            if parameter.kind is ParameterKind.SERIES
        }
        #: The run's columns, in schema order. The three schema-required
        #: aliases (everything but ``_OPTIONAL_ALIAS``) always get a column,
        #: even when genuinely absent from the raw dict (a brand-new run
        #: added via "+ Add experiment", ``{}``, has none of its four keys
        #: yet) -- :meth:`_placeholder_column` stands in so the grid always
        #: has something to type or import into. Temperature alone stays
        #: behind its own "+" button while absent (see below), unchanged
        #: from Phase 1.
        self._columns: list[ParameterItem] = [
            by_alias[alias]
            if alias in by_alias
            else self._placeholder_column(run, alias)
            for alias in KNOWN_ALIASES
            if alias in by_alias or alias != _OPTIONAL_ALIAS
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
        self._database_examples_button = None
        if not read_only:
            self._database_examples_button = QToolButton()
            self._database_examples_button.setText("Compare…")
            self._database_examples_button.setToolTip(
                "Compare this run's data against sample cells or another BPX file"
            )
            self._database_examples_button.setAutoRaise(True)
            self._database_examples_button.clicked.connect(self._open_database_examples)
            header.addWidget(self._database_examples_button)
        layout.addLayout(header)

        # Import-first entry for a run with nothing typed yet (Phase 3): an
        # upload/drop target above the still-usable empty grid. Disappears
        # the moment any column holds a value -- see
        # :meth:`_refresh_derived_state`, kept live via the grid's own
        # ``changed`` so a typed cell (not only a commit) dismisses it.
        self._dropzone = None
        if not read_only:
            self._dropzone = _CsvDropzone()
            self._dropzone.csv_path_chosen.connect(self._import_csv_from_path)
            layout.addWidget(self._dropzone)

        headers = tuple(parameter.label for parameter in self._columns)
        self._grid = MultiColumnGrid(headers, read_only=read_only)
        for index, values in enumerate(self._originals):
            self._grid.set_column_values(index, values)
        self._grid.set_cell_issues(experiment_cells(self._all_issues(), headers))
        self._grid.changed.connect(self._on_grid_changed)
        self._grid.expand_toggled.connect(self.expand_toggled)
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

        # Per-column sample counts ("Time 120 · Current 120 · Voltage 118"):
        # factual counts only, never a validity judgement -- bpx alone judges
        # whether a mismatch matters (the chip above). Kept live by
        # :meth:`_refresh_derived_state`, the same as the dropzone.
        self._sample_count_chip = QLabel()
        self._sample_count_chip.setObjectName("SampleCountChip")
        self._sample_count_chip.setStyleSheet(f"color: {MUTED};")
        self._grid.add_toolbar_widget(self._sample_count_chip)

        # Focus the resolved column, if any -- a bare run-node reveal
        # (``focused_alias is None``) leaves the grid's default focus alone
        # (decision D1a). All columns stay editable regardless.
        if focused_alias in headers:
            self._grid.focus_column(headers.index(focused_alias))

        self._refresh_derived_state()
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
        # ``set_column_values`` is silent by design (it seeds), so Escape
        # must refresh the dropzone/sample-count chip itself -- the same
        # derived state a real edit updates via ``_on_grid_changed``.
        self._refresh_derived_state()

    # ------------------------------------------------------------------
    # Derived display state: dropzone visibility + sample-count chip
    # ------------------------------------------------------------------

    def _on_grid_changed(self) -> None:
        self._refresh_derived_state()

    def _refresh_derived_state(self) -> None:
        """Recompute the dropzone's visibility and the sample-count chip
        from the grid's *current* draft -- not just the last committed
        baseline -- so a typed first value dismisses the dropzone live,
        without waiting for a commit. (A commit rebuilds this card from
        scratch anyway -- see ``InspectorPanel._show_experiment`` -- which
        re-derives the same state fresh.)
        """
        if self._dropzone is not None:
            empty = all(
                self._grid.column_length(index) == 0
                for index in range(self._grid.column_count)
            )
            self._dropzone.setVisible(empty)
            # The dropzone's "Upload data…" already covers an empty run, so
            # the toolbar's "Import CSV…" only earns its place once there is
            # data to replace. "Compare…" stays put regardless: opened on an
            # empty run, the dialog says so plainly and still shows the
            # reference data (redesign 2026-07-20).
            self._import_button.setVisible(not empty)
        self._sample_count_chip.setText(self._sample_count_text())

    def _sample_count_text(self) -> str:
        """"Time 120 · Current 120 · Voltage 118" -- one entry per column,
        its short alias (see ``_short_alias``) and its current length."""
        parts = (
            f"{_short_alias(parameter.label)} {self._grid.column_length(index)}"
            for index, parameter in enumerate(self._columns)
        )
        return " · ".join(parts)

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

    @staticmethod
    def _placeholder_column(run: TreeNode, alias: str) -> ParameterItem:
        """A stand-in for a schema-required array *alias* not yet present in
        *run* -- see the ``_columns`` construction. ``value=None`` renders
        as an empty column exactly like :meth:`_baseline` already treats any
        non-list value; committing it (a typed cell, or CSV import) writes
        the key for the first time through the ordinary upsert path
        (``SetValues``/``core.editing.set_values``), so nothing here is
        itself a document mutation -- it only lets the grid show a column
        that doesn't exist yet."""
        return ParameterItem(label=alias, path=run.path + (alias,), kind=ParameterKind.SERIES)

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
    # Database examples comparison
    # ------------------------------------------------------------------

    def _own_run_snapshot(self) -> dict[str, list]:
        """The card's current live draft, in :class:`DatabaseExamplesDialog`'s
        "own_run" shape: one entry per column this card actually holds --
        e.g. no ``"Temperature [K]"`` key at all while that column hasn't
        been added yet, exactly as the dialog expects "You" to lack it."""
        return {
            parameter.label: self._grid.column_values(index)
            for index, parameter in enumerate(self._columns)
        }

    def _own_series_label(self) -> str:
        """This run's own series label in the compare dialog: "<file> ·
        <run>", reading like the reference runs rather than "You" (Bella's
        call 2026-07-20). Falls back to "Active file" for an unsaved
        document with no real name yet."""
        stem = Path(self._document_name).stem
        name = stem if stem and stem.lower() != "untitled" else "Active file"
        return f"{name} · {self._run_label}"

    def _open_database_examples(self) -> None:
        dialog = DatabaseExamplesDialog(
            self._own_run_snapshot(),
            self._own_series_label(),
            run_label=self._run_label,
            parent=self,
        )
        dialog.exec()

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
        if path:
            self._import_csv_from_path(path)

    def _import_csv_from_path(self, path: str) -> None:
        """Read, map and (on confirm) apply *path* -- shared by the header's
        "Import CSV…" button and the dropzone (Browse or drop), so a file
        obtained either way runs through exactly one mapping pipeline."""
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
