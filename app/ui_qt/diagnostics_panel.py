"""Diagnostics page: summary strip + section rail + single-section detail
pane (Validation-page rail redesign, ``PLAN-completion-track.md`` S4b,
decisions F2-F7 -- Stage B, built on Stage A's ``core.page_buckets``).

``bucket_page_content`` (Stage A) makes every grouping/absorption decision
once, inward of the UI: this module renders its ``PageBuckets`` output and
nothing else -- it never re-derives which section an issue or task belongs
to. The old ``_display_path``/``_owning_section``/``_group_outstanding_tasks``
helpers this file used to carry are gone; that duplication is exactly what
put Issues and Outstanding grouping out of sync with each other before
(see ``core.page_buckets``'s own module docstring).

Layout (F2, signed-off wireframe):

* A **summary strip** across the top -- three static chips (errors,
  warnings, outstanding), counts from ``PageBuckets`` totals.
* A **rail** (``_RailList``, fixed width) below it: "All sections" first
  (one neutral total badge), a separator, then one entry per
  ``SectionBucket`` in ``PageBuckets`` order (the Document bucket, when
  occupied, sits first -- Stage A already orders it that way). Quiet by
  design (F4): a clean bucket shows no badge at all; red/amber/grey rounded
  badges appear only for nonzero error/warning/outstanding counts; an
  absent section renders its name italic. Selecting an entry (click or
  arrow keys) switches the pane immediately and never touches the document.
* A **detail pane** to the right, one of two views:

  - a single section's Issues + Outstanding, each a bordered, banded
    "group box" (``_GroupBox``), composed by ``_SectionDetailView``;
  - "All sections", the whole-document backup view (F3): every bucket
    exactly once, a foldable header (chevron + label + the same badges as
    the rail) over its issue rows then its outstanding rows under
    pinned-copy sub-heads (``_AllSectionsView``). This is what F3's
    reconciliation test checks against the strip/rail totals -- nothing
    renders here that isn't already counted there, and nothing counted
    there is missing here.

Row anatomy (F5): an issue row's severity is a small delegate-painted
filled-circle icon (:data:`ui_qt.parameter_row.SEVERITY_ROLE`) -- red X for
an error, amber ! for a warning -- replacing the old bracketed
``[ERROR]``/``[WARN]`` text tag. This is a shared change to
``ParameterRowDelegate`` itself, so the Inspector's Issues tab
(:mod:`ui_qt.issues_tab`) picks it up too. A task row keeps its own glyph
(a hollow circle for "missing", a half-filled circle for "added, no value
yet"), bold name + muted unit, a REQUIRED tag where applicable, the
absorbed validator message (decision O) as muted secondary text, and its
action ("Go to (right chevron)"/"+ Add section"/"Choose...") always visible
in accent colour (decision L).

Activation contract (decision L, unchanged): Enter/double-click only,
selection alone never acts. Both panes expose the same
``issue_activated``/``task_activated`` signals this panel forwards
unmodified -- ``MainWindow`` dispatches exactly as it did before this
redesign (``_on_task_activated``). A Document-bucket issue row's nav_path
is whatever the diagnostic-attachment pass resolved (its nearest existing
ancestor, or empty when nothing resolves); ``NavigationService.navigate``
already no-ops on an empty path, so "no attachment point -> no-op" needs no
special-casing here.

View state (F6: one primary document, no module-level globals) lives on
this panel instance: the selected rail entry and the All-sections fold set.
Both persist across an ordinary ``refresh`` (a commit, undo/redo) and reset
via :meth:`reset_view_state`, called by ``MainWindow`` only when a
*different* document replaces the session (open/new) -- mirrors the
parameter list's own expansion-state convention.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core.completion import CompletionTask, PartitionedIssues, TaskKind
from core.page_buckets import (
    DOCUMENT_BUCKET_PATH,
    PageBuckets,
    SectionBucket,
    strip_parameterisation_prefix,
)
from core.validation import Severity, merge_union_pair

from . import badges, icons, parameter_row, style
from .parameter_row import ParameterRowDelegate
from .titles import panel_title

_MSG_NO_DOCUMENT = "No document open"
_MSG_NO_ISSUES = style.all_clear("No issues")
_MSG_NOTHING_OUTSTANDING = style.all_clear("Nothing outstanding")
#: Decision C's pinned Partial-model notice. A bucket alone cannot tell
#: "Partial, so nothing is ever tracked" apart from "concrete model, fully
#: filled, nothing remaining" -- both look identical from bucket data (zero
#: ``required_tasks``, nonzero ``required_total``) -- so this is the one
#: place ``model`` reaches this module (:meth:`_SectionDetailView.render`),
#: a narrow, deliberate exception to "consume only PageBuckets" (grouping/
#: counting logic itself stays entirely bucket-derived).
_MSG_PARTIAL_NO_TARGET = (
    "Model is Partial - no completion target. Expected fields are still "
    "suggested in each section's parameter list."
)

_ACTION_GO_TO = "Go to ›"
_ACTION_ADD_SECTION = "+ Add section"
_ACTION_CHOOSE = "Choose…"

#: Task-row glyphs (F5): a hollow circle for "nothing committed yet"
#: (MISSING_FIELD/MISSING_SECTION/DECLARE_MODEL), a half-filled circle for
#: "committed, but null" (NULL_FIELD) -- the same missing/added-no-value
#: distinction decision D draws in prose, made visible at a glance. Plain
#: Unicode glyphs, used only for a task item's underlying (non-painted)
#: ``QListWidgetItem`` text -- the delegate always paints the row's
#: :data:`parameter_row.HTML_ROLE` fragment instead (see :func:`_task_glyph_svg`
#: for that rich-text counterpart, the shared dot family from :mod:`ui_qt.icons`).
_GLYPH_MISSING = "○"
_GLYPH_NULL = "◐"

#: Rail/selection sentinel for the "All sections" entry -- distinct from
#: every real bucket path, including the empty-tuple Document sentinel
#: (``DOCUMENT_BUCKET_PATH``), since a plain string can never equal a tuple.
_ALL_SECTIONS_KEY = "__all__"

#: Item-data roles for the two detail-pane lists (group-box lists and the
#: All-sections list share these). 256 is the pre-existing nav-path role
#: "issue" rows carry (kept unchanged so nothing downstream that reads it
#: needs to know this file changed).
_NAV_PATH_ROLE = 256
_KIND_ROLE = Qt.UserRole + 300  # "issue" | "task" | "message" | "subhead" | "fold_header"
_TASK_ROLE = Qt.UserRole + 301
_FOLD_BUCKET_ROLE = Qt.UserRole + 302  # SectionBucket, "fold_header" rows only (All-sections)
_FOLD_COLLAPSED_ROLE = Qt.UserRole + 303

#: Item-data roles for the rail list.
_RAIL_KIND_ROLE = Qt.UserRole + 310  # "all" | "separator" | "section"
_RAIL_PATH_ROLE = Qt.UserRole + 311  # bucket.path, "section" rows only
_RAIL_ABSENT_ROLE = Qt.UserRole + 312
_RAIL_BADGE_ROLE = Qt.UserRole + 313  # list[(text, bg, fg)]


# ---------------------------------------------------------------------------
# Badge painting -- shared by the rail and the All-sections fold headers
# ("same badges as rail", per the signed-off wireframe). QTextDocument/QSS
# cannot paint a rounded pill, so every badge here is delegate-drawn, the
# same idiom the app-rail's own ActivityButton badge already uses.
# ---------------------------------------------------------------------------


def _issue_badge_specs(bucket: SectionBucket) -> list[tuple[str, str, str]]:
    """Ordered ``(text, bg, fg)`` badge specs for one bucket's Issues count
    only -- red for errors, amber for warnings, either/both/neither
    depending on what is actually nonzero (F4/F5). The red/amber half of
    :func:`_bucket_badge_specs`, factored out so the rail/fold-header badges
    and the section pane's Issues box header (which has no outstanding
    badge of its own -- that ratio lives in the Outstanding box's title)
    can never drift apart on what "an issue badge" means."""
    specs: list[tuple[str, str, str]] = []
    if bucket.error_count:
        specs.append((str(bucket.error_count), *badges.badge_colors("error")))
    if bucket.warning_count:
        specs.append((str(bucket.warning_count), *badges.badge_colors("warning")))
    return specs


def _bucket_badge_specs(bucket: SectionBucket) -> list[tuple[str, str, str]]:
    """Ordered ``(text, bg, fg)`` badge specs for one bucket (F4): a clean
    bucket (all counts zero) yields no specs at all -- the quiet rail."""
    specs = list(_issue_badge_specs(bucket))
    if bucket.outstanding_count:
        specs.append((str(bucket.outstanding_count), *badges.badge_colors(None)))
    return specs


def _measure_badge_specs(specs: list[tuple[str, str, str]]) -> int:
    """Total width *specs* will occupy when painted (see :func:`_paint_badges`),
    used to reserve label space before drawing -- 0 for an empty list."""
    if not specs:
        return 0
    total = 0
    for text, _bg, _fg in specs:
        total += badges.badge_width(text) + 6
    return total


def _paint_one_badge(painter: QPainter, right_x: int, y_mid: int, text: str, bg: str, fg: str) -> int:
    """Paint one small rounded count badge ending at *right_x*, vertically
    centred on *y_mid*; returns the left edge to place the next badge at."""
    height = badges.HEIGHT
    width = badges.badge_width(text)
    rect = QRect(0, 0, width, height)
    rect.moveRight(right_x)
    rect.moveTop(int(y_mid - height / 2))
    badges.paint_badge(painter, rect, text, bg, fg)
    return rect.left() - 6


def _paint_badges(painter: QPainter, rect: QRect, specs: list[tuple[str, str, str]]) -> None:
    """Paint *specs* right-aligned within *rect*, in reading order left to
    right (error, then warning, then outstanding -- callers already build
    *specs* in that priority order, e.g. :func:`_bucket_badge_specs`).
    Painting itself works right to left (each successive badge placed to
    the left of the last, anchored off *rect*'s own right edge), so the
    *last* spec is painted first, at the rightmost position -- ``specs`` is
    walked in reverse to land the first (most severe) spec leftmost."""
    y_mid = rect.center().y()
    right = rect.right()
    for text, bg, fg in reversed(specs):
        right = _paint_one_badge(painter, right, y_mid, text, bg, fg)


# ---------------------------------------------------------------------------
# View-only filtering (F8, phase B). Rows are hidden by the VIEW BUILDERS
# below (``_SectionDetailView``/``_AllSectionsView``) after they already
# have their bucket's true, unfiltered content in hand -- ``core.page_
# buckets`` is never touched, so rail badges/strip counts/the app badge/F3
# reconciliation all keep reading the same unfiltered ``PageBuckets`` this
# module always has. ``_FilterState`` and the two visibility predicates
# below are the one shared, pure "does this row survive the filter" rule
# both view builders consume -- neither one re-derives it.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FilterState:
    """Per-session view-only filter state (F8). All-on is the default --
    i.e. "no filtering". (F8's text filter was removed by explicit user
    decision: per-section buckets are small and the toolbar search already
    finds anything by name -- the chips alone remain.)"""

    error_on: bool = True
    warning_on: bool = True
    outstanding_on: bool = True


#: What an issue row shows in place of an empty section-relative location
#: (a loc that collapses entirely into the bucket label, e.g. a section-level
#: validator error).
_EMPTY_LOCATION_LABEL = "(document)"


def _issue_visible(diagnostic, filters: _FilterState) -> bool:
    """Whether one issue row survives *filters* -- its severity's chip must
    be on (a cheap enum check)."""
    is_error = diagnostic.severity == Severity.ERROR
    if is_error and not filters.error_on:
        return False
    if not is_error and not filters.warning_on:
        return False
    return True


def _task_visible(task: CompletionTask, filters: _FilterState) -> bool:
    """Whether one task row survives *filters* -- the outstanding chip
    must be on."""
    return filters.outstanding_on


# ---------------------------------------------------------------------------
# Outstanding-row / issue-row content (shared by the section pane's group
# boxes and the All-sections view).
# ---------------------------------------------------------------------------


def _relative_location(bucket_label: str, nav_path: tuple[str, ...]) -> str:
    """The issue's location *within* its bucket -- the bucket label is the
    box/fold header above it, so it's dropped. Handles both a canonical,
    resolved path (``("Parameterisation", "Cell", "X")`` for the "Cell"
    bucket) and a V4-stripped, unresolved one (``("Cell", "X")``, the
    validator's own leading-prefix-dropped convention) the same way: strip
    a leading "Parameterisation" wrapper via the one shared owner of that
    rule (:func:`core.page_buckets.strip_parameterisation_prefix` -- the
    same normalization :func:`core.page_buckets._bucket_path_for` itself
    builds on), then strip the bucket's own label if it is the leading
    token either way."""
    trimmed = strip_parameterisation_prefix(nav_path)
    if trimmed[:1] == (bucket_label,):
        trimmed = trimmed[1:]
    return " → ".join(trimmed)


def _is_declare_model_only(bucket: SectionBucket) -> bool:
    """True when *bucket*'s only Outstanding row is "declare a model" --
    ``document_completion`` always returns DECLARE_MODEL alone (decision C),
    so a group holding it is never a section-shape fact ("Header -- 1 of 3
    remaining" would read indirectly when the one actionable thing is
    declaring a model). Such a group renders no ratio at all."""
    return len(bucket.required_tasks) == 1 and bucket.required_tasks[0].kind is TaskKind.DECLARE_MODEL


def _required_field_tasks(bucket: SectionBucket) -> tuple[CompletionTask, ...]:
    """*bucket.required_tasks* minus any MISSING_SECTION entries.

    Stage A buckets a present section's absent CHILD sections together with
    its own leaf-field tasks (e.g. a present ``State`` with both
    ``Initial conditions`` and ``Thermal environment`` still missing lands
    both MISSING_SECTION tasks in the ``State`` bucket, per
    ``core.page_buckets``'s own grouping rule) -- naming a whole absent
    child is not a leaf-field fact, so it must not count toward
    ``required_total`` (M counts leaf fields only, per
    ``completion_for``) or its "N of M" numerator."""
    return tuple(task for task in bucket.required_tasks if task.kind is not TaskKind.MISSING_SECTION)


def _ratio_words(bucket: SectionBucket) -> str:
    """"N of M remaining" / "section absent" / "N sections absent"
    (Document's fallback: "N remaining") -- the shared core of both the
    pane's box title and the All-sections pinned sub-head text; callers add
    their own prefix.

    A present bucket can also hold one or more required MISSING_SECTION
    tasks for its own absent children (see :func:`_required_field_tasks`);
    those never enter the leaf-field ratio, so they are named separately
    ("N sections absent") rather than folded into a "0 of 0 remaining"
    that would misreport real rows sitting beneath it as "nothing to do".
    Verified against every SPM/SPMe/DFN section (none mixes required leaf
    fields with a required child section) that this case's own
    ``required_total`` is always 0, so there is no reachable "ratio AND
    absent children" combination to word today -- simplest correct is to
    report the absent-child note alone. Revisit if a future schema section
    ever mixes the two shapes (the ratio would silently go unreported)."""
    if bucket.path == DOCUMENT_BUCKET_PATH:
        return f"{len(bucket.required_tasks)} remaining"
    if bucket.absent:
        return "section absent"
    section_tasks = [task for task in bucket.required_tasks if task.kind is TaskKind.MISSING_SECTION]
    if section_tasks:
        noun = "section" if len(section_tasks) == 1 else "sections"
        return f"{len(section_tasks)} {noun} absent"
    field_tasks = _required_field_tasks(bucket)
    return f"{len(field_tasks)} of {bucket.required_total} remaining"


def _outstanding_box_title(bucket: SectionBucket) -> str:
    if _is_declare_model_only(bucket):
        return "Outstanding"
    return f"Outstanding · {_ratio_words(bucket)}"


def _absorbed_messages(task: CompletionTask, partition: PartitionedIssues | None) -> tuple[str, ...]:
    """The real validator messages *task* stands in for (decision O), merging
    a float/int union pair (decision Q) the same way the Issues surfaces do."""
    if partition is None:
        return ()
    pairs = partition.absorbed_by_task.get(task, ())
    merged = merge_union_pair(tuple(diagnostic for diagnostic, _ in pairs))
    return tuple(diagnostic.message for diagnostic in merged)


def _task_glyph(task: CompletionTask) -> str:
    return _GLYPH_NULL if task.kind is TaskKind.NULL_FIELD else _GLYPH_MISSING


def _task_glyph_svg(task: CompletionTask) -> str:
    """The rich-text counterpart of :func:`_task_glyph`, painted by
    :func:`_task_row_html`: the same NULL_FIELD/other split, a mark from the
    shared dot family (:mod:`ui_qt.icons`) instead of a bare Unicode glyph."""
    return icons.HALF if task.kind is TaskKind.NULL_FIELD else icons.RING


def _task_label(task: CompletionTask) -> tuple[str, str | None, str]:
    """Return ``(name, note, action)`` for one task, per the pinned copy table."""
    if task.kind is TaskKind.MISSING_FIELD:
        return task.alias, None, _ACTION_GO_TO
    if task.kind is TaskKind.NULL_FIELD:
        return task.alias, "added, no value yet", _ACTION_GO_TO
    if task.kind is TaskKind.MISSING_SECTION:
        return task.path[-1], None, _ACTION_ADD_SECTION
    return "Declare a model", None, _ACTION_CHOOSE  # DECLARE_MODEL


def _task_row_text(task: CompletionTask, absorbed_messages: tuple[str, ...]) -> str:
    glyph = _task_glyph(task)
    name, note, action = _task_label(task)
    label = f"{name} - {note}" if note else name
    text = f"{glyph} {label}"
    if task.required:
        text += "  (REQUIRED)"
    text += f"  {action}"
    if absorbed_messages:
        text += "  - " + "; ".join(absorbed_messages)
    return text


def _task_row_html(task: CompletionTask, absorbed_messages: tuple[str, ...]) -> str:
    """§4b F5: REQUIRED sits inline right after the name; the action text
    itself is NOT part of this HTML fragment -- it is painted separately,
    right-aligned, by the delegate (see :data:`parameter_row.ACTION_ROLE`,
    set by :func:`_add_task_row`) so it never competes with a long name for
    the same line.

    Polish round: the ring/half-filled mark is painted in ``style.MUTED``
    (the same grey #57606a family) to harmonise with the issue rows' flat
    severity dots, not swept up in the bold name span the way it used to be."""
    glyph_img = icons.html_img(_task_glyph_svg(task), color=style.MUTED, size=parameter_row.MARK_BOX)
    name, note, action = _task_label(task)
    label = f"{name} - {note}" if note else name
    hints: list[tuple[str, str]] = []
    if task.required:
        hints.append(("REQUIRED", style.REQUIRED))
    name_fragment = parameter_row.compose_row_html(label, hints, name_color=style.DEFAULT_TEXT)
    fragment = f"{glyph_img}  {name_fragment}"
    if absorbed_messages:
        secondary = "<br>".join(
            f'<span style="color:{style.MUTED}; font-size:90%;">{_html.escape(message)}</span>'
            for message in absorbed_messages
        )
        fragment += "<br>" + secondary
    return fragment


# ---------------------------------------------------------------------------
# Row builders -- shared by ``_GroupBox``'s lists and ``_AllSectionsView``.
# ---------------------------------------------------------------------------


def _add_issue_row(list_widget: QListWidget, bucket_label: str, diagnostic, nav_path: tuple[str, ...]) -> None:
    is_error = diagnostic.severity == Severity.ERROR
    label = "ERROR" if is_error else "WARN"
    location = _relative_location(bucket_label, nav_path)
    plain_loc = location or _EMPTY_LOCATION_LABEL
    item = QListWidgetItem(f"[{label}] {plain_loc}: {diagnostic.message}")
    item.setData(parameter_row.HTML_ROLE, parameter_row.compose_issue_row_html(location, diagnostic.message))
    item.setData(parameter_row.SEVERITY_ROLE, "error" if is_error else "warning")
    item.setToolTip(style.severity_tooltip(diagnostic.severity))
    item.setData(_NAV_PATH_ROLE, nav_path)
    item.setData(_KIND_ROLE, "issue")
    list_widget.addItem(item)


def _add_task_row(list_widget: QListWidget, task: CompletionTask, absorbed_messages: tuple[str, ...]) -> None:
    item = QListWidgetItem(_task_row_text(task, absorbed_messages))
    item.setData(_KIND_ROLE, "task")
    item.setData(_TASK_ROLE, task)
    item.setData(parameter_row.HTML_ROLE, _task_row_html(task, absorbed_messages))
    item.setData(parameter_row.ACTION_ROLE, _task_label(task)[2])
    item.setToolTip(style.task_kind_tooltip(task.kind))
    list_widget.addItem(item)


def _add_message_row(list_widget: QListWidget, text: str) -> None:
    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "message")
    item.setForeground(QColor(style.MUTED))
    list_widget.addItem(item)


def _add_subhead_row(list_widget: QListWidget, text: str) -> None:
    """A quiet, non-activatable sub-head row: the per-section pane's
    "OPTIONAL -- K UNFILLED", or (All-sections only) the pinned-copy
    "<Section> -- N of M remaining" / "<Section> -- section absent" /
    "<Section> * optional -- K unfilled" lines."""
    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "subhead")
    item.setData(parameter_row.HTML_ROLE, parameter_row.compose_row_html(text, [], name_color=style.MUTED))
    list_widget.addItem(item)


def _add_fold_header_row(list_widget: QListWidget, bucket: SectionBucket, collapsed: bool) -> None:
    """All-sections only: one foldable header per bucket (chevron + label +
    the same badges as the rail, painted by ``_DiagnosticsRowDelegate``)."""
    chevron = "▸" if collapsed else "▾"
    item = QListWidgetItem(f"{chevron} {bucket.label}")
    item.setFlags(Qt.ItemIsEnabled)  # visible + clickable, never selectable
    item.setData(_KIND_ROLE, "fold_header")
    item.setData(_FOLD_BUCKET_ROLE, bucket)
    item.setData(_FOLD_COLLAPSED_ROLE, collapsed)
    list_widget.addItem(item)


def _hidden_by_filters_text(count: int) -> str:
    """F8's pinned copy for the one quiet line a view renders when filters
    (toggled-off chips) hid something -- never rendered for a genuinely
    empty box/section (those keep the pinned ✓ wording instead, which
    claims truth; this line only ever claims view state)."""
    return f"{count} hidden by filters"


def _add_hidden_line_row(list_widget: QListWidget, count: int) -> None:
    _add_message_row(list_widget, _hidden_by_filters_text(count))


class _DiagnosticsRowDelegate(ParameterRowDelegate):
    """Detail-pane row painting on top of the shared row delegate.

    Only actionable rows (issue/task) show hover/selection -- a message/
    subhead/fold_header row paints flat whatever the mouse does, since a
    highlight promises interaction and activating one is a structural
    no-op. A ``fold_header`` row (All-sections only) gets its own custom
    paint: a shaded band, a bold chevron+label, and right-aligned count
    badges -- the same badges the rail paints for the same bucket.
    """

    _INTERACTIVE_KINDS = frozenset({"issue", "task"})
    _FOLD_HEADER_HEIGHT = 30

    def paint(self, painter, option, index) -> None:
        kind = index.data(_KIND_ROLE)
        if kind == "fold_header":
            self._paint_fold_header(painter, option, index)
            return
        if kind is not None and kind not in self._INTERACTIVE_KINDS:
            option = QStyleOptionViewItem(option)
            option.state &= ~(QStyle.State_MouseOver | QStyle.State_Selected)
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        if index.data(_KIND_ROLE) == "fold_header":
            return QSize(int(self._available_width(option)), self._FOLD_HEADER_HEIGHT)
        return super().sizeHint(option, index)

    def _paint_fold_header(self, painter, option, index) -> None:
        bucket: SectionBucket = index.data(_FOLD_BUCKET_ROLE)
        collapsed = bool(index.data(_FOLD_COLLAPSED_ROLE))

        painter.save()
        painter.fillRect(option.rect, QColor(style.RAIL_BG))
        painter.restore()

        specs = _bucket_badge_specs(bucket)
        badge_width = _measure_badge_specs(specs)
        chevron = "▸" if collapsed else "▾"
        text_rect = option.rect.adjusted(self._h_pad, 0, -(self._h_pad + badge_width), 0)

        painter.save()
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(style.MUTED))
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, f"{chevron}  {bucket.label}")
        painter.restore()

        if specs:
            badge_rect = option.rect.adjusted(0, 0, -self._h_pad, 0)
            _paint_badges(painter, badge_rect, specs)


class _ContentSizedList(QListWidget):
    """A ``QListWidget`` that reports its natural content height (the sum
    of its own rows' delegate ``sizeHint``s) as its ``sizeHint`` instead of
    the generic scroll-area default, and carries ``QSizePolicy.Minimum``
    vertically -- so it hugs exactly its own rows in a ``QVBoxLayout``
    rather than stretching to fill whatever space a sibling stretch factor
    would otherwise hand it (the wireframe's content-hugging group boxes,
    F2: a one-row Issues box must not become a ~300px empty card).
    ``updateGeometry()`` must be called after any change that can alter row
    count/height (every caller here does, right after populating)."""

    def sizeHint(self) -> QSize:
        width = super().sizeHint().width()
        height = 2 * self.frameWidth() + sum(
            self.sizeHintForRow(row) for row in range(self.count())
        )
        return QSize(width, height)


class _GroupBox(QFrame):
    """One F2 group box: a banded header (title + zero or more count badges)
    over a borderless list of rows that hugs its own content height
    (:class:`_ContentSizedList`) rather than stretching. Reused for both the
    Issues and the Outstanding box in ``_SectionDetailView`` -- Issues can
    show BOTH a red error badge and an amber warning badge at once (F5), the
    same ``_issue_badge_specs`` the rail/fold-header badges use, so the
    three surfaces can never disagree on what counts as "an issue badge";
    Outstanding never calls :meth:`set_badges` -- its ratio lives in the
    title text instead (:func:`_outstanding_box_title`)."""

    def __init__(self, title: str) -> None:
        super().__init__()
        self.setObjectName("DiagnosticsGroupBox")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("DiagnosticsGroupBoxHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(10, 6, 10, 6)
        self.title_text = ""
        self._title_label = panel_title("", object_name="DiagnosticsGroupBoxTitle")
        header_layout.addWidget(self._title_label)
        self._suffix_label = QLabel()
        self._suffix_label.setObjectName("DiagnosticsGroupBoxTitleSuffix")
        header_layout.addWidget(self._suffix_label)
        self.set_title(title)
        header_layout.addStretch(1)
        self._badge_row = QWidget()
        self._badge_layout = QHBoxLayout(self._badge_row)
        self._badge_layout.setContentsMargins(0, 0, 0, 0)
        self._badge_layout.setSpacing(4)
        header_layout.addWidget(self._badge_row)
        outer.addWidget(header)

        self.list = _ContentSizedList()
        self.list.setObjectName("DiagnosticsGroupBoxList")
        self.list.setFrameShape(QFrame.NoFrame)
        self.list.setWordWrap(True)
        self.list.setItemDelegate(_DiagnosticsRowDelegate(self.list))
        self.list.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        # A hugging list has no space of its own to scroll within -- any
        # overflow (a section with very many rows) is still reachable via
        # the pane's own outer scroll behaviour, not a nested scrollbar.
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        outer.addWidget(self.list)

    def refresh_content_size(self) -> None:
        """Tell the layout this box's preferred height may have changed --
        call after any ``self.list`` population (``QListWidget`` does not
        reliably propagate a custom ``sizeHint`` override on its own)."""
        self.list.updateGeometry()
        self.updateGeometry()

    def set_title(self, text: str) -> None:
        """Render *text* in the panel-title tier: the fixed word before
        " · " becomes the caps title; any ratio/count tail stays
        sentence-case in the muted suffix label (counts are information,
        not chrome). ``title_text`` keeps the verbatim string as the
        domain-facing seam -- ``tests/ui_driver.py`` reads it, because the
        caps rendering is presentation only."""
        self.title_text = text
        head, _, tail = text.partition(" · ")
        self._title_label.setText(head.upper())
        self._suffix_label.setText(f"· {tail}")
        self._suffix_label.setVisible(bool(tail))

    def set_badges(self, specs: list[tuple[str, str, str]]) -> None:
        """Replace the header's badges with one label per ``(text, bg, fg)``
        spec, left to right -- 0, 1 or 2 for Issues (:func:`_issue_badge_specs`);
        an empty list clears every badge (a clean bucket, F4)."""
        while self._badge_layout.count():
            item = self._badge_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        for text, bg, fg in specs:
            self._badge_layout.addWidget(badges.make_badge_label(text, bg, fg))


class _SectionDetailView(QWidget):
    """One selected section's Issues + Outstanding, each its own
    content-hugging group box, stacked at the top with the leftover space
    left below them (F2's wireframe) rather than the boxes splitting the
    pane's full height. The whole column sits in a plain (frameless)
    ``QScrollArea`` so a section with more rows than the pane's viewport
    height scrolls as a unit instead of either box clipping its own rows."""

    issue_activated = Signal(tuple)
    task_activated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setObjectName("DiagnosticsSectionScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        outer_layout.addWidget(scroll)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(12, 10, 12, 12)
        layout.setSpacing(10)

        self._header = QLabel()
        self._header.setObjectName("DiagnosticsPaneHeader")
        self._header.setWordWrap(True)
        layout.addWidget(self._header)

        self._issues_box = _GroupBox("Issues")
        self._issues_box.list.itemActivated.connect(self._on_issue_activated)
        layout.addWidget(self._issues_box)

        self._outstanding_box = _GroupBox("Outstanding")
        self._outstanding_box.list.itemActivated.connect(self._on_task_activated)
        layout.addWidget(self._outstanding_box)

        self._hidden_label = QLabel()
        self._hidden_label.setObjectName("DiagnosticsHiddenLine")
        self._hidden_label.setVisible(False)
        layout.addWidget(self._hidden_label)

        layout.addStretch(1)  # leftover space below the boxes, not inside them
        scroll.setWidget(content)

    def render(
        self,
        bucket: SectionBucket,
        partition: PartitionedIssues | None,
        model: str | None,
        filters: _FilterState,
    ) -> None:
        issue_count = len(bucket.issues)
        header_html = (
            f'<span style="font-weight:700;">{_html.escape(bucket.label)}</span>'
            f'<span style="color:{style.MUTED};">  ·  {issue_count} issue'
            f'{"s" if issue_count != 1 else ""} · {bucket.outstanding_count} outstanding</span>'
        )
        self._header.setText(header_html)
        hidden_issues = self._render_issues(bucket, filters)
        hidden_tasks = self._render_outstanding(bucket, partition, model, filters)
        self._set_hidden_count(hidden_issues + hidden_tasks)

    def _set_hidden_count(self, count: int) -> None:
        self._hidden_label.setVisible(count > 0)
        if count:
            self._hidden_label.setText(_hidden_by_filters_text(count))

    def _render_issues(self, bucket: SectionBucket, filters: _FilterState) -> int:
        lst = self._issues_box.list
        lst.clear()
        self._issues_box.set_badges(_issue_badge_specs(bucket))  # unfiltered truth (F8)
        if not bucket.issues:
            _add_message_row(lst, _MSG_NO_ISSUES)
            self._issues_box.refresh_content_size()
            return 0
        hidden = 0
        for diagnostic, nav_path in bucket.issues:
            if _issue_visible(diagnostic, filters):
                _add_issue_row(lst, bucket.label, diagnostic, nav_path)
            else:
                hidden += 1
        # A filter emptying the box entirely leaves it with zero rows and no
        # pinned message -- the box header/badge (already set above) stays
        # true, and the pane-level hidden line accounts for the rows (F8);
        # "no issues" would be a lie about content that still exists.
        self._issues_box.refresh_content_size()
        return hidden

    def _render_outstanding(
        self,
        bucket: SectionBucket,
        partition: PartitionedIssues | None,
        model: str | None,
        filters: _FilterState,
    ) -> int:
        lst = self._outstanding_box.list
        lst.clear()
        if model == "Partial":
            # decision C (revised): nothing is ever Required under Partial,
            # so there is no ratio to title with, and a bucket's own
            # required_tasks==()/required_total>0 shape is indistinguishable
            # from "fully filled" -- only model says which. But Partial does
            # carry NULL_FIELD tasks now, and their absorbed diagnostics must
            # stay reachable here (decision O: re-seated, never silenced), so
            # only the no-tasks case pins the notice; with tasks present the
            # shared rendering below runs unchanged.
            self._outstanding_box.set_title("Outstanding")
            if not bucket.optional_tasks:
                _add_message_row(lst, _MSG_PARTIAL_NO_TARGET)
                self._outstanding_box.refresh_content_size()
                return 0
        else:
            self._outstanding_box.set_title(_outstanding_box_title(bucket))
            if not bucket.required_tasks and not bucket.optional_tasks:
                _add_message_row(lst, _MSG_NOTHING_OUTSTANDING)
                self._outstanding_box.refresh_content_size()
                return 0

        hidden = 0
        required_rows = []
        for task in bucket.required_tasks:
            absorbed = _absorbed_messages(task, partition)
            if _task_visible(task, filters):
                required_rows.append((task, absorbed))
            else:
                hidden += 1
        for task, absorbed in required_rows:
            _add_task_row(lst, task, absorbed)

        if bucket.optional_tasks:
            optional_rows = []
            for task in bucket.optional_tasks:
                absorbed = _absorbed_messages(task, partition)
                if _task_visible(task, filters):
                    optional_rows.append((task, absorbed))
                else:
                    hidden += 1
            # The "OPTIONAL -- K unfilled" subhead is itself a header for the
            # rows beneath it -- like the box header, its own K is always
            # true (bucket.optional_tasks, unfiltered); but showing it over
            # zero surviving rows would orphan a header for nothing, so it
            # only renders when at least one optional row survives.
            if optional_rows:
                _add_subhead_row(lst, f"OPTIONAL - {len(bucket.optional_tasks)} UNFILLED")
                for task, absorbed in optional_rows:
                    _add_task_row(lst, task, absorbed)

        self._outstanding_box.refresh_content_size()
        return hidden

    def _on_issue_activated(self, item: QListWidgetItem) -> None:
        if item.data(_KIND_ROLE) == "issue":
            self.issue_activated.emit(item.data(_NAV_PATH_ROLE))

    def _on_task_activated(self, item: QListWidgetItem) -> None:
        if item.data(_KIND_ROLE) == "task":
            self.task_activated.emit(item.data(_TASK_ROLE))


class _AllSectionsView(QWidget):
    """The whole-document backup view (F3): every bucket exactly once, a
    foldable header over its issue rows then its outstanding rows under
    pinned-copy sub-heads. One QListWidget -- the simplest structure that
    keeps the keyboard/activation contract."""

    issue_activated = Signal(tuple)
    task_activated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(0)

        self._list = QListWidget()
        self._list.setObjectName("DiagnosticsAllSectionsList")
        self._list.setWordWrap(True)
        self._list.setItemDelegate(_DiagnosticsRowDelegate(self._list))
        self._list.itemActivated.connect(self._on_activated)
        self._list.itemClicked.connect(self._on_clicked)
        layout.addWidget(self._list)

        self._collapsed: set[tuple[str, ...]] = set()
        self._last_buckets: PageBuckets | None = None
        self._last_partition: PartitionedIssues | None = None
        self._last_filters = _FilterState()

    def reset_fold_state(self) -> None:
        self._collapsed.clear()

    def render(self, buckets: PageBuckets, partition: PartitionedIssues | None, filters: _FilterState) -> None:
        self._last_buckets = buckets
        self._last_partition = partition
        self._last_filters = filters
        self._list.clear()
        hidden_total = 0
        for bucket in buckets.buckets:
            collapsed = bucket.path in self._collapsed
            _add_fold_header_row(self._list, bucket, collapsed)  # unfiltered truth badges (F8)
            if collapsed:
                # A fold-hidden row is not a filter-hidden row (F8): it was
                # never even considered, so it contributes nothing to
                # hidden_total -- filters and folds compose independently.
                continue

            for diagnostic, nav_path in bucket.issues:
                if _issue_visible(diagnostic, filters):
                    _add_issue_row(self._list, bucket.label, diagnostic, nav_path)
                else:
                    hidden_total += 1

            if bucket.required_tasks:
                required_rows = []
                for task in bucket.required_tasks:
                    absorbed = _absorbed_messages(task, partition)
                    if _task_visible(task, filters):
                        required_rows.append((task, absorbed))
                    else:
                        hidden_total += 1
                if required_rows:
                    if not _is_declare_model_only(bucket):
                        _add_subhead_row(self._list, f"{bucket.label} - {_ratio_words(bucket)}")
                    for task, absorbed in required_rows:
                        _add_task_row(self._list, task, absorbed)

            if bucket.optional_tasks:
                optional_rows = []
                for task in bucket.optional_tasks:
                    absorbed = _absorbed_messages(task, partition)
                    if _task_visible(task, filters):
                        optional_rows.append((task, absorbed))
                    else:
                        hidden_total += 1
                if optional_rows:
                    _add_subhead_row(
                        self._list, f"{bucket.label} · optional - {len(bucket.optional_tasks)} unfilled"
                    )
                    for task, absorbed in optional_rows:
                        _add_task_row(self._list, task, absorbed)

        if hidden_total:
            _add_hidden_line_row(self._list, hidden_total)

    def _on_activated(self, item: QListWidgetItem) -> None:
        kind = item.data(_KIND_ROLE)
        if kind == "issue":
            self.issue_activated.emit(item.data(_NAV_PATH_ROLE))
        elif kind == "task":
            self.task_activated.emit(item.data(_TASK_ROLE))

    def _on_clicked(self, item: QListWidgetItem) -> None:
        if item.data(_KIND_ROLE) != "fold_header":
            return
        bucket: SectionBucket = item.data(_FOLD_BUCKET_ROLE)
        self._collapsed.symmetric_difference_update({bucket.path})
        if self._last_buckets is not None:
            self.render(self._last_buckets, self._last_partition, self._last_filters)


class _RailDelegate(ParameterRowDelegate):
    """Paints one rail entry: label (italic+grey when absent), right-aligned
    badges, and a 3px accent bar + tinted background when selected. Fully
    custom paint -- rail rows carry no HTML_ROLE -- inherits
    ParameterRowDelegate only for its _available_width helper."""

    _ACCENT_BAR = 3
    _ROW_HEIGHT = 32
    _SEPARATOR_HEIGHT = 9

    def sizeHint(self, option, index):
        if index.data(_RAIL_KIND_ROLE) == "separator":
            return QSize(int(self._available_width(option)), self._SEPARATOR_HEIGHT)
        return QSize(int(self._available_width(option)), self._ROW_HEIGHT)

    def paint(self, painter, option, index) -> None:
        kind = index.data(_RAIL_KIND_ROLE)
        if kind == "separator":
            self._paint_separator(painter, option)
            return

        painter.save()
        if option.state & QStyle.State_Selected:
            painter.fillRect(option.rect, QColor(style.RAIL_SELECTED_BG))
            bar = QRect(option.rect.left(), option.rect.top(), self._ACCENT_BAR, option.rect.height())
            painter.fillRect(bar, QColor(style.ACCENT))
        elif option.state & QStyle.State_MouseOver:
            painter.fillRect(option.rect, QColor(style.RAIL_HOVER_BG))
        painter.restore()

        absent = bool(index.data(_RAIL_ABSENT_ROLE))
        badge_specs = index.data(_RAIL_BADGE_ROLE) or []
        text = index.data(Qt.DisplayRole) or ""
        badge_width = _measure_badge_specs(badge_specs)
        label_rect = option.rect.adjusted(self._ACCENT_BAR + 10, 0, -(10 + badge_width), 0)

        painter.save()
        font = QFont(option.font)
        if absent:
            font.setItalic(True)
        painter.setFont(font)
        metrics = QFontMetrics(font)
        elided = metrics.elidedText(text, Qt.ElideRight, max(label_rect.width(), 0))
        painter.setPen(QColor(style.MUTED if absent else style.DEFAULT_TEXT))
        painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()

        if badge_specs:
            badge_rect = option.rect.adjusted(0, 0, -10, 0)
            _paint_badges(painter, badge_rect, badge_specs)

    def _paint_separator(self, painter, option) -> None:
        painter.save()
        painter.setPen(QPen(QColor(style.BORDER), 1))
        y = option.rect.center().y()
        painter.drawLine(option.rect.left() + 10, y, option.rect.right() - 10, y)
        painter.restore()


def _add_rail_entry_all(rail: QListWidget, buckets: PageBuckets) -> None:
    total = buckets.error_count + buckets.warning_count + buckets.outstanding_count
    item = QListWidgetItem("All sections")
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    item.setData(_RAIL_KIND_ROLE, "all")
    item.setData(_RAIL_ABSENT_ROLE, False)
    badge_specs = [(str(total), style.NEUTRAL_TINT, style.DEFAULT_TEXT)] if total else []
    item.setData(_RAIL_BADGE_ROLE, badge_specs)
    item.setToolTip(style.counts_tooltip(buckets.error_count, buckets.warning_count, buckets.outstanding_count))
    rail.addItem(item)


def _add_rail_separator(rail: QListWidget) -> None:
    item = QListWidgetItem("")
    item.setFlags(Qt.NoItemFlags)
    item.setData(_RAIL_KIND_ROLE, "separator")
    rail.addItem(item)


def _add_rail_entry_section(rail: QListWidget, bucket: SectionBucket) -> None:
    item = QListWidgetItem(bucket.label)
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
    item.setData(_RAIL_KIND_ROLE, "section")
    item.setData(_RAIL_PATH_ROLE, bucket.path)
    item.setData(_RAIL_ABSENT_ROLE, bucket.absent)
    item.setData(_RAIL_BADGE_ROLE, _bucket_badge_specs(bucket))
    item.setToolTip(style.counts_tooltip(bucket.error_count, bucket.warning_count, bucket.outstanding_count))
    rail.addItem(item)


class _RailList(QListWidget):
    """The left section rail. Selection (click or arrow keys) switches the
    pane immediately and never mutates the document -- unlike every other
    list in this module, this one acts on plain selection, not activation,
    because switching the pane is navigation of the page itself, not the
    document."""

    selection_changed = Signal(object)  # _ALL_SECTIONS_KEY | bucket.path

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiagnosticsRail")
        self.setItemDelegate(_RailDelegate(self))
        self.setFocusPolicy(Qt.StrongFocus)
        self.currentItemChanged.connect(self._on_current_changed)

    def _on_current_changed(self, current: QListWidgetItem | None, _previous) -> None:
        if current is None:
            return
        kind = current.data(_RAIL_KIND_ROLE)
        if kind == "all":
            self.selection_changed.emit(_ALL_SECTIONS_KEY)
        elif kind == "section":
            self.selection_changed.emit(current.data(_RAIL_PATH_ROLE))


def _chip_html(svg: str, color: str, text: str, *, on: bool) -> str:
    """*on* controls the chip's own colours (F8) -- when a chip is toggled
    off, both its dot and its count text go ``style.MUTED``, on top of the
    "off" QSS state (:data:`_FilterChip`) that greys its card background:
    visibly muted/pressed-out, never merely relabelled."""
    icon_color = color if on else style.MUTED
    text_color = style.DEFAULT_TEXT if on else style.MUTED
    icon = icons.html_img(svg, color=icon_color, size=parameter_row.MARK_BOX)
    return f'{icon}<span style="color:{text_color};">  {_html.escape(text)}</span>'


class _FilterChip(QLabel):
    """One strip chip, also a click-toggle filter (F8). Stays a ``QLabel``
    (not a ``QPushButton``) so it keeps rendering its rich-text icon+count
    content (a coloured dot plus text, :func:`_chip_html`) -- native Qt
    buttons render ``text()`` as plain text, not HTML. Interactivity is
    layered on with :meth:`mousePressEvent` and a dynamic "off" QSS
    property, the same pattern ``QPushButton#AddParameterCreate``'s own
    "selected" property already uses in this stylesheet."""

    toggled = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiagnosticsChip")
        self.setCursor(Qt.PointingHandCursor)
        self._on = True

    def is_on(self) -> bool:
        return self._on

    def set_on(self, on: bool) -> None:
        """Set the toggle state without emitting :attr:`toggled` -- used by
        programmatic resets (:meth:`_SummaryStrip.reset_filters`), which
        must not re-enter the filter-change/render path while a *different*
        document's buckets are still being assembled."""
        self._on = on
        self.setProperty("chipOff", not on)
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.set_on(not self._on)
        self.toggled.emit(self._on)


class _SummaryStrip(QWidget):
    """Top band: three toggleable count-filter chips (F8; F2 phase A had
    them static), each its own bordered, rounded card on the shaded strip
    band (the wireframe's "boxes/shading to make regions distinguishable").
    Filtering here is purely a VIEW concern -- this widget owns the filter
    *state* (chip on/off) and reports it via :meth:`filter_state`; it never
    touches counts, badges or buckets itself (:class:`DiagnosticsPanel`
    reads the state and re-renders the pane -- see F8's "view-only" rule).
    F8's companion text-filter field was removed by explicit user decision;
    the chips are the whole filter surface."""

    #: Emitted whenever a chip is toggled -- DiagnosticsPanel re-renders
    #: only the *pane* on this signal (never a full ``refresh()``), so
    #: toggling can never re-enter the document-wide refresh path.
    filters_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiagnosticsSummaryStrip")
        # A plain QWidget subclass ignores stylesheet background/border
        # unless told to paint them (see ActivityBar/PageHeader's own note);
        # without this the strip's border-bottom silently never draws.
        self.setAttribute(Qt.WA_StyledBackground, True)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(10)

        self._counts = (0, 0, 0)

        self._errors = _FilterChip()
        self._warnings = _FilterChip()
        self._outstanding = _FilterChip()
        for chip in (self._errors, self._warnings, self._outstanding):
            chip.toggled.connect(self._on_chip_toggled)
            layout.addWidget(chip)

        layout.addStretch(1)

    def set_counts(self, errors: int, warnings: int, outstanding: int) -> None:
        self._counts = (errors, warnings, outstanding)
        self._refresh_chip_text()
        # Tooltips stay truthful regardless of on/off state (F8): they
        # always describe the real, unfiltered counts.
        self._errors.setToolTip(style.error_count_tooltip(errors))
        self._warnings.setToolTip(style.warning_count_tooltip(warnings))
        self._outstanding.setToolTip(style.outstanding_count_tooltip(outstanding))

    def filter_state(self) -> _FilterState:
        return _FilterState(
            error_on=self._errors.is_on(),
            warning_on=self._warnings.is_on(),
            outstanding_on=self._outstanding.is_on(),
        )

    def reset_filters(self) -> None:
        """Back to all-on -- called only on a *different* document
        (:meth:`DiagnosticsPanel.reset_view_state`), never on an ordinary
        refresh, where persisting is the point (F8)."""
        for chip in (self._errors, self._warnings, self._outstanding):
            chip.set_on(True)
        self._refresh_chip_text()

    def _refresh_chip_text(self) -> None:
        errors, warnings, outstanding = self._counts
        self._errors.setText(
            _chip_html(
                icons.DOT, style.ERROR, f"{errors} error{'s' if errors != 1 else ''}", on=self._errors.is_on()
            )
        )
        self._warnings.setText(
            _chip_html(
                icons.DOT,
                style.WARNING,
                f"{warnings} warning{'s' if warnings != 1 else ''}",
                on=self._warnings.is_on(),
            )
        )
        self._outstanding.setText(
            _chip_html(icons.RING, style.MUTED, f"{outstanding} outstanding", on=self._outstanding.is_on())
        )

    def _on_chip_toggled(self, _on: bool) -> None:
        self._refresh_chip_text()
        self.filters_changed.emit()


class DiagnosticsPanel(QWidget):
    """Renders the Diagnostics page: summary strip + rail + detail pane.

    Shows an explanatory placeholder instead of the page only when there is
    no document at all -- once a document is open, the strip/rail/pane are
    always present (mirrors the Inspector's Issues tab convention of never
    showing a truly blank area).
    """

    issue_activated = Signal(tuple)
    task_activated = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._stack = QStackedWidget()

        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._strip = _SummaryStrip()
        self._strip.filters_changed.connect(self._on_filters_changed)
        content_layout.addWidget(self._strip)

        body = QWidget()
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        self._rail = _RailList()
        self._rail.setFixedWidth(200)
        self._rail.selection_changed.connect(self._on_rail_selection_changed)
        body_layout.addWidget(self._rail)

        self._pane_stack = QStackedWidget()
        self._section_view = _SectionDetailView()
        self._section_view.issue_activated.connect(self.issue_activated)
        self._section_view.task_activated.connect(self.task_activated)
        self._all_view = _AllSectionsView()
        self._all_view.issue_activated.connect(self.issue_activated)
        self._all_view.task_activated.connect(self.task_activated)
        self._pane_stack.addWidget(self._section_view)
        self._pane_stack.addWidget(self._all_view)
        body_layout.addWidget(self._pane_stack, 1)

        content_layout.addWidget(body, 1)
        self._stack.addWidget(content)

        self._placeholder = QLabel(_MSG_NO_DOCUMENT)
        self._placeholder.setObjectName("IssuesPlaceholder")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setWordWrap(True)
        self._stack.addWidget(self._placeholder)

        layout.addWidget(self._stack)
        self._stack.setCurrentIndex(1)

        self._buckets: PageBuckets | None = None
        self._partition: PartitionedIssues | None = None
        self._model: str | None = None
        self._selected_key: tuple[str, ...] | str = _ALL_SECTIONS_KEY

    def reset_view_state(self) -> None:
        self._selected_key = _ALL_SECTIONS_KEY
        self._all_view.reset_fold_state()
        self._strip.reset_filters()

    def refresh(
        self, buckets: PageBuckets | None, partition: PartitionedIssues | None, model: str | None
    ) -> None:
        """Rebuild the strip, rail and detail pane from one derivation
        point's output.

        *buckets* is ``core.page_buckets.bucket_page_content``'s result --
        computed once in ``main_window._refresh_all`` alongside the rail
        badge, so this panel and the badge can never disagree (decision G).
        *partition* is passed through only for its ``absorbed_by_task``
        lookup (decision O's secondary text); *model* only for the Partial
        notice (see :data:`_MSG_PARTIAL_NO_TARGET`) -- every grouping/count
        this panel renders otherwise comes from *buckets* alone.
        """
        self._buckets = buckets
        self._partition = partition
        self._model = model
        if buckets is None:
            self._placeholder.setText(_MSG_NO_DOCUMENT)
            self._stack.setCurrentIndex(1)
            return
        self._strip.set_counts(buckets.error_count, buckets.warning_count, buckets.outstanding_count)
        self._rebuild_rail()
        self._stack.setCurrentIndex(0)

    def _rebuild_rail(self) -> None:
        assert self._buckets is not None
        self._rail.blockSignals(True)
        self._rail.clear()
        _add_rail_entry_all(self._rail, self._buckets)
        _add_rail_separator(self._rail)
        for bucket in self._buckets.buckets:
            _add_rail_entry_section(self._rail, bucket)

        target_row = 0
        if self._selected_key != _ALL_SECTIONS_KEY:
            found = False
            for row in range(self._rail.count()):
                item = self._rail.item(row)
                if item.data(_RAIL_KIND_ROLE) == "section" and item.data(_RAIL_PATH_ROLE) == self._selected_key:
                    target_row = row
                    found = True
                    break
            if not found:
                self._selected_key = _ALL_SECTIONS_KEY
        self._rail.setCurrentRow(target_row)
        self._rail.blockSignals(False)
        self._render_pane()

    def _on_rail_selection_changed(self, key) -> None:
        self._selected_key = key
        self._render_pane()

    def _on_filters_changed(self) -> None:
        """A chip toggled (F8) -- re-render only
        the pane, never a full ``refresh()``: filters are view-only and
        must never re-enter the document-wide refresh path (rail badges,
        strip counts and the app badge are untouched by this call)."""
        self._render_pane()

    def _render_pane(self) -> None:
        if self._buckets is None:
            return
        filters = self._strip.filter_state()
        # Always keep the All-sections view current, even while a single
        # section is showing: it is the F3 backup view (nothing renders
        # there that isn't already counted in the strip/rail), and a stale
        # copy sitting behind the visible section pane would quietly break
        # that promise the moment the user (or a test) switches back to it.
        self._all_view.render(self._buckets, self._partition, filters)
        if self._selected_key != _ALL_SECTIONS_KEY:
            bucket = next((b for b in self._buckets.buckets if b.path == self._selected_key), None)
            if bucket is not None:
                self._pane_stack.setCurrentWidget(self._section_view)
                self._section_view.render(bucket, self._partition, self._model, filters)
                return
            self._selected_key = _ALL_SECTIONS_KEY
        self._pane_stack.setCurrentWidget(self._all_view)
        self._all_view.render(self._buckets, self._partition, filters)
