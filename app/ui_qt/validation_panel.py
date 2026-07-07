"""Validation tab: all issues; double-click or Enter/Return jumps to the owning
parameter."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QVBoxLayout, QWidget

from core.document import BPXDocument
from core.validation import Severity


class ValidationPanel(QWidget):
    """Lists issues; emits a parameter path to navigate to on activation."""

    issue_activated = Signal(tuple)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._list = QListWidget()
        # itemActivated fires on Enter/Return and double-click, so a single
        # connection covers keyboard and mouse activation without duplicate
        # emits. Selection changes alone (arrow keys) do not trigger it.
        self._list.itemActivated.connect(self._on_activated)
        layout.addWidget(self._list)

    def refresh(self, document: BPXDocument | None) -> None:
        self._list.clear()
        if document is None:
            return
        for issue, nav_path in document.iter_issues():
            prefix = "ERROR" if issue.severity == Severity.ERROR else "WARN"
            loc_str = " → ".join(nav_path) if nav_path else "(document)"
            item = QListWidgetItem(f"[{prefix}] {loc_str}: {issue.message}")
            item.setData(256, nav_path)
            self._list.addItem(item)

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.issue_activated.emit(item.data(256))
