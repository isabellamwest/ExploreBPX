"""Validation tab: all issues; double-click or Enter/Return jumps to the owning
parameter."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core.document import BPXDocument
from core.validation import Severity

_MSG_NO_DOCUMENT = "No document open"
_MSG_NO_ISSUES = "✓ No issues"


class ValidationPanel(QWidget):
    """Lists issues; emits a parameter path to navigate to on activation.

    Shows an explanatory placeholder instead of a blank list both when there
    is no document and when a loaded document has no issues, mirroring the
    Inspector's Issues tab (see ``issues_tab.py``).
    """

    issue_activated = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._list = QListWidget()
        # itemActivated fires on Enter/Return and double-click, so a single
        # connection covers keyboard and mouse activation without duplicate
        # emits. Selection changes alone (arrow keys) do not trigger it.
        self._list.itemActivated.connect(self._on_activated)
        self._stack.addWidget(self._list)  # index 0 — issue list

        self._placeholder = QLabel(_MSG_NO_DOCUMENT)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # index 1 — empty state

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)  # start on the placeholder

    def refresh(self, document: BPXDocument | None) -> None:
        self._list.clear()
        if document is None:
            self._placeholder.setText(_MSG_NO_DOCUMENT)
            self._stack.setCurrentIndex(1)
            return
        for issue, nav_path in document.iter_issues():
            prefix = "ERROR" if issue.severity == Severity.ERROR else "WARN"
            loc_str = " → ".join(nav_path) if nav_path else "(document)"
            item = QListWidgetItem(f"[{prefix}] {loc_str}: {issue.message}")
            item.setData(256, nav_path)
            self._list.addItem(item)
        if self._list.count() == 0:
            self._placeholder.setText(_MSG_NO_ISSUES)
            self._stack.setCurrentIndex(1)
        else:
            self._stack.setCurrentIndex(0)

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.issue_activated.emit(item.data(256))
