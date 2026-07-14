"""Validation page: two always-present sections, Issues then Outstanding
(completion track Phase 5, decisions E/F/G/L and the pinned UI copy in
``PLAN-completion-track.md``).

``Issues`` shows ``core.completion.partition_issues``'s ``visible`` diagnostics
only -- absorbed diagnostics (decision E) never appear here, so this list and
the rail badge (derived from the same ``PartitionedIssues`` in
``main_window._refresh_all``) can never disagree. ``Outstanding`` shows
``core.completion.document_completion``'s tasks, grouped by owning section in
document order. Each section renders up to two non-activatable subheaders
(decision R): a required group (``"<Section> -- N of M remaining"`` /
``"<Section> -- section absent"``) holding only Required tasks -- so N
always equals the row count beneath it -- followed by a quiet optional
sub-group (``"<Section> · optional -- K unfilled"``) for Expected-but-
optional fields committed null (decision D, revised). Either may be absent
(a section with no optional nulls shows no optional sub-group; one with only
optional nulls shows no required header at all).

Single ``QListWidget``, role-typed rows (mirrors ``parameter_list.py``'s group
idiom): a page-section header, a group subheader, an issue row, a task row, or
a plain message row. Only issue/task rows are selectable, so keyboard
navigation skips every header/message row and Enter on one of them is a
structural no-op rather than a special-cased guard. ``itemActivated`` (Enter/
double-click) is the sole activation path; arrow-key selection alone never
acts -- the same contract ``IssuesTab`` uses.
"""

from __future__ import annotations

import html as _html

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from core import completion
from core.completion import CompletionTask, PartitionedIssues, TaskKind
from core.validation import Severity, merge_union_pair, merge_union_pairs_by_location

from . import parameter_row, style
from .parameter_row import ParameterRowDelegate

_MSG_NO_DOCUMENT = "No document open"
_MSG_NO_ISSUES = "✓ No issues"
_MSG_NOTHING_OUTSTANDING = "✓ Nothing outstanding"
_MSG_PARTIAL_NO_TARGET = (
    "Model is Partial — no completion target. Expected fields are still "
    "suggested in each section's parameter list."
)

_ACTION_GO_TO = "Go to ›"
_ACTION_ADD_SECTION = "+ Add section"
_ACTION_CHOOSE = "Choose…"

#: Item-data roles. 256 is the pre-existing nav-path role "issue" rows carry
#: (kept unchanged so nothing downstream that reads it needs to know this
#: file changed). The rest are new, Phase 5 roles.
_NAV_PATH_ROLE = 256
_KIND_ROLE = Qt.UserRole + 300  # "page_header" | "group_header" | "issue" | "task" | "message"
_TASK_ROLE = Qt.UserRole + 301  # CompletionTask, "task" rows only


def _value_at(raw: dict, path: tuple[str, ...]) -> dict:
    """Read-only nested lookup, defaulting to ``{}`` for any unresolved or
    non-dict segment -- used only to fetch an *existing* group's section value
    for a ``completion_for`` call (never raises, unlike ``core.editing``'s
    mutation-oriented ``_navigate``)."""
    node: object = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return {}
        node = node[key]
    return node if isinstance(node, dict) else {}


def _owning_section(task: CompletionTask) -> tuple[str, ...]:
    """The section a task's Outstanding row groups under.

    A ``MISSING_SECTION`` task names an absent section, so it groups under
    *itself* (a group of exactly one, per decision M). Every other task kind
    names a field inside a section that necessarily exists (fields are only
    ever enumerated for present sections), so it groups under its parent.
    """
    if task.kind is TaskKind.MISSING_SECTION:
        return task.path
    return task.path[:-1]


def _group_outstanding_tasks(
    tasks: tuple[CompletionTask, ...],
) -> list[tuple[tuple[str, ...], list[CompletionTask]]]:
    """Group *tasks* by :func:`_owning_section`, preserving first-appearance
    order (already document order -- ``document_completion`` walks the tree
    in raw dict order, so tasks sharing a section are already contiguous)."""
    groups: dict[tuple[str, ...], list[CompletionTask]] = {}
    order: list[tuple[str, ...]] = []
    for task in tasks:
        key = _owning_section(task)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(task)
    return [(key, groups[key]) for key in order]


def _outstanding_row_text(
    name: str, note: str | None, required: bool, action: str, absorbed_messages: tuple[str, ...] = ()
) -> str:
    label = f"{name} — {note}" if note else name
    tags = (["REQUIRED"] if required else []) + [action]
    text = f"{label}  ({' · '.join(tags)})"
    if absorbed_messages:
        text += "  — " + "; ".join(absorbed_messages)
    return text


def _outstanding_row_html(
    name: str, note: str | None, required: bool, action: str, absorbed_messages: tuple[str, ...] = ()
) -> str:
    """One Outstanding row's rich-text fragment: the bold name (plus an
    "-- note" suffix for a null field), a REQUIRED tag styled exactly like the
    add-parameter popup's (``style.REQUIRED``), the row's own action in
    accent -- decision L: every Outstanding row displays its action -- and,
    when this row absorbed real validator diagnostics, a muted secondary line
    beneath carrying their verbatim messages (decision O: "never remove any
    validation ever" -- absorption re-seats, it never hides). Deliberately
    neutral otherwise (``parameter_row.DEFAULT_TEXT``): red/error styling
    belongs to the Issues section only (terminology discipline, decision B) --
    the secondary text stays muted, never red, so Outstanding stays calm."""
    label = f"{name} — {note}" if note else name
    hints: list[tuple[str, str]] = []
    if required:
        hints.append(("REQUIRED", style.REQUIRED))
    hints.append((action, style.ACCENT))
    fragment = parameter_row.compose_row_html(label, hints, name_color=parameter_row.DEFAULT_TEXT)
    if absorbed_messages:
        secondary = "<br>".join(
            f'<span style="color:{style.MUTED}; font-size:90%;">{_html.escape(message)}</span>'
            for message in absorbed_messages
        )
        fragment += "<br>" + secondary
    return fragment


def _task_row_content(task: CompletionTask, absorbed_messages: tuple[str, ...] = ()) -> tuple[str, str]:
    """Return (plain_text, html) for one Outstanding task row, per decision L
    and the plan's pinned UI copy table.

    The REQUIRED tag reads ``task.required`` -- MISSING_FIELD is always
    Required (decision B), but a NULL_FIELD task may now be optional
    (decision D, revised: any schema-Expected null field is Outstanding, not
    just Required ones), so this must not assume True. MISSING_SECTION/
    DECLARE_MODEL never carry the tag, per the pinned copy table.
    *absorbed_messages* (decision O) renders as muted secondary text under
    the row when this task covers real validator diagnostics.
    """
    if task.kind is TaskKind.MISSING_FIELD:
        return (
            _outstanding_row_text(task.alias, None, task.required, _ACTION_GO_TO, absorbed_messages),
            _outstanding_row_html(task.alias, None, task.required, _ACTION_GO_TO, absorbed_messages),
        )
    if task.kind is TaskKind.NULL_FIELD:
        note = "added, no value yet"
        return (
            _outstanding_row_text(task.alias, note, task.required, _ACTION_GO_TO, absorbed_messages),
            _outstanding_row_html(task.alias, note, task.required, _ACTION_GO_TO, absorbed_messages),
        )
    if task.kind is TaskKind.MISSING_SECTION:
        section_name = task.path[-1]
        return (
            _outstanding_row_text(section_name, None, False, _ACTION_ADD_SECTION, absorbed_messages),
            _outstanding_row_html(section_name, None, False, _ACTION_ADD_SECTION, absorbed_messages),
        )
    return (  # DECLARE_MODEL
        _outstanding_row_text("Declare a model", None, False, _ACTION_CHOOSE, absorbed_messages),
        _outstanding_row_html("Declare a model", None, False, _ACTION_CHOOSE, absorbed_messages),
    )


class ValidationPanel(QWidget):
    """Renders the Validation page's Issues + Outstanding sections; emits a
    parameter path (Issues) or a :class:`CompletionTask` (Outstanding) on
    activation.

    Shows an explanatory placeholder instead of the list only when there is no
    document at all -- once a document is open, both sections (and their own
    empty-state rows) are always present (pinned copy), mirroring the
    Inspector's Issues tab convention of never showing a truly blank area.
    """

    issue_activated = Signal(tuple)
    #: Carries the activated Outstanding row's CompletionTask; the caller
    #: (MainWindow) dispatches by ``task.kind`` (decision L) -- this signal
    #: does not, and cannot, route through NavigationService alone, since a
    #: missing field/section names a target that does not exist yet.
    task_activated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._list = QListWidget()
        self._list.setWordWrap(True)
        # A row with no HTML_ROLE data (page/group headers, plain Issues rows,
        # message rows) falls through to the base QStyledItemDelegate
        # untouched -- only "task" rows carry rich text.
        self._list.setItemDelegate(ParameterRowDelegate(self._list))
        # itemActivated fires on Enter/Return and double-click, so a single
        # connection covers keyboard and mouse activation without duplicate
        # emits. Selection changes alone (arrow keys) do not trigger it, and
        # header/message rows are never selectable at all, so they cannot
        # become "current" for Enter to target.
        self._list.itemActivated.connect(self._on_activated)
        self._stack.addWidget(self._list)  # index 0 -- issue list

        self._placeholder = QLabel(_MSG_NO_DOCUMENT)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # index 1 -- empty state

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)  # start on the placeholder

    def refresh(
        self,
        raw: dict | None,
        model: str | None,
        partition: PartitionedIssues | None,
        tasks: tuple[CompletionTask, ...],
    ) -> None:
        """Rebuild both sections from one derivation point's output.

        *raw*/*model*/*partition*/*tasks* are exactly what
        ``main_window._refresh_all`` computes once per refresh
        (``core.completion.document_completion``/``partition_issues``) and
        also feeds the rail badge, so this panel and the badge can never
        disagree (decision G). *raw*/*model* are used only to look up an
        Outstanding group's ``required_total`` (the "M" in "N of M
        remaining") via ``core.completion.completion_for`` -- no other
        document-wide logic lives here.
        """
        self._list.clear()
        if raw is None:
            self._placeholder.setText(_MSG_NO_DOCUMENT)
            self._stack.setCurrentIndex(1)
            return
        self._add_page_header("Issues")
        self._add_issues_rows(partition)
        self._add_page_header("Outstanding")
        self._add_outstanding_rows(raw, model, tasks, partition)
        self._stack.setCurrentIndex(0)

    # -- Issues ------------------------------------------------------
    def _add_issues_rows(self, partition: PartitionedIssues | None) -> None:
        visible = partition.visible if partition is not None else ()
        # Decision Q: a null/bad FloatInt value's float_type+int_type pair
        # (V5) displays as one row here, matching the merged badge/page count
        # (core.completion.partition_issues already computes error_count/
        # warning_count the same way).
        merged = merge_union_pairs_by_location(visible)
        if not merged:
            self._add_message_row(_MSG_NO_ISSUES)
            return
        for issue, nav_path in merged:
            prefix = "ERROR" if issue.severity == Severity.ERROR else "WARN"
            loc_str = " → ".join(nav_path) if nav_path else "(document)"
            item = QListWidgetItem(f"[{prefix}] {loc_str}: {issue.message}")
            item.setData(_NAV_PATH_ROLE, nav_path)
            item.setData(_KIND_ROLE, "issue")
            self._list.addItem(item)

    # -- Outstanding ---------------------------------------------------
    def _add_outstanding_rows(
        self,
        raw: dict,
        model: str | None,
        tasks: tuple[CompletionTask, ...],
        partition: PartitionedIssues | None,
    ) -> None:
        if not tasks:
            if model == "Partial":
                self._add_message_row(_MSG_PARTIAL_NO_TARGET)
            else:
                self._add_message_row(_MSG_NOTHING_OUTSTANDING)
            return
        for section_path, group_tasks in _group_outstanding_tasks(tasks):
            # A DECLARE_MODEL task is always alone in its group (document_
            # completion returns it as the sole task whenever it appears) and
            # is not itself a section-shape fact -- "Header -- 1 of 2
            # remaining" reads indirectly when the one actionable thing is
            # declaring a model. It renders standalone, with no group
            # subheader, directly under the pinned "Declare a model" +
            # "Choose..." copy (plan's copy table).
            if group_tasks[0].kind is TaskKind.DECLARE_MODEL:
                for task in group_tasks:
                    self._add_task_row(task, partition)
                continue
            # Decision R: the required group's N/M ratio must never include
            # an optional row (the live-review defect -- "Cell -- 5 of 5
            # remaining" rendering 6 rows because an optional null field sat
            # in the same group). Only a NULL_FIELD task is ever optional
            # (MISSING_FIELD/MISSING_SECTION are always Required by
            # construction -- decision B), so splitting on ``task.required``
            # is exact: every task in ``required_tasks`` is Required, so N
            # (the row count) always equals M's numerator by construction.
            required_tasks = [task for task in group_tasks if task.required]
            optional_tasks = [task for task in group_tasks if not task.required]
            if required_tasks:
                self._add_required_group_header(raw, model, section_path, required_tasks)
                for task in required_tasks:
                    self._add_task_row(task, partition)
            if optional_tasks:
                self._add_optional_group_header(section_path, optional_tasks)
                for task in optional_tasks:
                    self._add_task_row(task, partition)

    def _add_required_group_header(
        self,
        raw: dict,
        model: str | None,
        section_path: tuple[str, ...],
        required_tasks: list[CompletionTask],
    ) -> None:
        """``<Section> -- N of M remaining`` (decision R): *required_tasks*
        is already filtered to Required-only, so N is always its own length
        -- the row count under this header always equals N, by construction,
        never a mismatch against optional rows sitting elsewhere now."""
        section_label = section_path[-1]
        # Checking only required_tasks[0]'s kind is correct because a
        # MISSING_SECTION task never shares its owning-section group with
        # field tasks (decision M: an absent section is one row; its fields
        # enumerate only once it exists, so a MISSING_SECTION and a
        # MISSING_FIELD/NULL_FIELD for the same section_path can never both
        # appear in the same document_completion() output at once). If that
        # invariant is ever relaxed, this must switch to checking every task.
        assert all(
            task.kind is TaskKind.MISSING_SECTION for task in required_tasks
        ) or not any(task.kind is TaskKind.MISSING_SECTION for task in required_tasks), (
            "A required group must be either one MISSING_SECTION task or all "
            "field tasks, never a mix (decision M) -- got: "
            f"{[task.kind for task in required_tasks]}"
        )
        if required_tasks[0].kind is TaskKind.MISSING_SECTION:
            text = f"{section_label} — section absent"
        else:
            value = _value_at(raw, section_path)
            required_total = completion.completion_for(section_path, value, model).required_total
            text = f"{section_label} — {len(required_tasks)} of {required_total} remaining"
        self._add_muted_header_row(text)

    def _add_optional_group_header(
        self, section_path: tuple[str, ...], optional_tasks: list[CompletionTask]
    ) -> None:
        """``<Section> · optional -- K unfilled`` (decision R): a quiet
        sub-group directly beneath the required group, for Expected-but-
        optional fields committed null (decision D, revised) -- no ratio (an
        optional field is never "required" to reach), no REQUIRED tag on its
        rows (:func:`_task_row_content` already reads ``task.required``)."""
        section_label = section_path[-1]
        text = f"{section_label} · optional — {len(optional_tasks)} unfilled"
        self._add_muted_header_row(text)

    def _add_muted_header_row(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
        item.setData(_KIND_ROLE, "group_header")
        item.setForeground(QColor(style.MUTED))
        font = QFont(self._list.font())
        font.setBold(True)
        item.setFont(font)
        self._list.addItem(item)

    def _add_task_row(self, task: CompletionTask, partition: PartitionedIssues | None) -> None:
        """Add one Outstanding row, including its absorbed messages (decision
        O) as muted secondary text -- merging a float/int pair (decision Q)
        the same way the Issues section and Issues tab do."""
        absorbed_pairs = partition.absorbed_by_task.get(task, ()) if partition is not None else ()
        merged = merge_union_pair(tuple(diagnostic for diagnostic, _ in absorbed_pairs))
        absorbed_messages = tuple(diagnostic.message for diagnostic in merged)
        text, html = _task_row_content(task, absorbed_messages)
        item = QListWidgetItem(text)
        item.setData(_KIND_ROLE, "task")
        item.setData(_TASK_ROLE, task)
        item.setData(parameter_row.HTML_ROLE, html)
        self._list.addItem(item)

    # -- shared --------------------------------------------------------
    def _add_page_header(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
        item.setData(_KIND_ROLE, "page_header")
        font = QFont(self._list.font())
        font.setBold(True)
        item.setFont(font)
        self._list.addItem(item)

    def _add_message_row(self, text: str) -> None:
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
        item.setData(_KIND_ROLE, "message")
        item.setForeground(QColor(style.MUTED))
        self._list.addItem(item)

    def _on_activated(self, item: QListWidgetItem) -> None:
        kind = item.data(_KIND_ROLE)
        if kind == "issue":
            self.issue_activated.emit(item.data(_NAV_PATH_ROLE))
        elif kind == "task":
            self.task_activated.emit(item.data(_TASK_ROLE))
