"""Issues tab: the parameter-scoped issue list shown inside the Inspector's
secondary workspace.

Data contract:
  - show_parameter(parameter) is the sole inbound data path; None clears it.
  - issue_activated(tuple) is emitted on double-click for navigation.
  - No document-wide or BPX schema logic lives here.
"""

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

from core.tree_model import ParameterItem
from core.validation import Severity

_PATH_ROLE = 256  # Qt.UserRole

_MSG_NO_SELECTION = "Select a parameter to view its issues."
_MSG_NO_ISSUES = "\u2713\u2002No validation issues for this parameter."


class IssuesTab(QWidget):
    """Lists validation issues for the currently selected parameter.

    When no issues are present the tab shows an explanatory placeholder rather
    than an empty area, so the panel always communicates its state.
    """

    issue_activated = Signal(tuple)  # parameter path tuple

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("IssuesTab")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._list = QListWidget()
        self._list.setObjectName("IssuesList")
        self._list.itemDoubleClicked.connect(self._on_activated)
        self._stack.addWidget(self._list)  # index 0 — issue list

        self._placeholder = QLabel(_MSG_NO_SELECTION)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # index 1 — empty state

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)  # start on the placeholder

    def show_parameter(self, parameter: ParameterItem | None) -> int:
        """Populate the list for *parameter* and return the issue count.

        Switches to the placeholder when *parameter* is None or has no issues,
        so the panel always explains its state rather than showing a blank area.
        """
        self._list.clear()
        if parameter is None:
            self._placeholder.setText(_MSG_NO_SELECTION)
            self._stack.setCurrentIndex(1)
            return 0

        for issue in parameter.issues:
            prefix = "ERROR" if issue.severity == Severity.ERROR else "WARN"
            item = QListWidgetItem(f"[{prefix}] {issue.message}")
            item.setData(_PATH_ROLE, parameter.path)
            self._list.addItem(item)

        count = len(parameter.issues)
        if count:
            self._stack.setCurrentIndex(0)
        else:
            self._placeholder.setText(_MSG_NO_ISSUES)
            self._stack.setCurrentIndex(1)
        return count

    def reset(self) -> None:
        self.show_parameter(None)

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.issue_activated.emit(item.data(_PATH_ROLE))
