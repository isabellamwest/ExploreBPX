"""Issues drawer: compact top-right panel for the selected parameter's issues.

The drawer has two states:
  - Collapsed: a compact toggle button at the top-right showing the issue count.
  - Expanded: the toggle button plus a scrollable issue list below it.

Data contract:
  - show_parameter(parameter) is the sole inbound data path.
  - reset() is called when a new document is opened.
  - issue_activated(tuple) is emitted on double-click for navigation.
  - No document-wide or BPX schema logic lives here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QListWidget,
    QListWidgetItem,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from core.tree_model import ParameterItem
from core.validation import Severity

BUTTON_WIDTH = 90
EXPANDED_WIDTH = 280


class IssuesDrawer(QWidget):
    """Collapsible right-edge drawer showing issues for the selected parameter."""

    issue_activated = Signal(tuple)  # parameter path tuple

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("IssuesDrawer")
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._expanded = False
        self._user_dismissed = False
        self._prev_path: tuple[str, ...] | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.setAlignment(Qt.AlignTop)

        # Toggle button: always visible at the top-right.
        self._toggle_btn = QToolButton()
        self._toggle_btn.setObjectName("IssuesToggle")
        self._toggle_btn.setText("Issues")
        self._toggle_btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._toggle_btn.clicked.connect(self._on_toggle)
        layout.addWidget(self._toggle_btn)

        # Issue list: shown only when expanded.
        self._list = QListWidget()
        self._list.setObjectName("IssuesList")
        self._list.itemDoubleClicked.connect(self._on_activated)
        layout.addWidget(self._list)

        self._set_expanded(False)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show_parameter(self, parameter: ParameterItem | None) -> None:
        """Show issues for *parameter*.  Clears and collapses when None."""
        current_path = parameter.path if parameter is not None else None
        # Reset dismissed state whenever the selected parameter changes.
        if current_path != self._prev_path:
            self._user_dismissed = False
            self._prev_path = current_path

        self._list.clear()
        count = 0
        if parameter is not None:
            for issue in parameter.issues:
                prefix = "ERROR" if issue.severity == Severity.ERROR else "WARN"
                item = QListWidgetItem(f"[{prefix}] {issue.message}")
                item.setData(256, issue.path)
                self._list.addItem(item)
            count = len(parameter.issues)

        self._toggle_btn.setText(f"Issues ({count})" if count else "Issues")

        # Auto-expand when the parameter has issues and user hasn't dismissed;
        # collapse when there are no issues or no parameter is selected.
        if count > 0 and not self._user_dismissed:
            self._set_expanded(True)
        elif count == 0:
            self._set_expanded(False)

    def reset(self) -> None:
        """Called when a new document is opened; clears all state."""
        self._prev_path = None
        self._user_dismissed = False
        self._toggle_btn.setText("Issues")
        self._list.clear()
        self._set_expanded(False)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_toggle(self) -> None:
        new_state = not self._expanded
        self._user_dismissed = not new_state
        self._set_expanded(new_state)

    def _set_expanded(self, expanded: bool) -> None:
        self._expanded = expanded
        self._list.setVisible(expanded)
        self.setFixedWidth(EXPANDED_WIDTH if expanded else BUTTON_WIDTH)

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.issue_activated.emit(item.data(256))
