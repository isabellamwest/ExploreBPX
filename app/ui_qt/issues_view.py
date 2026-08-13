"""Issues section body: the parameter-scoped issue list inside the
Inspector's Issues section.

The Issues section (a :class:`~ui_qt.group_box.TintedSection` the Inspector
owns) appears only while the shown parameter has issues, so unlike the old
tab this list carries no placeholder state -- when there is nothing to
show, the whole section is hidden. The list hugs its own rows
(:class:`~ui_qt.content_sized_list.ContentSizedList`) and scrolls with the
Inspector's page, never inside itself.

Data contract:
  - show_issues(issues, path) is the sole inbound data path and returns the
    merged row count; an empty *issues* just clears the list.
  - issue_activated(tuple) is emitted on double-click or Enter/Return
    activation for navigation.
  - No document-wide or BPX schema logic lives here.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QListWidgetItem, QSizePolicy, QVBoxLayout, QWidget

from core.validation import Severity, input_fact, merge_union_pair

from . import parameter_row, style
from .content_sized_list import ContentSizedList
from .parameter_row import ParameterRowDelegate

_PATH_ROLE = 256  # Qt.UserRole


class IssuesView(QWidget):
    """Lists validation issues for the currently shown parameter."""

    issue_activated = Signal(tuple)  # parameter path tuple

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("IssuesView")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._list = ContentSizedList()
        self._list.setObjectName("IssuesList")
        self._list.setFrameShape(QFrame.NoFrame)
        self._list.setWordWrap(True)
        self._list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        # A hugging list has no space of its own to scroll within -- any
        # overflow is reachable via the Inspector page's own scrolling.
        self._list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        # Paint each row's HTML_ROLE fragment (a coloured severity tag + the
        # verbatim message) so this list reads identically to the Validation
        # page's Issues section.
        self._list.setItemDelegate(ParameterRowDelegate(self._list))
        # itemActivated fires on Enter/Return and double-click, so a single
        # connection covers keyboard and mouse activation without duplicate
        # emits. Selection changes alone (arrow keys) do not trigger it.
        self._list.itemActivated.connect(self._on_activated)
        layout.addWidget(self._list)

    def show_issues(self, issues, path: tuple[str, ...] | None) -> int:
        """Rebuild the list for *issues* and return the merged row count.

        *path* is the owning parameter's path, carried on every row for
        activation; ``None`` (no parameter shown) only ever arrives with no
        issues. A committed-null ``FloatInt`` value's ``float_type``+
        ``int_type`` pair (V5) displays as one merged row; the returned
        count (used for the Issues section's header count) follows the
        same merge.
        """
        self._list.clear()
        merged = merge_union_pair(issues)
        for issue in merged:
            is_error = issue.severity == Severity.ERROR
            label = "ERROR" if is_error else "WARN"
            # The offending value, when the validator captured a real number
            # -- see core.validation.input_fact's own fidelity rule. *merged*
            # has already collapsed a FloatInt union pair to one diagnostic,
            # so this never fires twice for one underlying problem.
            fact = input_fact(issue)
            message = f"{issue.message} · {fact}" if fact else issue.message
            item = QListWidgetItem(f"[{label}] {message}")
            # Same treatment as the Diagnostics page's issue rows: a
            # delegate-painted severity icon (SEVERITY_ROLE) plus the muted
            # verbatim message; the location slot stays empty -- this list is
            # already scoped to one parameter.
            item.setData(
                parameter_row.HTML_ROLE,
                parameter_row.compose_issue_row_html("", issue.message, fact),
            )
            item.setData(parameter_row.SEVERITY_ROLE, "error" if is_error else "warning")
            item.setToolTip(style.severity_tooltip(issue.severity))
            item.setData(_PATH_ROLE, path)
            self._list.addItem(item)
        # ContentSizedList's sizeHint changed with the rows; tell the layout.
        self._list.updateGeometry()
        self.updateGeometry()
        return len(merged)

    def reset(self) -> None:
        self.show_issues((), None)

    def _on_activated(self, item: QListWidgetItem) -> None:
        self.issue_activated.emit(item.data(_PATH_ROLE))
