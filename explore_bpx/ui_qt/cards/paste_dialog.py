"""Paste preview: confirm parsed clipboard data before it touches the grid.

Nothing is written until the user confirms here. The dialog shows exactly what
the parser made of the clipboard -- the detected delimiter, whether a header row
was skipped, how many cells were kept as text rather than coerced, and the
parsed grid itself -- then offers to *replace* the grid's contents or *append*
to them. This is the safety step for the app's "never silently coerce or
discard" rule: a value the parser could not read as a number is shown in place
(kept as text), never zero-filled, and the user sees it before committing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from explore_bpx.core.values import format_value
from explore_bpx.ui_qt.style import ERROR, MUTED, TABLE_PREVIEW_MAX_HEIGHT

if TYPE_CHECKING:
    from explore_bpx.core.paste import ParsedPaste

#: Rows shown in the preview before it notes "and N more". The parse itself is
#: complete; only the preview is capped, so a thousand-row paste stays instant.
_PREVIEW_ROWS = 100


class PastePreviewResult:
    """The user's choice from the dialog."""

    REPLACE = "replace"
    APPEND = "append"


class PastePreviewDialog(QDialog):
    """Modal preview of a :class:`ParsedPaste`, returning replace/append/cancel."""

    def __init__(self, parsed: ParsedPaste, headers: tuple[str, ...], parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paste preview")
        self.setMinimumWidth(520)
        self._choice: str | None = None

        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(_summary(parsed), objectName="Heading"))

        detail = QLabel(_detail(parsed))
        detail.setStyleSheet(f"color: {MUTED};")
        detail.setWordWrap(True)
        layout.addWidget(detail)

        layout.addWidget(_preview_table(parsed, headers))

        if parsed.row_count > _PREVIEW_ROWS:
            more = QLabel(f"Showing the first {_PREVIEW_ROWS} of {parsed.row_count} rows.")
            more.setStyleSheet(f"color: {MUTED};")
            more.setWordWrap(True)
            layout.addWidget(more)

        buttons = QDialogButtonBox()
        replace = QPushButton("Replace all")
        append = QPushButton("Append")
        replace.setDefault(True)
        buttons.addButton(replace, QDialogButtonBox.AcceptRole)
        buttons.addButton(append, QDialogButtonBox.AcceptRole)
        buttons.addButton(QDialogButtonBox.Cancel)
        replace.clicked.connect(lambda: self._choose(PastePreviewResult.REPLACE))
        append.clicked.connect(lambda: self._choose(PastePreviewResult.APPEND))
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Nothing to add means Append would be a no-op; guide toward Replace.
        append.setEnabled(parsed.row_count > 0)
        replace.setEnabled(parsed.row_count > 0)

    def _choose(self, choice: str) -> None:
        self._choice = choice
        self.accept()

    @property
    def choice(self) -> str | None:
        """``PastePreviewResult.REPLACE`` / ``.APPEND``, or ``None`` if cancelled."""
        return self._choice


def _summary(parsed: ParsedPaste) -> str:
    if parsed.row_count == 0:
        return "Nothing to paste"
    return f"{parsed.row_count} row{'s' if parsed.row_count != 1 else ''} parsed"


def _detail(parsed: ParsedPaste) -> str:
    parts = [f"delimiter: {parsed.delimiter}"]
    if parsed.header is not None:
        parts.append(f'header row skipped: "{parsed.header}"')
    if parsed.rejected:
        parts.append(f"{parsed.rejected} cell{'s' if parsed.rejected != 1 else ''} kept as text (not a number)")
    if parsed.dropped_columns:
        parts.append(f"{parsed.dropped_columns} extra column-value(s) dropped")
    return " · ".join(parts)


def _preview_table(parsed: ParsedPaste, headers: tuple[str, ...]) -> QTableWidget:
    shown = parsed.rows[:_PREVIEW_ROWS]
    table = QTableWidget(len(shown), len(headers))
    table.setHorizontalHeaderLabels(list(headers))
    table.setEditTriggers(QTableWidget.NoEditTriggers)
    table.setSelectionMode(QTableWidget.NoSelection)
    # Columns stretch to fill the width, matching the NumericGrid this
    # preview feeds into.
    table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
    for r, row in enumerate(shown):
        for c in range(len(headers)):
            value = row[c] if c < len(row) else None
            item = QTableWidgetItem(format_value(value))
            item.setTextAlignment(int(Qt.AlignRight | Qt.AlignVCenter))
            # Flag a non-numeric (kept-as-text) cell so the user spots it.
            if value is not None and not isinstance(value, (int, float)):
                item.setForeground(QColor(ERROR))
            table.setItem(r, c, item)
    table.setMaximumHeight(TABLE_PREVIEW_MAX_HEIGHT)
    return table
