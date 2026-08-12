"""ValidationEmptyState: guided empty state for a zero-run Validation section.

Shown by the Inspector's ``reveal()`` when the user selects the bare
``("Validation",)`` container node and it currently has zero runs, instead of
falling through to the generic "nothing to inspect" placeholder. With at
least one run, selecting the container is unchanged
(``show_placeholder()`` still applies): this widget is only ever a substitute
for the placeholder in the one genuinely-empty case, never a
populated-container view (out of scope: the separate, unchanged absent-section
case).

Both actions below are ready-made :class:`~core.commands.Command` objects
handed to the Inspector's existing ``bulk_commit_requested`` /
``_on_bulk_commit`` seam -- the same one every card's CSV import and
``ExperimentCard``'s "+ Temperature [K]" already use -- so this widget needs
no new plumbing in ``MainWindow`` or the Inspector beyond the ordinary "any
card may hand over a Command" contract:

* **"+ Add experiment"** -- one ``AddSection`` under ``("Validation",)``,
  named via a :class:`~.name_popup.NamePopup` (the same popup class, and the
  same one-field/Enter-confirms/Escape-cancels behaviour, the tree's own
  "Add experiment…" context-menu entry uses -- see ``tree_panel.py``'s
  ``_open_add_named``). One undo step.

* **"Import CSV as new experiment…"** -- file pick, then the same name
  prompt, then the CSV mapping dialog, and only once that is confirmed does
  anything get written: first the ``AddSection`` (the named run), then a
  ``SetValues`` filling its mapped columns -- deliberately two undo steps,
  so undoing the import keeps the named empty run. The
  mapping dialog always runs *before* either command is emitted: once the
  first command lands, the Inspector may rebuild this widget's content out
  from under it (exactly like any other card's commit), so nothing here may
  open a further modal dialog on ``self`` after that point.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core.commands import AddSection, SetValues
from core.csv_import import CsvData, read_csv_file

from .cards.csv_dialog import CsvImportDialog
from .cards.experiment import KNOWN_ALIASES
from .cards.page import GUTTER
from .name_popup import NamePopup
from .style import ERROR, MUTED
from . import typography

_HEADING = "No experiments yet"
_COPY = (
    "Validation stores measured traces (time, current, voltage, "
    "optionally temperature) to check this parameter set against."
)


class ValidationEmptyState(QWidget):
    """Guided empty state for a Validation section with zero runs."""

    #: See the module docstring: a ready-made Command for the Inspector's
    #: existing _on_bulk_commit to execute as one undo step. Emitted
    #: once for "+ Add experiment", twice (in sequence) for the CSV flow.
    bulk_commit_requested = Signal(object)

    #: Never dirty: unlike a card, this widget holds no editable draft, so
    #: the Inspector's undo guard (has_focused_draft, which checks
    #: card.is_dirty on whatever _card currently is) always reads it
    #: as having nothing to lose.
    is_dirty = False

    def __init__(self) -> None:
        super().__init__()

        # No layout-level AlignCenter: it would shrink each child to its
        # preferred size, and a word-wrapped QLabel's preferred height
        # under-estimates, clipping the last line on screen. Labels span the
        # widget and centre their text; the buttons centre themselves below.
        layout = QVBoxLayout(self)
        # The Inspector pane no longer carries margins of its own (structured-
        # page layout), so this full-pane empty state supplies the shared
        # gutter itself, plus headroom in place of a page header.
        layout.setContentsMargins(GUTTER, 24, GUTTER, 16)
        layout.setSpacing(8)

        heading = QLabel(_HEADING)
        heading.setObjectName("CardTitle")
        heading.setAlignment(Qt.AlignCenter)
        heading.setWordWrap(True)
        layout.addWidget(heading)

        copy = QLabel(_COPY)
        copy.setObjectName("ValidationEmptyStateCopy")
        copy.setWordWrap(True)
        copy.setAlignment(Qt.AlignCenter)
        copy.setStyleSheet(f"color: {MUTED};")
        layout.addWidget(copy)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addStretch(1)
        self._add_button = QPushButton("+ Add experiment")
        self._add_button.setObjectName("ValidationEmptyStateAdd")
        self._add_button.clicked.connect(self._open_add_experiment_popup)
        actions.addWidget(self._add_button)

        self._import_button = QPushButton("Import CSV…")
        self._import_button.setObjectName("ValidationEmptyStateImport")
        self._import_button.clicked.connect(self._import_csv_as_new_experiment)
        actions.addWidget(self._import_button)
        actions.addStretch(1)
        layout.addLayout(actions)

        # Import feedback (same role as ExperimentCard's CsvImportMessage):
        # an unreadable file or a zero-row parse must say so, not silently
        # do nothing. Cleared on the next import attempt.
        self._import_message = QLabel("")
        self._import_message.setObjectName("CsvImportMessage")
        self._import_message.setWordWrap(True)
        self._import_message.setAlignment(Qt.AlignCenter)
        self._import_message.setStyleSheet(
            f"color: {ERROR}; {typography.size_qss(typography.META)}"
        )
        self._import_message.hide()
        layout.addWidget(self._import_message)

        # One popup, one pending intent -- mirrors tree_panel.TreePanel's own
        # _popup_intent convention: None means the plain "+ Add
        # experiment" click; a (CsvData, filename) pair means the CSV flow is
        # waiting on a name before it can run the mapping dialog (see
        # _on_name_chosen).
        self._popup = NamePopup(self)
        self._popup.name_chosen.connect(self._on_name_chosen)
        self._pending_import: tuple[CsvData, str] | None = None

    # ------------------------------------------------------------------
    # "+ Add experiment": one AddSection undo step
    # ------------------------------------------------------------------

    def _open_add_experiment_popup(self) -> None:
        self._pending_import = None
        self._open_name_popup(self._add_button)

    def _open_name_popup(self, anchor_button) -> None:
        # A brand-new Validation section always has zero runs here (this
        # widget only ever shows for that case -- see the module docstring),
        # so there is no sibling name to collide with.
        self._popup.open_at(
            anchor_button.mapToGlobal(anchor_button.rect().bottomLeft()),
            "New experiment name…",
        )

    def _on_name_chosen(self, name: str) -> None:
        pending, self._pending_import = self._pending_import, None
        if pending is None:
            self.bulk_commit_requested.emit(AddSection(("Validation",), name))
            return
        data, filename = pending
        self._prompt_csv_mapping_then_create(data, filename, name)

    # ------------------------------------------------------------------
    # "Import CSV as new experiment…": file -> name -> mapping -> fill
    # ------------------------------------------------------------------

    def _import_csv_as_new_experiment(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Import CSV",
            "",
            "CSV files (*.csv *.tsv *.txt);;All files (*)",
        )
        if not path:
            return
        self._show_import_message("")
        try:
            data = read_csv_file(path)
        except OSError as exc:
            self._show_import_message(f"Could not read {Path(path).name}: {exc}")
            return
        if data.row_count == 0:
            self._show_import_message(f"{Path(path).name} has no data rows to import.")
            return
        self._pending_import = (data, Path(path).name)
        self._open_name_popup(self._import_button)

    def _show_import_message(self, message: str) -> None:
        self._import_message.setText(message)
        self._import_message.setVisible(bool(message))

    def _prompt_csv_mapping_then_create(
        self, data: CsvData, filename: str, name: str
    ) -> None:
        """Confirm the mapping, then write both commands back to back.

        The dialog runs first, while self is still guaranteed to be the
        live widget the Inspector is showing (nothing has been committed
        yet) -- see the module docstring for why that ordering matters. A
        cancelled mapping is a clean no-op: neither command fires, so
        nothing is created at all, matching every other CSV import's
        "nothing is written until confirmed" contract.
        """
        dialog = CsvImportDialog(data, KNOWN_ALIASES, self, filename=filename)
        dialog.exec()
        if dialog.accepted_mapping is None:
            return

        self.bulk_commit_requested.emit(AddSection(("Validation",), name))

        targets = tuple(("Validation", name, alias) for alias in KNOWN_ALIASES)
        updates = tuple(
            (targets[index], list(data.columns[column]))
            for index, column in enumerate(dialog.accepted_mapping)
            if column is not None
        )
        if updates:
            self.bulk_commit_requested.emit(SetValues(updates, label="Import CSV"))
