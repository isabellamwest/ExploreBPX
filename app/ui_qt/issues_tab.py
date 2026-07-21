"""Issues tab: the parameter-scoped issue list shown inside the Inspector's
secondary workspace.

Data contract:
  - show_parameter(parameter) is the sole inbound data path; None clears it.
  - issue_activated(tuple) is emitted on double-click or Enter/Return
    activation for navigation.
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
from core.validation import Severity, merge_union_pair

from . import parameter_row, style
from .parameter_row import ParameterRowDelegate

_PATH_ROLE = 256  # Qt.UserRole

_MSG_NO_SELECTION = "Select a parameter to view its issues."
_MSG_NO_ISSUES = style.all_clear("No validation issues for this parameter.")


def issue_count(issues) -> int:
    """The number of rows :meth:`IssuesTab.show_parameter` would render for
    *issues* -- i.e. the merged count (decision Q), after collapsing a
    committed-null ``FloatInt``'s ``float_type``+``int_type`` pair (V5) to
    one displayed row.

    The single source of truth for "how many rows does this tab show": any
    caller that sets the secondary-workspace tab badge for an issues list
    that did *not* go through :meth:`show_parameter` itself (e.g. Inspector's
    live-preview and Escape-revert paths) MUST route the count through this
    function rather than ``len(issues)`` -- a real defect (M1, reviewed): two
    call-sites in ``inspector.py`` pushed the unmerged length into the same
    badge, so the badge and the list disagreed for a committed-null FloatInt
    parameter. Keeping one function used by both the list-builder and every
    badge-setter is what makes that drift impossible to reintroduce.
    """
    return len(merge_union_pair(issues))


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
        self._list.setWordWrap(True)
        # Paint each row's HTML_ROLE fragment (a coloured severity tag + the
        # verbatim message) so this tab reads identically to the Validation
        # page's Issues section.
        self._list.setItemDelegate(ParameterRowDelegate(self._list))
        # itemActivated fires on Enter/Return and double-click, so a single
        # connection covers keyboard and mouse activation without duplicate
        # emits. Selection changes alone (arrow keys) do not trigger it.
        self._list.itemActivated.connect(self._on_activated)
        self._stack.addWidget(self._list)  # index 0 - issue list

        self._placeholder = QLabel(_MSG_NO_SELECTION)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # index 1 - empty state

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)  # start on the placeholder

    def show_parameter(self, parameter: ParameterItem | None) -> int:
        """Populate the list for *parameter* and return the issue count.

        Switches to the placeholder when *parameter* is None or has no issues,
        so the panel always explains its state rather than showing a blank area.
        A committed-null ``FloatInt`` value's ``float_type``+``int_type`` pair
        (V5) displays as one merged row (decision Q); the returned count
        (used for the secondary-workspace tab badge) follows the same merge.
        """
        self._list.clear()
        if parameter is None:
            self._placeholder.setText(_MSG_NO_SELECTION)
            self._stack.setCurrentIndex(1)
            return 0

        merged = merge_union_pair(parameter.issues)
        for issue in merged:
            is_error = issue.severity == Severity.ERROR
            label = "ERROR" if is_error else "WARN"
            item = QListWidgetItem(f"[{label}] {issue.message}")
            # Same treatment as the Diagnostics page's issue rows (F5): a
            # delegate-painted severity icon (SEVERITY_ROLE) plus the muted
            # verbatim message; the location slot stays empty -- this tab is
            # already scoped to one parameter.
            item.setData(
                parameter_row.HTML_ROLE,
                parameter_row.compose_issue_row_html("", issue.message),
            )
            item.setData(parameter_row.SEVERITY_ROLE, "error" if is_error else "warning")
            item.setToolTip(style.severity_tooltip(issue.severity))
            item.setData(_PATH_ROLE, parameter.path)
            self._list.addItem(item)

        count = issue_count(parameter.issues)  # same function every badge-setter must use
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
