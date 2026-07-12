"""Series editing card: a one-column grid over a BPX ``list[FloatInt]``.

``SERIES`` is the kind of the four Validation experiment arrays (``Time [s]``,
``Current [A]``, ``Voltage [V]``, ``Temperature [K]``). It has exactly one legal
representation, so the card shows a grid and no mode strip.

The column header is the parameter's label, which already carries the unit
(``Time [s]``), so the grid needs no separate unit affordance.

Inside a Validation run the card also shows the run's *other* arrays as
read-only context columns beside the edited one (seeded on the parameter as
``sibling_series`` by ``core.tree_model``): the arrays are row-aligned samples
of one experiment, so a length mismatch -- the validator error these fields
actually produce -- is visible as trailing phantom rows while editing. Only the
first column is the card's value; ``value()`` never reads the context.
"""

from __future__ import annotations

from PySide6.QtWidgets import QFileDialog, QToolButton, QVBoxLayout

from core.commands import SetValues

from .base import EditorCard
from .csv_dialog import CsvImportDialog
from .csv_import import read_csv_text
from .grid import NumericGrid
from .table_preview import TablePreview


class SeriesCard(EditorCard):
    """Edits a list of numbers as a single grid column, above a live preview."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._preview = TablePreview(mode="series")
        self._preview.set_axis_titles("row", parameter.label)
        layout.addWidget(self._preview)

        # A sibling whose value is not a list has nothing tabular to show;
        # its own card (and the validator) report it, so it is simply absent
        # here rather than rendered as a fabricated column.
        context = tuple(
            (sibling.label, tuple(sibling.value))
            for sibling in parameter.sibling_series
            if isinstance(sibling.value, list)
        )
        self._grid = NumericGrid((parameter.label,), context_columns=context)
        # Populate before wiring ``changed``: seeding must not mark the card
        # touched, or construction alone would make a bare Enter commit.
        self._grid.set_values(self._rows(self._original))
        self._preview.update_rows(self._grid.values())
        self._grid.changed.connect(self._on_grid_changed)
        self._grid.expand_toggled.connect(self.expand_toggled)
        # Stretch factor 1: when the card fills an expanded pane, the grid (not
        # the fixed-height preview) absorbs the extra height.
        layout.addWidget(self._grid, 1)

        # CSV import lives in the expanded (takeover) editor only: it is a
        # bulk operation over the whole run, not a cell-level edit, and the
        # takeover is where the user has the room to review it.
        self._import_button = QToolButton()
        self._import_button.setText("Import CSV…")
        self._import_button.setToolTip(
            "Fill this run's arrays from the columns of a CSV file"
        )
        self._import_button.setAutoRaise(True)
        self._import_button.clicked.connect(self._import_csv)
        self._import_button.hide()
        self._grid.add_toolbar_widget(self._import_button)
        self._grid.expand_toggled.connect(self._import_button.setVisible)

        self._install_keyboard_handler(self._grid.focus_widget())

    def _on_grid_changed(self) -> None:
        self._preview.update_rows(self._grid.values())
        self.draft_changed.emit()

    # ------------------------------------------------------------------
    # CSV import
    # ------------------------------------------------------------------

    def _csv_targets(self) -> tuple[tuple[str, tuple[str, ...]], ...]:
        """The parameters a CSV can fill: this one first, then its siblings.

        First because the resulting ``SetValues`` selects its first path, so
        the user stays on the card they imported from. Siblings come from the
        tree's seeding (a Validation run's other arrays); a lone series simply
        offers one target.
        """
        return ((self.parameter.label, self.parameter.path),) + tuple(
            (sibling.label, sibling.path) for sibling in self.parameter.sibling_series
        )

    def _import_csv(self) -> None:
        """Pick a file, map its columns, and commit the batch atomically."""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CSV",
            "",
            "CSV files (*.csv *.tsv *.txt);;All files (*)",
        )
        if not path:
            return
        # BOM-tolerant; a byte that is not UTF-8 survives as a visible
        # replacement character in the preview rather than aborting the import.
        with open(path, encoding="utf-8-sig", errors="replace") as handle:
            data = read_csv_text(handle.read())
        if data.row_count == 0:
            return
        targets = self._csv_targets()
        dialog = CsvImportDialog(data, tuple(label for label, _ in targets), self)
        dialog.exec()
        if dialog.accepted_mapping is not None:
            self._apply_csv_import(data, dialog.accepted_mapping)

    def _apply_csv_import(self, data, mapping: tuple[int | None, ...]) -> None:
        """Turn a confirmed *mapping* into one atomic ``SetValues`` commit.

        Every mapped target gets its file column verbatim (raw objects, blanks
        as ``None``); an unmapped target is *not touched* -- skipping a column
        must never blank a stored array. The batch is a single command, so the
        whole import is one undo step.
        """
        updates = tuple(
            (path, list(data.columns[column]))
            for (_, path), column in zip(self._csv_targets(), mapping)
            if column is not None
        )
        if updates:
            self.bulk_commit_requested.emit(SetValues(updates, label="Import CSV"))

    @staticmethod
    def _rows(value: object) -> list[list[object]]:
        """One grid row per list item. A ``None`` value is an empty grid.

        A freshly added parameter holds ``None``, the honest "no value". It
        renders as an empty grid, and because an untouched card is never dirty,
        Enter on it commits nothing -- the stored ``null`` survives.
        """
        if value is None:
            return []
        return [[item] for item in value]

    def value(self) -> object:
        """The column's cells verbatim. An empty grid is ``[]``, not ``None``.

        Cells are whatever the user typed: a number, or the raw string of a
        mistyped one, or ``None`` for a blank row. Nothing is coerced -- the
        validator reports the type error.
        """
        return [row[0] for row in self._grid.values()]

    def reset(self) -> None:
        self._grid.set_values(self._rows(self._original))
        self._preview.update_rows(self._grid.values())
