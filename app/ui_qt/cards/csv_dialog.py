"""CSV import dialog: route file columns to parameters, then confirm.

Nothing is written until the user confirms here, and the mapping is **always**
shown -- a wrong auto-detection must be visible and correctable, never silently
imported. The dialog presents what the parser made of the file (delimiter,
header row, cells kept as text), one selector per target parameter proposing
the auto-mapped column, and a preview of the file itself. Import is blocked --
with the reason spelled out -- while the mapping is unusable (no column chosen,
or one column routed to two parameters).
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from ..style import ERROR, MUTED
from .csv_import import CsvData, auto_map
from .values import format_value

#: Rows shown in the preview; the parse itself is complete (same convention as
#: the paste preview).
_PREVIEW_ROWS = 100

#: The combo entry meaning "leave this parameter untouched".
_SKIP = "— skip —"


class CsvImportDialog(QDialog):
    """Modal mapping + preview for a :class:`CsvData`, returning a mapping."""

    def __init__(
        self,
        data: CsvData,
        targets: tuple[str, ...],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Import CSV")
        self._data = data
        self._targets = targets
        self._accepted_mapping: tuple[int | None, ...] | None = None

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

        # One selector per target, preselected from the auto-map. The names
        # come straight from the file (or a positional "Column N"); nothing
        # is guessed invisibly.
        proposed = auto_map(data, targets)
        form = QFormLayout()
        self._combos: list[QComboBox] = []
        column_names = [data.column_name(i) for i in range(data.column_count)]
        for target, guess in zip(targets, proposed):
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

        buttons = QDialogButtonBox()
        self._import_button = QPushButton("Import")
        self._import_button.setDefault(True)
        buttons.addButton(self._import_button, QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        self._import_button.clicked.connect(self._choose)
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

    def _blocked_reason(self) -> str | None:
        chosen = [column for column in self.mapping() if column is not None]
        if not chosen:
            return "Choose a column for at least one parameter."
        if len(set(chosen)) != len(chosen):
            return "Each column can fill only one parameter."
        return None

    def _refresh_gate(self, *_args) -> None:
        reason = self._blocked_reason()
        self._import_button.setEnabled(reason is None)
        self._reason.setVisible(reason is not None)
        self._reason.setText(reason or "")

    def _choose(self) -> None:
        if self._blocked_reason() is not None:
            return
        self._accepted_mapping = self.mapping()
        self.accept()


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
    for column_index, column in enumerate(data.columns):
        for row_index in range(shown):
            value = column[row_index]
            item = QTableWidgetItem(format_value(value))
            item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
            # Flag a non-numeric (kept-as-text) cell so the user spots it.
            if value is not None and not isinstance(value, (int, float)):
                item.setForeground(Qt.red)
            table.setItem(row_index, column_index, item)
    table.setMaximumHeight(260)
    return table
