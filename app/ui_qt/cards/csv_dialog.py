"""CSV import dialog: route file columns to parameters, then confirm.

Nothing is written until the user confirms here, and the mapping is **always**
shown -- a wrong auto-detection must be visible and correctable, never silently
imported. The dialog presents what the parser made of the file (delimiter,
header row, cells kept as text), one selector per target parameter proposing
a mapping, and a preview of the file itself. Import is blocked -- with the
reason spelled out -- while the mapping is unusable.

Three optional parameters let a second caller (the x/y table grid) reuse this
same dialog without changing the series import's behaviour, which is the
default in every case:

* ``proposed`` overrides the auto-mapped proposal (the table passes
  :func:`~.csv_import.positional_map`, since ``auto_map``'s substring rule is
  unsafe for one-letter targets like "x"/"y").
* ``require_all_targets`` tightens the gate from "at least one column chosen"
  to "every target mapped". A series import deliberately leaves an unmapped
  array untouched -- skipping a column is a valid, partial import. A table's
  two columns are *one value*, so a half-mapped import would blank the other
  column: that is data loss, not a skip, so it is required.
* ``offer_append`` adds Replace/Append buttons and an ``accepted_mode``
  (reusing :class:`~.paste_dialog.PastePreviewResult`), for a caller that
  writes into an existing grid rather than only ever filling parameters fresh.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from core.csv_import import CsvData, auto_map
from core.values import format_value

from ..style import ERROR, MUTED
from .paste_dialog import PastePreviewResult

#: Rows shown in the preview; the parse itself is complete (same convention as
#: the paste preview).
_PREVIEW_ROWS = 100

#: The combo entry meaning "leave this target untouched".
_SKIP = "(skip)"


class CsvImportDialog(QDialog):
    """Modal mapping + preview for a :class:`CsvData`, returning a mapping."""

    def __init__(
        self,
        data: CsvData,
        targets: tuple[str, ...],
        parent=None,
        *,
        proposed: tuple[int | None, ...] | None = None,
        require_all_targets: bool = False,
        offer_append: bool = False,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._data = data
        self._targets = targets
        self._require_all_targets = require_all_targets
        self._offer_append = offer_append
        self._accepted_mapping: tuple[int | None, ...] | None = None
        self._accepted_mode: str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f"{data.row_count} row{'s' if data.row_count != 1 else ''} · "
                f"{data.column_count} column{'s' if data.column_count != 1 else ''}",
                objectName="Heading",
            )
        )
        detail = QLabel(_detail(data))
        detail.setStyleSheet(f"color: {MUTED};")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        # One selector per target, preselected from the proposal -- the
        # auto-map, or an explicit override (the table's positional_map). The
        # names come straight from the file (or a positional "Column N");
        # nothing is guessed invisibly.
        proposal = proposed if proposed is not None else auto_map(data, targets)
        form = QFormLayout()
        self._combos: list[QComboBox] = []
        column_names = [data.column_name(i) for i in range(data.column_count)]
        for target, guess in zip(targets, proposal):
            combo = QComboBox()
            combo.addItem(_SKIP)
            combo.addItems(column_names)
            combo.setCurrentIndex(0 if guess is None else guess + 1)
            combo.currentIndexChanged.connect(self._refresh_gate)
            self._combos.append(combo)
            form.addRow(f"{target}:", combo)
        layout.addLayout(form)

        layout.addWidget(_preview_table(data))
        if data.row_count > _PREVIEW_ROWS:
            more = QLabel(f"Showing the first {_PREVIEW_ROWS} of {data.row_count} rows.")
            more.setStyleSheet(f"color: {MUTED};")
            layout.addWidget(more)

        # Why Import is blocked, when it is. Same convention as a card's
        # commit gate: refuse and explain, never guess.
        self._reason = QLabel("")
        self._reason.setStyleSheet(f"color: {ERROR};")
        self._reason.setWordWrap(True)
        self._reason.hide()
        layout.addWidget(self._reason)

        # Import is one plain button by default (the series path, byte-
        # identical to before); a caller that also wants to choose between
        # replacing and appending gets two buttons instead, both gated the
        # same way.
        buttons = QDialogButtonBox()
        if self._offer_append:
            self._import_button = QPushButton("Replace")
            append_button = QPushButton("Append")
            self._import_button.setDefault(True)
            buttons.addButton(self._import_button, QDialogButtonBox.AcceptRole)
            buttons.addButton(append_button, QDialogButtonBox.AcceptRole)
            self._import_button.clicked.connect(
                lambda: self._choose(PastePreviewResult.REPLACE)
            )
            append_button.clicked.connect(lambda: self._choose(PastePreviewResult.APPEND))
            self._confirm_buttons = [self._import_button, append_button]
        else:
            self._import_button = QPushButton("Import")
            self._import_button.setDefault(True)
            buttons.addButton(self._import_button, QDialogButtonBox.AcceptRole)
            # A lambda, not ``self._choose`` directly: PySide6 passes the
            # button's own ``clicked(checked=False)`` argument straight through
            # to a bare-connected slot, which would make ``accepted_mode`` read
            # ``False`` instead of ``None`` -- matching the two Replace/Append
            # lambdas above.
            self._import_button.clicked.connect(lambda: self._choose())
            self._confirm_buttons = [self._import_button]
        buttons.addButton(QDialogButtonBox.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_gate()

    # ------------------------------------------------------------------

    def mapping(self) -> tuple[int | None, ...]:
        """The current per-target column choice (``None`` = skip)."""
        return tuple(
            combo.currentIndex() - 1 if combo.currentIndex() > 0 else None
            for combo in self._combos
        )

    @property
    def accepted_mapping(self) -> tuple[int | None, ...] | None:
        """The confirmed mapping, or ``None`` if the dialog was cancelled."""
        return self._accepted_mapping

    @property
    def accepted_mode(self) -> str | None:
        """``PastePreviewResult.REPLACE``/``.APPEND`` when ``offer_append`` is
        set and the dialog was confirmed; ``None`` otherwise (including a
        caller that never offered the choice, and a cancelled dialog)."""
        return self._accepted_mode

    def _blocked_reason(self) -> str | None:
        chosen = [column for column in self.mapping() if column is not None]
        if self._require_all_targets and len(chosen) < len(self._targets):
            if self._data.column_count < len(self._targets):
                # Naming a column to choose is not actionable when the file
                # simply does not have enough of them -- say what is actually
                # wrong instead.
                count = self._data.column_count
                return (
                    f"This file has {count} column{'s' if count != 1 else ''}; "
                    f"{_join_targets(self._targets)} each need one."
                )
            return f"Choose a column for {_join_targets(self._targets)}."
        # "Field", not "parameter": the form rows are labelled with whatever
        # aliases the caller targets (array names for an Experiment run,
        # parameter names elsewhere), so the generic word has to cover both.
        if not self._require_all_targets and not chosen:
            return "Choose a column for at least one field."
        if len(set(chosen)) != len(chosen):
            return "Each column can fill only one field."
        return None

    def _refresh_gate(self, *_args) -> None:
        reason = self._blocked_reason()
        for button in self._confirm_buttons:
            button.setEnabled(reason is None)
        self._reason.setVisible(reason is not None)
        self._reason.setText(reason or "")

    def _choose(self, mode: str | None = None) -> None:
        if self._blocked_reason() is not None:
            return
        self._accepted_mapping = self.mapping()
        self._accepted_mode = mode
        self.accept()


def _join_targets(targets: tuple[str, ...]) -> str:
    """"x" -> "x"; ("x", "y") -> "x and y"; more targets get an Oxford list."""
    if len(targets) <= 1:
        return ", ".join(targets)
    return f"{', '.join(targets[:-1])} and {targets[-1]}"


def _detail(data: CsvData) -> str:
    parts = [f"delimiter: {data.delimiter}"]
    parts.append(
        "column names from the file's header row"
        if data.headers is not None
        else "no header row: columns are numbered"
    )
    if data.rejected:
        parts.append(
            f"{data.rejected} cell{'s' if data.rejected != 1 else ''} kept as text "
            "(not a number)"
        )
    return " · ".join(parts)


def _preview_table(data: CsvData) -> QTableWidget:
    shown = min(data.row_count, _PREVIEW_ROWS)
    table = QTableWidget(shown, data.column_count)
    table.setHorizontalHeaderLabels(
        [data.column_name(i) for i in range(data.column_count)]
    )
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionMode(QTableWidget.NoSelection)
    # Columns stretch to fill the width, matching the NumericGrid this
    # preview feeds into.
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for column_index, column in enumerate(data.columns):
        for row_index in range(shown):
            value = column[row_index]
            item = QTableWidgetItem(format_value(value))
            item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            # Flag a non-numeric (kept-as-text) cell so the user spots it.
            if value is not None and not isinstance(value, (int, float)):
                item.setForeground(QColor(ERROR))
            table.setItem(row_index, column_index, item)
    table.setMaximumHeight(260)
    return table
