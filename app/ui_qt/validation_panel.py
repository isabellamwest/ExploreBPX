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

Layout (Concept A, 2026-07-15 design pass -- "make it scannable, not a block
of text"): each page-section header carries a muted count suffix ("Issues ·
7 errors · 1 warning") so the page's scale reads before any detail. Issues
then cluster into **collapsible groups by section**; a single click on a
``▾ Section  N`` header folds it away (the count is coloured by the group's
worst severity). Every issue row is **two lines** -- a coloured severity tag
and the bold, section-relative location on the first, the validator's
verbatim message (muted) on the second (``parameter_row.compose_issue_row_html``)
-- so where and what stop competing for one line. Outstanding keeps its
decision-R grouping unchanged.

Single ``QListWidget``, role-typed rows (mirrors ``parameter_list.py``'s group
idiom): a page-section header, a collapsible issue section_group, a group
subheader, an issue row, a task row, a spacer, or a plain message row. Only
issue/task rows are selectable, so keyboard navigation skips every
header/message row and Enter on one of them is a structural no-op rather than
a special-cased guard. ``itemActivated`` (Enter/double-click) navigates
(issue/task rows only); ``itemClicked`` folds a section group and nothing
else -- navigation stays Enter/double-click, the same contract ``IssuesTab``
uses. A collapse persists across ``refresh`` (kept in
``_collapsed_issue_sections``) so an edit elsewhere doesn't snap folded
sections open.
"""

from __future__ import annotations

import html as _html

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import (
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QStyle,
    QStyleOptionViewItem,
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
_KIND_ROLE = Qt.UserRole + 300  # "page_header" | "group_header" | "section_group" | "issue" | "task" | "message" | "spacer"
_TASK_ROLE = Qt.UserRole + 301  # CompletionTask, "task" rows only
_SECTION_ROLE = Qt.UserRole + 302  # section name a "section_group" header toggles
_GROUP_KEY_ROLE = Qt.UserRole + 303  # fold key an Outstanding "group_header" toggles

#: The group an issue clusters under (Concept A): its top-level section --
#: nav paths are already section-relative (V4 strips Header/Parameterisation),
#: so the first segment is the section. A diagnostic with no location (a
#: document-level warning) clusters under this label instead.
_DOCUMENT_GROUP = "Document"


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


class _ValidationRowDelegate(ParameterRowDelegate):
    """Validation-page painting on top of the shared row delegate.

    Two page-specific behaviours:

    - a ``page_header`` row paints as a **labelled divider** -- a short
      leading rule, the bold title (with its muted count), then a hairline
      rule to the row's right edge -- so the two page sections read as ruled
      bands rather than floating bold lines;
    - only actionable rows (``issue``/``task``) show hover or selection.
      Headers, group rows, messages and spacers paint flat whatever the
      mouse does -- a highlight promises interaction, and activating them is
      a structural no-op. The fold-toggling section/group headers stay
      clickable; their chevron is the affordance, not a highlight.
    """

    _INTERACTIVE_KINDS = frozenset({"issue", "task"})
    _DIVIDER_LEAD = 10  # rule length before the label
    _DIVIDER_GAP = 8  # breathing room between rule and label text

    def paint(self, painter, option, index) -> None:
        kind = index.data(_KIND_ROLE)
        if kind == "page_header":
            self._paint_divider(painter, option, index)
            return
        if kind is not None and kind not in self._INTERACTIVE_KINDS:
            option = QStyleOptionViewItem(option)
            option.state &= ~(QStyle.State_MouseOver | QStyle.State_Selected)
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        if index.data(_KIND_ROLE) == "page_header":
            return QSize(int(self._available_width(option)), 34)
        return super().sizeHint(option, index)

    def _paint_divider(self, painter, option, index) -> None:
        doc = self._build_document(option, index, self._available_width(option))
        if doc is None:  # defensive: a header without HTML falls back plain
            super().paint(painter, option, index)
            return
        doc.setTextWidth(-1)  # natural width -- the label never wraps
        rect = option.rect.adjusted(self._h_pad, 0, -self._h_pad, 0)
        text_width = doc.idealWidth()
        text_height = doc.size().height()
        y_mid = rect.top() + rect.height() / 2.0
        text_x = rect.left() + self._DIVIDER_LEAD + self._DIVIDER_GAP

        painter.save()
        painter.translate(text_x, y_mid - text_height / 2.0)
        doc.drawContents(painter)
        painter.restore()

        painter.save()
        painter.setPen(QPen(QColor(style.BORDER), 1))
        y = round(y_mid)
        painter.drawLine(rect.left(), y, rect.left() + self._DIVIDER_LEAD, y)
        rule_start = round(text_x + text_width + self._DIVIDER_GAP)
        if rule_start < rect.right():
            painter.drawLine(rule_start, y, rect.right(), y)
        painter.restore()


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
        # 8px page margin + the 8px ::item padding lands row text at 16px,
        # aligned with the page header title's own 16px inset.
        layout.setContentsMargins(8, 4, 8, 8)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        self._list = QListWidget()
        self._list.setObjectName("ValidationList")
        self._list.setWordWrap(True)
        # Page-specific delegate: divider page headers, and hover/selection
        # painted only on actionable (issue/task) rows. Rows without
        # HTML_ROLE data still fall through to the base delegate untouched.
        self._list.setItemDelegate(_ValidationRowDelegate(self._list))
        # itemActivated fires on Enter/Return and double-click, so a single
        # connection covers keyboard and mouse activation without duplicate
        # emits. Selection changes alone (arrow keys) do not trigger it, and
        # header/message rows are never selectable at all, so they cannot
        # become "current" for Enter to target.
        self._list.itemActivated.connect(self._on_activated)
        # A single click toggles a collapsible section group; it never
        # navigates (navigation stays Enter/double-click, the Issues
        # contract). Issue/task rows ignore the click here.
        self._list.itemClicked.connect(self._on_clicked)
        self._stack.addWidget(self._list)  # index 0 -- issue list

        #: Issues-section groups the user has collapsed, by section name.
        #: Survives ``refresh`` (every commit rebuilds the list) so a collapse
        #: doesn't snap open on the next edit; a stale name for a section that
        #: no longer exists simply matches nothing.
        self._collapsed_issue_sections: set[str] = set()
        #: Outstanding groups the user has collapsed, keyed by
        #: ``(tier, *section_path)`` where tier is "required"/"optional" --
        #: the two sub-groups of one section fold independently. Same
        #: survives-refresh behaviour as the Issues folds.
        self._collapsed_outstanding_groups: set[tuple[str, ...]] = set()
        #: The last ``refresh`` arguments, replayed when a group is toggled so
        #: the toggle needs no access to ``main_window``'s derivation.
        self._last_refresh: tuple | None = None

        self._placeholder = QLabel(_MSG_NO_DOCUMENT)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)  # index 1 -- empty state

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)  # start on the placeholder

    def reset_view_state(self) -> None:
        """Forget per-document view state (folded groups).

        Folds are keyed by section *name*, so without this a section folded
        in one file would open pre-folded in the next file that happens to
        share the name. Called when a different document replaces the
        session (open/new) -- never on ordinary refreshes, where surviving
        is the point.
        """
        self._collapsed_issue_sections.clear()
        self._collapsed_outstanding_groups.clear()

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
        self._last_refresh = (raw, model, partition, tasks)
        self._list.clear()
        if raw is None:
            self._placeholder.setText(_MSG_NO_DOCUMENT)
            self._stack.setCurrentIndex(1)
            return
        self._add_page_header("Issues", self._issues_count_suffix(partition))
        self._add_issues_rows(partition)
        self._add_section_spacer()
        self._add_page_header("Outstanding", self._outstanding_count_suffix(tasks))
        self._add_outstanding_rows(raw, model, tasks, partition)
        self._stack.setCurrentIndex(0)

    # -- counts ------------------------------------------------------
    @staticmethod
    def _issues_count_suffix(partition: PartitionedIssues | None) -> str:
        """`` · 7 errors · 1 warning`` for the Issues header, from the merged
        counts the badge also uses (decision G/Q). Empty when the document is
        clean, so a valid document's header reads just ``Issues``."""
        if partition is None:
            return ""
        parts = []
        if partition.error_count:
            parts.append(f"{partition.error_count} error{'s' if partition.error_count != 1 else ''}")
        if partition.warning_count:
            parts.append(f"{partition.warning_count} warning{'s' if partition.warning_count != 1 else ''}")
        return "  ·  " + " · ".join(parts) if parts else ""

    @staticmethod
    def _outstanding_count_suffix(tasks: tuple[CompletionTask, ...]) -> str:
        """`` · 4 remaining`` for the Outstanding header. Every task is a
        thing left to do, so the raw task count is the honest total."""
        return f"  ·  {len(tasks)} remaining" if tasks else ""

    # -- Issues ------------------------------------------------------
    def _add_issues_rows(self, partition: PartitionedIssues | None) -> None:
        visible = partition.visible if partition is not None else ()
        # Decision Q: a null/bad FloatInt value's float/int pair (V5) displays
        # as one row here, matching the merged badge/page count (partition's
        # error_count/warning_count are computed the same way).
        merged = merge_union_pairs_by_location(visible)
        if not merged:
            self._add_message_row(_MSG_NO_ISSUES)
            return
        for section, issues in self._group_issues_by_section(merged):
            collapsed = section in self._collapsed_issue_sections
            self._add_issue_section_group(section, issues, collapsed)
            if collapsed:
                continue
            for issue, nav_path in issues:
                self._add_issue_row(issue, nav_path, section)

    @staticmethod
    def _group_issues_by_section(
        merged: tuple[tuple[object, tuple[str, ...]], ...],
    ) -> list[tuple[str, list[tuple[object, tuple[str, ...]]]]]:
        """Cluster merged issues by top-level section, first-appearance order
        (already document order -- ``iter_issues`` walks the tree in raw dict
        order). A diagnostic with no nav path clusters under ``Document``."""
        groups: dict[str, list] = {}
        order: list[str] = []
        for issue, nav_path in merged:
            section = nav_path[0] if nav_path else _DOCUMENT_GROUP
            if section not in groups:
                groups[section] = []
                order.append(section)
            groups[section].append((issue, nav_path))
        return [(section, groups[section]) for section in order]

    def _add_issue_section_group(
        self, section: str, issues: list, collapsed: bool
    ) -> None:
        """A collapsible ``▾ Section  N`` header clustering one section's
        issues. Clickable (``_on_clicked``) to fold the section away -- the
        core navigation aid for a document with many issues."""
        chevron = "▸" if collapsed else "▾"
        count = len(issues)
        # Colour the count by the worst severity the section holds -- red when
        # any error, amber for a warning-only section -- so a folded group
        # still signals how bad it is.
        has_error = any(issue.severity == Severity.ERROR for issue, _ in issues)
        count_color = style.ERROR if has_error else style.WARNING
        html = parameter_row.compose_row_html(
            f"{chevron}  {section}",
            [(str(count), count_color)],
            name_color=style.MUTED,
        )
        item = QListWidgetItem(f"{chevron} {section}  ({count})")
        item.setFlags(Qt.ItemIsEnabled)  # visible + clickable, never selectable
        item.setData(_KIND_ROLE, "section_group")
        item.setData(_SECTION_ROLE, section)
        item.setData(parameter_row.HTML_ROLE, html)
        self._list.addItem(item)

    @staticmethod
    def _relative_location(section: str, nav_path: tuple[str, ...]) -> str:
        """The issue's location *within* its section group -- the section
        prefix is the group header above it, so it's dropped. A section-level
        or document-level diagnostic (nav path is just the section, or empty)
        has no in-section location and returns ``""`` (message-only row)."""
        if len(nav_path) <= 1:
            return ""
        return " → ".join(nav_path[1:])

    def _add_issue_row(self, issue, nav_path: tuple[str, ...], section: str) -> None:
        is_error = issue.severity == Severity.ERROR
        label = "ERROR" if is_error else "WARN"
        color = style.ERROR if is_error else style.WARNING
        location = self._relative_location(section, nav_path)
        plain_loc = " → ".join(nav_path) if nav_path else "(document)"
        item = QListWidgetItem(f"[{label}] {plain_loc}: {issue.message}")
        item.setData(
            parameter_row.HTML_ROLE,
            parameter_row.compose_issue_row_html(label, color, location, issue.message),
        )
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
                required_key = ("required", *section_path)
                self._add_required_group_header(
                    raw, model, section_path, required_tasks, required_key
                )
                if required_key not in self._collapsed_outstanding_groups:
                    for task in required_tasks:
                        self._add_task_row(task, partition)
            if optional_tasks:
                optional_key = ("optional", *section_path)
                self._add_optional_group_header(section_path, optional_tasks, optional_key)
                if optional_key not in self._collapsed_outstanding_groups:
                    for task in optional_tasks:
                        self._add_task_row(task, partition)

    def _add_required_group_header(
        self,
        raw: dict,
        model: str | None,
        section_path: tuple[str, ...],
        required_tasks: list[CompletionTask],
        fold_key: tuple[str, ...],
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
        self._add_muted_header_row(text, fold_key)

    def _add_optional_group_header(
        self,
        section_path: tuple[str, ...],
        optional_tasks: list[CompletionTask],
        fold_key: tuple[str, ...],
    ) -> None:
        """``<Section> · optional -- K unfilled`` (decision R): a quiet
        sub-group directly beneath the required group, for Expected-but-
        optional fields committed null (decision D, revised) -- no ratio (an
        optional field is never "required" to reach), no REQUIRED tag on its
        rows (:func:`_task_row_content` already reads ``task.required``)."""
        section_label = section_path[-1]
        text = f"{section_label} · optional — {len(optional_tasks)} unfilled"
        self._add_muted_header_row(text, fold_key)

    def _add_muted_header_row(self, text: str, fold_key: tuple[str, ...]) -> None:
        """An Outstanding group header: muted, bold, foldable by a single
        click like the Issues section groups. ``item.text()`` stays the bare
        header text (the driver and tests match on it); the chevron lives
        only in the painted HTML."""
        chevron = "▸" if fold_key in self._collapsed_outstanding_groups else "▾"
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible + clickable, never selectable
        item.setData(_KIND_ROLE, "group_header")
        item.setData(_GROUP_KEY_ROLE, fold_key)
        item.setData(
            parameter_row.HTML_ROLE,
            parameter_row.compose_row_html(
                f"{chevron}  {text}", [], name_color=style.MUTED
            ),
        )
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
    def _add_page_header(self, text: str, count_suffix: str = "") -> None:
        # item.text() stays the bare title ("Issues"/"Outstanding") -- the
        # driver and section-message lookup match on it; the count lives only
        # in the painted HTML.
        item = QListWidgetItem(text)
        item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
        item.setData(_KIND_ROLE, "page_header")
        # The bold section title carries an optional muted count suffix
        # (" · 7 errors · 1 warning") so the page's scale reads before any
        # row detail; rendered as HTML so only the suffix is de-emphasised.
        head = (
            f'<span style="font-weight:700; color:{parameter_row.DEFAULT_TEXT};">'
            f"{_html.escape(text)}</span>"
        )
        if count_suffix:
            head += f'<span style="color:{style.MUTED};">{_html.escape(count_suffix)}</span>'
        item.setData(parameter_row.HTML_ROLE, head)
        self._list.addItem(item)

    def _add_section_spacer(self) -> None:
        """A thin, empty, non-interactive row that separates the two page
        sections -- breathing room the delegate's per-row padding can't give
        on its own."""
        item = QListWidgetItem("")
        item.setFlags(Qt.NoItemFlags)
        item.setData(_KIND_ROLE, "spacer")
        item.setSizeHint(QSize(0, 10))
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

    def _on_clicked(self, item: QListWidgetItem) -> None:
        """A single click on a foldable header (an Issues section group or an
        Outstanding group header) folds or unfolds it; every other row
        ignores the click (navigation stays Enter/double-click). The toggle
        replays the last ``refresh`` so the rebuild reuses one code path and
        needs no document access of its own."""
        kind = item.data(_KIND_ROLE)
        if kind == "section_group":
            section = item.data(_SECTION_ROLE)
            self._collapsed_issue_sections.symmetric_difference_update({section})
        elif kind == "group_header":
            fold_key = item.data(_GROUP_KEY_ROLE)
            if fold_key is None:
                return
            self._collapsed_outstanding_groups.symmetric_difference_update({fold_key})
        else:
            return
        if self._last_refresh is not None:
            self.refresh(*self._last_refresh)
