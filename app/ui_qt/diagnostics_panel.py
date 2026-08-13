"""Diagnostics page: one scrolling stream + a filter column, built on
``core.page_buckets``. A single renderer over a single dataset, replacing
a previous rail + two-renderer (single-section pane / "All sections"
backup pane) layout, so there is nothing left that could drift out of
sync with itself.

``bucket_page_content`` makes every grouping/absorption decision once,
inward of the UI: this module renders its ``PageBuckets`` output and
nothing else -- it never re-derives which section an issue or task belongs
to. Re-deriving that here is exactly what put Issues and Outstanding
grouping out of sync with each other before (see ``core.page_buckets``'s
own module docstring).

Layout:

* A **filter column** down the right -- a "Collapse all"/"Expand all"
  affordance shown once two or more sections render, then a "FILTER"
  category label over three toggleable count filters (errors, warnings,
  outstanding), counts from ``PageBuckets`` totals. Fixed width, flat text,
  one left edge: four peer items, not a control band.
* A **file-facts group** ahead of every bucket: the stream's own
  statement of the load-time facts ``core.load_record.LoadRecord``/
  ``BPXDocument.validation_reach`` already carry (a legacy v0.x
  conversion, an aborted checking run, YAML comments a save would
  destroy) -- see :mod:`ui_qt.file_facts` for the facts themselves. One
  quiet, muted-dot row per fact under a fold header exactly like a
  section bucket's own (foldable, in Collapse all/Expand all, never
  dismissible), exempt from the three chips (computed outside the filter
  path, like the clear line). Renders only while at least one fact exists
  -- the everyday clean file adds nothing.
* A **stream** (``_StreamView``, one ``QListWidget``) below it: only
  sections that have something in them render -- a bucket with zero
  errors/warnings/outstanding is *clear* and is named instead on one
  foldable footer line at the bottom, so the page's length tracks the
  amount of work rather than the size of the schema. A rendered section
  gets one foldable header (chevron + bold label + a muted words-only
  suffix built from whichever counts are nonzero -- never a count
  badge) over its issue rows then its outstanding rows, the optional ones
  under a quiet "OPTIONAL · K UNFILLED" sub-head. A genuinely clean
  document or a Partial document with nothing outstanding (the
  Partial notice, pinned copy) gets one pinned, non-activatable row above
  the clear line instead of a bare absence.

Row anatomy: an issue row's severity is a small delegate-painted
filled-circle icon (:data:`ui_qt.parameter_row.SEVERITY_ROLE`) -- red X for
an error, amber ! for a warning -- replacing the old bracketed
``[ERROR]``/``[WARN]`` text tag. This is a shared change to
``ParameterRowDelegate`` itself, so the Inspector's Issues tab
(:mod:`ui_qt.issues_view`) picks it up too. When the validator's own
offending value is a real number, it is appended after the message with the
app's " · " separator (:func:`core.validation.input_fact`) -- e.g. "... ·
input -0.3" -- via the shared :func:`ui_qt.parameter_row.
compose_issue_row_html`, so both surfaces show it identically; the verbatim
message itself is never altered. A task row keeps its own glyph
(a hollow circle for "missing", a half-filled circle for a committed null),
bold name + muted unit, a REQUIRED tag where applicable, the absorbed
validator message as muted secondary text, and -- task rows only --
its action ("Go to (right chevron)"/"+ Add section"/"Choose...") always
visible in accent colour; an issue row carries no trailing action text,
activation stays Enter/double-click as for every other row.

Activation contract: Enter/double-click only, selection alone never acts.
The stream exposes the same ``issue_activated``/``task_activated`` signals
this panel forwards unmodified to ``MainWindow`` (``_on_task_activated``).
A Document-bucket issue row's nav_path is whatever the diagnostic-attachment
pass resolved (its nearest existing ancestor, or empty when nothing
resolves); ``NavigationService.navigate`` already no-ops on an empty path,
so "no attachment point -> no-op" needs no special-casing here.

View state (one primary document, no module-level globals) lives on this
panel instance: the per-section fold set, the clear line's own
expanded/collapsed flag, and the column's chip filter state. All of it
persists across an ordinary ``refresh`` (a commit, undo/redo) and resets
via :meth:`reset_view_state`, called by ``MainWindow`` only when a
*different* document replaces the session (open/new) -- mirrors the
parameter list's own expansion-state convention.
"""

from __future__ import annotations

import html as _html
from dataclasses import dataclass

from PySide6.QtCore import QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QStackedWidget,
    QStyle,
    QStyleOptionViewItem,
    QVBoxLayout,
    QWidget,
)

from core.bpx_gateway import CheckReach, section_checked
from core.completion import CompletionTask, PartitionedIssues, TaskKind
from core.page_buckets import (
    DOCUMENT_BUCKET_PATH,
    PageBuckets,
    SectionBucket,
    strip_parameterisation_prefix,
)
from core.validation import Severity, input_fact, merge_union_pair

from . import icons, parameter_row, style, typography
from .activating_list import ActivatingList
from .file_facts import FileFact
from .parameter_row import ParameterRowDelegate

_MSG_NO_DOCUMENT = "No document open"
#: The filter column's fixed width -- the same 250px the app's other
#: secondary columns use (``reference_library_dialog``'s picker,
#: ``cards/database_examples_dialog``'s compare-with rail), so a page that
#: gained a side column doesn't invent a second column measure.
_COLUMN_WIDTH = 250
#: Pinned Partial-model notice. A bucket alone cannot tell "Partial, so
#: nothing is ever tracked" apart from "concrete model, fully filled,
#: nothing remaining" -- both look identical from bucket data (zero
#: ``required_tasks``, nonzero ``required_total``) -- so this is the one
#: place ``model`` reaches this module (:meth:`_StreamView.render`), a
#: narrow, deliberate exception to "consume only PageBuckets" (grouping/
#: counting logic itself stays entirely bucket-derived). Page-level now
#: (one row, once), not per-section as before -- a bucket alone still can't
#: tell the two shapes apart, but the whole-page ``outstanding_count``
#: total can.
_MSG_PARTIAL_NO_TARGET = (
    "Model is Partial, so there is no completion target. Expected fields "
    "are still suggested in each section's parameter list."
)

_ACTION_GO_TO = "Go to ▸"
_ACTION_ADD_SECTION = "+ Add section"
_ACTION_CHOOSE = "Choose…"

#: The file-facts group's sentinel fold-state path -- unlike
#: :data:`DOCUMENT_BUCKET_PATH` (``()``) or a real section path (schema
#: property names), this literal token can never collide with one, so it
#: shares :class:`_StreamView`'s one ``_collapsed`` set safely.
_FILE_FACTS_PATH: tuple[str, ...] = ("__file_facts__",)

#: Task-row glyphs: a hollow circle for "nothing committed yet"
#: (MISSING_FIELD/MISSING_SECTION/DECLARE_MODEL), a half-filled circle for
#: "committed, but null" (NULL_FIELD) -- the same missing/added-no-value
#: distinction drawn in prose, made visible at a glance. Plain
#: Unicode glyphs, used only for a task item's underlying (non-painted)
#: ``QListWidgetItem`` text -- the delegate always paints the row's
#: :data:`parameter_row.HTML_ROLE` fragment instead (see :func:`_task_glyph_svg`
#: for that rich-text counterpart, the shared dot family from :mod:`ui_qt.icons`).
_GLYPH_MISSING = "○"
_GLYPH_NULL = "◐"

#: Item-data roles for the stream list.
#: 256 is the pre-existing nav-path role "issue" rows carry (kept unchanged
#: so nothing downstream that reads it needs to know this file changed).
_NAV_PATH_ROLE = 256
_KIND_ROLE = Qt.UserRole + 300  # issue|task|message|subhead|fold_header|clear_summary|clear_row|all_clear
_TASK_ROLE = Qt.UserRole + 301
#: :class:`_FoldHeader` for "fold_header" rows (the path/label/suffix that
#: header is for -- a section bucket's own header and the file-facts
#: group's own header share this one shape) and ``SectionBucket`` for
#: "clear_row" rows (the clear bucket that row names, so an absent one can
#: still be painted italic from its own real font; see
#: :meth:`_DiagnosticsRowDelegate._paint_clear_row`).
_FOLD_BUCKET_ROLE = Qt.UserRole + 302
_FOLD_COLLAPSED_ROLE = Qt.UserRole + 303  # "fold_header" rows only


# ---------------------------------------------------------------------------
# View-only filtering. Rows are hidden by ``_add_section`` (below) after it
# already has its bucket's true, unfiltered content in hand -- ``core.page_
# buckets`` is never touched, so the column's counts/the app badge/the reconciliation
# test all keep reading the same unfiltered ``PageBuckets`` this module
# always has. ``_FilterState`` and the two visibility predicates below are
# the one shared, pure "does this row survive the filter" rule the stream
# consumes.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _FilterState:
    """Per-session view-only filter state. All-on is the default --
    i.e. "no filtering". (The text filter was removed: per-section buckets
    are small and the toolbar search already finds anything by name --
    the chips alone remain.)"""

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
# Outstanding-row / issue-row content, shared by every row the stream builds.
# ---------------------------------------------------------------------------


def _relative_location(bucket_label: str, nav_path: tuple[str, ...]) -> str:
    """The issue's location *within* its bucket -- the bucket label is the
    box/fold header above it, so it's dropped. Handles both a canonical,
    resolved path (``("Parameterisation", "Cell", "X")`` for the "Cell"
    bucket) and a leading-prefix-stripped, unresolved one
    (``("Cell", "X")``, the validator's own leading-prefix-dropped
    convention) the same way: strip a leading "Parameterisation" wrapper
    via the one shared owner of that
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
    ``document_completion`` always returns DECLARE_MODEL alone,
    so a group holding it is never a section-shape fact ("Header -- 1 of 3
    remaining" would read indirectly when the one actionable thing is
    declaring a model). Such a group renders no ratio at all."""
    return len(bucket.required_tasks) == 1 and bucket.required_tasks[0].kind is TaskKind.DECLARE_MODEL


def _required_field_tasks(bucket: SectionBucket) -> tuple[CompletionTask, ...]:
    """*bucket.required_tasks* minus any MISSING_SECTION entries.

    A present section's absent CHILD sections are bucketed together with
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
    (Document's fallback: "N remaining") -- the outstanding part of a
    rendered (non-clear) section's header suffix
    (:func:`_section_header_suffix`); a *clear* bucket's own clear-row
    wording is unrelated (:func:`_clear_row_text` does not call this).

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


#: Task kinds whose row already *is* "this field is not here". A ``missing``
#: diagnostic absorbed into one of them can only restate the row it sits
#: under, by construction of ``partition_issues`` rule (a) -- it matched
#: precisely because both describe the same absent field.
_MISSING_TASK_KINDS = (TaskKind.MISSING_FIELD, TaskKind.MISSING_SECTION)


def _absorbed_messages(task: CompletionTask, partition: PartitionedIssues | None) -> tuple[str, ...]:
    """The real validator messages *task* stands in for, merging
    a float/int union pair the same way the Issues surfaces do.

    A ``missing`` diagnostic under a MISSING task is dropped: the row above
    it already carries the field's name and its (REQUIRED) tag, so printing
    the validator's "Field required" beneath said the same thing twice on
    every one of thirty-five rows. This is a structural test, not a reading
    of the validator's words -- absorption matched these two *because* they
    describe the same absent field. Every other absorbed message still
    prints, including a NULL_FIELD's, where the validator has something the
    row does not say (what was wrong with the value that is there).
    """
    if partition is None:
        return ()
    pairs = partition.absorbed_by_task.get(task, ())
    if task.kind in _MISSING_TASK_KINDS:
        pairs = tuple(
            pair for pair in pairs if getattr(pair[0], "error_type", None) != "missing"
        )
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
    """Return ``(name, note, action)`` for one task, per the pinned copy
    table (the NULL_FIELD suffix reads "No Value", not the old "added, no
    value yet" -- shortened 2026-08-05; ``style.task_kind_tooltip``'s own
    wording is a different surface and is untouched)."""
    if task.kind is TaskKind.MISSING_FIELD:
        return task.alias, None, _ACTION_GO_TO
    if task.kind is TaskKind.NULL_FIELD:
        return task.alias, "No Value", _ACTION_GO_TO
    if task.kind is TaskKind.MISSING_SECTION:
        return task.path[-1], None, _ACTION_ADD_SECTION
    return "Declare a model", None, _ACTION_CHOOSE  # DECLARE_MODEL


def _task_row_text(task: CompletionTask, absorbed_messages: tuple[str, ...]) -> str:
    glyph = _task_glyph(task)
    name, note, action = _task_label(task)
    label = f"{name} · {note}" if note else name
    text = f"{glyph} {label}"
    if task.required:
        text += "  (REQUIRED)"
    text += f"  {action}"
    if absorbed_messages:
        text += "  · " + "; ".join(absorbed_messages)
    return text


def _task_row_html(task: CompletionTask, absorbed_messages: tuple[str, ...]) -> str:
    """REQUIRED sits inline right after the name; the action text
    itself is NOT part of this HTML fragment -- it is painted separately,
    right-aligned, by the delegate (see :data:`parameter_row.ACTION_ROLE`,
    set by :func:`_add_task_row`) so it never competes with a long name for
    the same line.

    The ring/half-filled mark is painted in ``style.MUTED``
    (the same grey #57606a family) to harmonise with the issue rows' flat
    severity dots, rather than swept up in the bold name span."""
    glyph_img = icons.html_img(_task_glyph_svg(task), color=style.MUTED, size=parameter_row.MARK_BOX)
    name, note, action = _task_label(task)
    label = f"{name} · {note}" if note else name
    hints: list[tuple[str, str]] = []
    if task.required:
        hints.append(("REQUIRED", style.REQUIRED))
    name_fragment = parameter_row.compose_row_html(label, hints, name_color=style.DEFAULT_TEXT)
    fragment = f"{glyph_img}  {name_fragment}"
    if absorbed_messages:
        secondary = "<br>".join(
            f'<span style="color:{style.MUTED}; {typography.size_qss(typography.META)}">{_html.escape(message)}</span>'
            for message in absorbed_messages
        )
        fragment += "<br>" + secondary
    return fragment


# ---------------------------------------------------------------------------
# Row builders -- shared by ``_StreamView``.
# ---------------------------------------------------------------------------


def _add_issue_row(list_widget: QListWidget, bucket_label: str, diagnostic, nav_path: tuple[str, ...]) -> None:
    is_error = diagnostic.severity == Severity.ERROR
    label = "ERROR" if is_error else "WARN"
    location = _relative_location(bucket_label, nav_path)
    plain_loc = location or _EMPTY_LOCATION_LABEL
    # The offending value, when the validator captured a real number --
    # see core.validation.input_fact's own fidelity rule. bucket.issues has
    # already been through merge_union_pair (core.page_buckets.
    # bucket_page_content, once per document), so a FloatInt union pair
    # never reaches here twice.
    fact = input_fact(diagnostic)
    message = f"{diagnostic.message} · {fact}" if fact else diagnostic.message
    item = QListWidgetItem(f"[{label}] {plain_loc}: {message}")
    item.setData(parameter_row.HTML_ROLE, parameter_row.compose_issue_row_html(location, diagnostic.message, fact))
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
    """A quiet, non-activatable, muted single line -- the Partial notice
    today. A per-section empty state is unreachable: a bucket with nothing
    in it simply does not render."""
    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "message")
    item.setForeground(QColor(style.MUTED))
    list_widget.addItem(item)


def _add_subhead_row(list_widget: QListWidget, text: str) -> None:
    """A quiet, non-activatable sub-head row -- today only the section's own
    "K optional parameters unfilled" line: a plain sentence, stating the
    count once. The required group's own ratio ("N of M remaining") lives
    in the section's fold header instead, so it is never repeated here."""
    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "subhead")
    item.setData(parameter_row.HTML_ROLE, parameter_row.compose_row_html(text, [], name_color=style.MUTED))
    list_widget.addItem(item)


def _section_header_suffix(bucket: SectionBucket) -> str:
    """The muted words after a rendered section's bold label: whichever
    of "N error(s)"/"N warning(s)"/the outstanding ratio are actually
    nonzero, joined with " · " (U+00B7 middle dot, never a plain period)
    -- never a count badge. This is the module's one place a
    count is spelled out, replacing four separate badges (rail, fold
    header, box badge, box title) that used to say the same number.

    The ratio part only appears when ``bucket.required_tasks`` itself is
    non-empty -- :func:`_ratio_words` answers "how much REQUIRED work is
    left", and a bucket whose only outstanding work is optional (empty
    ``required_tasks``, nonzero ``required_total``) would otherwise read
    "0 of N remaining", falsely implying N fields are required when none
    are missing. Such a bucket still renders (it isn't clear) with a
    bare label; its OPTIONAL sub-head says what the outstanding work
    actually is."""
    parts: list[str] = []
    if bucket.error_count:
        parts.append(f"{bucket.error_count} error{'s' if bucket.error_count != 1 else ''}")
    if bucket.warning_count:
        parts.append(f"{bucket.warning_count} warning{'s' if bucket.warning_count != 1 else ''}")
    if bucket.required_tasks and not _is_declare_model_only(bucket):
        parts.append(_ratio_words(bucket))
    return " · ".join(parts)


@dataclass(frozen=True)
class _FoldHeader:
    """One banded fold-header row's path/label/suffix -- generalised off
    ``SectionBucket`` so the file-facts group can reuse the very same
    header machinery a section bucket does, keyed by its own sentinel path
    (:data:`_FILE_FACTS_PATH`) rather than a faked-up bucket. *path* is also
    the fold-state key stored in :attr:`_StreamView._collapsed`."""

    path: tuple[str, ...]
    label: str
    suffix: str


def _add_fold_header_row(list_widget: QListWidget, header: _FoldHeader, collapsed: bool) -> None:
    """One foldable header row: chevron + bold label + the muted words-only
    suffix, painted as a shaded band by :class:`_DiagnosticsRowDelegate`.
    The plain text below already carries the suffix (unlike the old
    rail/fold-header badges, which were paint-only) --
    ``diagnostics_stream_headers()`` reads it directly."""
    chevron = "▸" if collapsed else "▾"
    text = f"{chevron} {header.label}" + (f"  {header.suffix}" if header.suffix else "")
    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)  # visible + clickable, never selectable
    item.setData(_KIND_ROLE, "fold_header")
    item.setData(_FOLD_BUCKET_ROLE, header)
    item.setData(_FOLD_COLLAPSED_ROLE, collapsed)
    list_widget.addItem(item)


def _bucket_is_clear(bucket: SectionBucket) -> bool:
    """The definition of "nothing to show" -- from unfiltered truth, so a
    filter never changes which buckets count as clear."""
    return bucket.error_count == 0 and bucket.warning_count == 0 and bucket.outstanding_count == 0


def _page_is_clear(buckets: PageBuckets) -> bool:
    """The whole-document condition for the pinned all-clear row."""
    return buckets.error_count == 0 and buckets.warning_count == 0 and buckets.outstanding_count == 0


def _clear_line_text(checked: int, unchecked: int) -> str:
    """The clear line's words, split by what ``bpx`` actually judged.

    "Clear" is a verdict, so it may only cover buckets whose stage the run
    reached; a bucket beyond an aborted run's reach was never examined and
    reads "not checked" instead. Both words come from the same checking-
    stage ladder -- the line never vouches for an unexamined section and
    never disowns a judged one.
    """
    if not unchecked:
        return f"{checked} section{'s' if checked != 1 else ''} clear"
    if not checked:
        return f"{unchecked} section{'s' if unchecked != 1 else ''} not checked"
    return f"{checked} section{'s' if checked != 1 else ''} clear · {unchecked} not checked"


def _add_clear_summary_row(
    list_widget: QListWidget,
    checked: int,
    unchecked: int,
    expanded: bool,
    reach: CheckReach = CheckReach.COMPLETE,
) -> None:
    """The clear line: one collapsed/expanded footer row naming every
    clear bucket at once. Its own single-click fold is independent of any
    per-section fold state -- toggled by :meth:`_StreamView._on_clicked`,
    tracked on :attr:`_StreamView._clear_expanded`, not per-row data."""
    chevron = "▾" if expanded else "▸"
    item = QListWidgetItem(f"{chevron} {_clear_line_text(checked, unchecked)}")
    item.setFlags(Qt.ItemIsEnabled)  # visible + clickable, never selectable
    item.setData(_KIND_ROLE, "clear_summary")
    # Only the "not checked" half of the line needs explaining; a line that is
    # all clear says everything already.
    if unchecked:
        item.setToolTip(style.not_checked_tooltip(reach))
    list_widget.addItem(item)


def _clear_row_text(bucket: SectionBucket, checked: bool = True) -> str:
    # Absence is the stronger fact (visible in the file itself); after it,
    # an unexamined bucket states so instead of its filled count -- a
    # completion tally next to no verdict would read as one.
    if bucket.absent:
        return f"{bucket.label} · section absent"
    if not checked:
        return f"{bucket.label} · not checked"
    if bucket.required_total:
        return f"{bucket.label} · {bucket.required_total} of {bucket.required_total} filled"
    return bucket.label


def _add_clear_row(
    list_widget: QListWidget,
    bucket: SectionBucket,
    checked: bool = True,
    reach: CheckReach = CheckReach.COMPLETE,
) -> None:
    """One quiet, non-activatable row per clear bucket, shown only while
    the clear line is expanded -- the positive completion signal the
    old rail's quiet, badge-less entries used to carry.

    Rendered the same way the OPTIONAL sub-head is (:func:`_add_subhead_row`):
    one muted :func:`~ui_qt.parameter_row.compose_row_html` span, wrapped in
    ``<i>`` for an absent bucket (the same "muted italic" idiom
    ``parameter_row.build_ghost_row_html`` already uses for a reference-only
    ghost row) -- reusing the shared HTML-document sizeHint path is what
    keeps this row's height and colour identical to every other single-line
    row on the page, rather than a bespoke custom paint that a review found
    rendering tall with accent-tinted digits."""
    text = _clear_row_text(bucket, checked)
    item = QListWidgetItem(text)
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "clear_row")
    if not checked:
        item.setToolTip(style.not_checked_tooltip(reach))
    fragment = parameter_row.compose_row_html(text, [], name_color=style.MUTED)
    if bucket.absent:
        fragment = f"<i>{fragment}</i>"
    item.setData(parameter_row.HTML_ROLE, fragment)
    list_widget.addItem(item)


# ---------------------------------------------------------------------------
# The file-facts group -- ahead of every bucket, its own fold header
# (:func:`_add_fold_header_row`, the same machinery a section bucket uses)
# plus one quiet row per fact. Like the clear line/all-clear row, this is
# computed straight from unfiltered truth -- the three chips never touch it.
# ---------------------------------------------------------------------------


def _file_facts_suffix(count: int) -> str:
    return f"{count} note" if count == 1 else f"{count} notes"


def _file_fact_html(fact: FileFact) -> str:
    """One fact row's rich-text fragment: a muted filled dot (never amber --
    these are structural facts, not counted diagnostics), a bold headline,
    a muted META detail line beneath -- the same glyph-then-two-line shape
    :func:`_task_row_html` already uses for a task row's own ring/half mark."""
    dot_img = icons.html_img(icons.DOT, color=style.MUTED, size=parameter_row.MARK_BOX)
    headline = parameter_row.compose_row_html(fact.headline, [], name_color=style.DEFAULT_TEXT)
    detail = (
        f'<span style="color:{style.MUTED}; {typography.size_qss(typography.META)}">'
        f"{_html.escape(fact.sub)}</span>"
    )
    return f"{dot_img}  {headline}<br>{detail}"


def _add_file_fact_row(list_widget: QListWidget, fact: FileFact) -> None:
    """One quiet, non-selectable, non-activatable file-facts row -- no
    severity, no trailing action, no badge, the same
    plain-text-plus-``HTML_ROLE`` idiom :func:`_add_clear_row` uses."""
    item = QListWidgetItem(f"{fact.headline}\n{fact.sub}")
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "file_fact")
    item.setData(parameter_row.HTML_ROLE, _file_fact_html(fact))
    list_widget.addItem(item)


def _add_file_facts_group(
    list_widget: QListWidget, filename: str, facts: tuple[FileFact, ...], *, collapsed: bool
) -> bool:
    """Build the file-facts group's fold header + rows and report whether
    anything rendered. Renders only while *facts* is non-empty -- the same
    "nothing to show, say nothing" rule extended to this group -- an
    everyday clean file adds nothing to the page. Folding hides the rows
    only: the header, and the fact of how many notes there are, never
    disappears -- there is no separate "dismiss" affordance."""
    if not facts:
        return False
    header = _FoldHeader(_FILE_FACTS_PATH, filename, _file_facts_suffix(len(facts)))
    _add_fold_header_row(list_widget, header, collapsed)
    if collapsed:
        return True
    for fact in facts:
        _add_file_fact_row(list_widget, fact)
    return True


def _add_all_clear_row(list_widget: QListWidget, total_buckets: int, *, model: str | None) -> None:
    """The pinned, non-activatable reassurance for a genuinely clean
    document: the shared all-clear glyph+wording (:func:`style.all_clear`)
    on line 1, unchanged regardless of *model*. Line 2 is normally the
    "N of N sections complete and valid" scale claim -- except under
    Partial, which has no completion target, so "complete and valid"
    would be false the same way
    :data:`_MSG_PARTIAL_NO_TARGET` exists to say elsewhere; line 2 becomes
    that notice instead, and it does not ALSO render as its own row (the
    caller's if/elif in :meth:`_StreamView.render` guarantees that). The
    clear line still renders below this row, expandable as usual."""
    line1 = style.all_clear("No issues, nothing incomplete")
    line2 = _MSG_PARTIAL_NO_TARGET if model == "Partial" else f"{total_buckets} of {total_buckets} sections complete and valid"
    html = (
        f'<span style="color:{style.DEFAULT_TEXT};">{_html.escape(line1)}</span><br>'
        f'<span style="color:{style.MUTED}; {typography.size_qss(typography.META)}">{_html.escape(line2)}</span>'
    )
    item = QListWidgetItem(f"{line1}\n{line2}")
    item.setFlags(Qt.ItemIsEnabled)  # visible, never selectable/activatable
    item.setData(_KIND_ROLE, "all_clear")
    item.setData(parameter_row.HTML_ROLE, html)
    list_widget.addItem(item)


def _add_section(
    list_widget: QListWidget,
    bucket: SectionBucket,
    partition: PartitionedIssues | None,
    filters: _FilterState,
    *,
    collapsed: bool,
) -> bool:
    """Build one non-clear bucket's fold header + rows. Returns whether
    anything actually rendered -- a header is emitted only once at least
    one row survives the filter: a section whose content is
    entirely filtered out leaves no trace at all, not even its header, and
    is not on the clear line either (clear is computed unfiltered)."""
    visible_issues = [
        (diagnostic, nav_path) for diagnostic, nav_path in bucket.issues if _issue_visible(diagnostic, filters)
    ]
    required_rows = [
        (task, _absorbed_messages(task, partition)) for task in bucket.required_tasks if _task_visible(task, filters)
    ]
    optional_rows = [
        (task, _absorbed_messages(task, partition)) for task in bucket.optional_tasks if _task_visible(task, filters)
    ]
    if not visible_issues and not required_rows and not optional_rows:
        return False

    header = _FoldHeader(bucket.path, bucket.label, _section_header_suffix(bucket))
    _add_fold_header_row(list_widget, header, collapsed)
    if collapsed:
        return True

    for diagnostic, nav_path in visible_issues:
        _add_issue_row(list_widget, bucket.label, diagnostic, nav_path)
    for task, absorbed in required_rows:
        _add_task_row(list_widget, task, absorbed)
    if optional_rows:
        # The subhead's own K is always the unfiltered truth
        # (bucket.optional_tasks); showing it over zero surviving rows
        # would orphan a header for nothing, so it only renders when at
        # least one optional row survives.
        count = len(bucket.optional_tasks)
        _add_subhead_row(
            list_widget, f"{count} optional parameter{'s' if count != 1 else ''} unfilled"
        )
        for task, absorbed in optional_rows:
            _add_task_row(list_widget, task, absorbed)
    return True


class _DiagnosticsRowDelegate(ParameterRowDelegate):
    """Stream row painting on top of the shared row delegate.

    Only actionable rows (issue/task) show hover/selection -- a message/
    subhead/clear_row/all_clear row paints flat whatever the mouse does,
    since a highlight promises interaction and activating one is a
    structural no-op. The two ruled header kinds (:attr:`_BAND_KINDS`) get
    their own custom paint -- caps text plus one boundary hairline on the
    plain page, whitespace above doing the separating a filled band once
    did: a per-section ``fold_header`` splits bold label from muted suffix
    (no badges); the page-wide ``clear_summary`` row paints its own
    already-composed plain text, single tier. A ``clear_row`` also gets
    custom paint --
    plain text, muted, italic only when its bucket is absent -- so an
    absent section's italic is drawn from the row's own real font rather
    than a font substituted via ``QListWidgetItem.setFont``.
    """

    _INTERACTIVE_KINDS = frozenset({"issue", "task"})
    #: Total header-row height: :attr:`_HEADER_AIR` of deliberate
    #: whitespace over a text tier -- the air, not a filled band, is what
    #: separates one section from the last.
    _FOLD_HEADER_HEIGHT = 40
    #: The whitespace share of :attr:`_FOLD_HEADER_HEIGHT`, above the text.
    _HEADER_AIR = 12
    _BAND_KINDS = frozenset({"fold_header", "clear_summary"})
    #: The widest a stream row's *content* gets, however wide the window is.
    #: A validator message ran the full bleed -- around 200 characters a line
    #: on a maximised window, well past readable -- and its right-aligned
    #: "Go to ▸" ended up a thousand pixels from the row it belonged to.
    #: ``style.PAGE_MEASURE`` (the data-column measure, not the prose one:
    #: these dense technical strings starve at ``style.CONTENT_MEASURE``),
    #: and a no-op on a narrow window.
    _MEASURE = style.PAGE_MEASURE

    def _available_width(self, option) -> float:
        return min(super()._available_width(option), self._MEASURE)

    def _measured(self, option) -> QStyleOptionViewItem:
        """*option* with its row narrowed to the measure.

        The rect is what both the text wrap and the right-aligned action are
        laid out against, so narrowing it here is what keeps the two in one
        column. The band kinds come through here too: a band used to paint
        full-bleed while rows stopped at the measure, which is exactly what
        made the dead space to their right visible -- bands and rows now
        share one edge.
        """
        narrowed = QStyleOptionViewItem(option)
        narrowed.rect.setWidth(min(narrowed.rect.width(), self._MEASURE))
        return narrowed

    def paint(self, painter, option, index) -> None:
        kind = index.data(_KIND_ROLE)
        if kind == "fold_header":
            self._paint_fold_header(painter, self._measured(option), index)
            return
        if kind == "clear_summary":
            self._paint_band(painter, self._measured(option), index.data(Qt.DisplayRole) or "")
            return
        if kind == "clear_row":
            self._paint_clear_row(painter, option, index)
            return
        option = self._measured(option)
        if kind is not None and kind not in self._INTERACTIVE_KINDS:
            option.state &= ~(QStyle.State_MouseOver | QStyle.State_Selected)
        super().paint(painter, option, index)

    def sizeHint(self, option, index):
        if index.data(_KIND_ROLE) in self._BAND_KINDS:
            return QSize(int(self._available_width(option)), self._FOLD_HEADER_HEIGHT)
        return super().sizeHint(option, index)

    def _hairline(self, painter, option, *, edge_at_top: bool) -> None:
        """A header's single 1px boundary rule -- all that survives of the
        old shaded band, whose fill read too heavy repeated once per
        section. The rule is the half that stays for a reason the contrast
        pass already paid for: a wash alone vanished on ordinary Windows
        panels, a line cannot. A fold header's rule sits on its bottom
        edge, under its own title; the clear line's sits on its top edge,
        against the rows above it. The line is the app's ordinary
        ``BORDER`` tone, not ``BORDER_STRONG`` -- at one per section the
        darker step made the dividers the loudest thing on the page."""
        painter.save()
        edge_y = option.rect.top() if edge_at_top else option.rect.bottom()
        painter.fillRect(
            QRect(option.rect.left(), edge_y, option.rect.width(), 1),
            QColor(style.BORDER),
        )
        painter.restore()

    def _caps_font(self, option) -> QFont:
        """The caps-tier font for a band's title text -- META semibold with
        the shared letter-spacing, the same treatment the parameter-list
        header's own section title already wears (that header uppercases
        section labels too, the precedent for doing it here): structure in
        caps, validator text in sentence case, so the two never blur."""
        return typography.apply_caps_spacing(
            typography.semibold(typography.sized(option.font, typography.META))
        )

    def _paint_band(self, painter, option, text: str) -> None:
        """The page-wide clear line: one muted caps row, ruled on its top
        edge against the stream above it; :meth:`_paint_fold_header` is
        the per-section variant with its own two-tier text."""
        self._hairline(painter, option, edge_at_top=True)
        painter.save()
        font = self._caps_font(option)
        painter.setFont(font)
        painter.setPen(QColor(style.MUTED))
        text_rect = option.rect.adjusted(self._h_pad, 0, -self._h_pad, 0)
        # Elided, never clipped: drawText cuts mid-glyph at the rect edge.
        elided = QFontMetrics(font).elidedText(
            text.upper(), Qt.ElideRight, text_rect.width()
        )
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()

    def _paint_fold_header(self, painter, option, index) -> None:
        header: _FoldHeader = index.data(_FOLD_BUCKET_ROLE)
        collapsed = bool(index.data(_FOLD_COLLAPSED_ROLE))
        chevron = "▸" if collapsed else "▾"
        label_text = f"{chevron}  {header.label.upper()}"
        suffix = header.suffix

        self._hairline(painter, option, edge_at_top=False)

        # The row's top ``_HEADER_AIR`` is deliberate whitespace -- the
        # inter-section gap lives inside the header row -- so both text
        # tiers centre in the zone below it, just above the bottom rule.
        zone = option.rect.adjusted(0, self._HEADER_AIR, 0, 0)
        font = self._caps_font(option)
        metrics = QFontMetrics(font)
        suffix_font = typography.sized(option.font, typography.META)
        label_rect = zone.adjusted(self._h_pad, 0, -self._h_pad, 0)
        # The label gives way before the suffix vanishes: reserve the suffix
        # its natural width (never more than half the band), elide the label
        # into the rest. Unelided, a long section name pushed suffix_x past
        # the rect and the counts silently collapsed to width 0.
        reserved = 0
        if suffix:
            natural = QFontMetrics(suffix_font).horizontalAdvance(suffix)
            reserved = min(natural, label_rect.width() // 2) + 10
        label_elided = metrics.elidedText(
            label_text, Qt.ElideRight, max(label_rect.width() - reserved, 0)
        )

        painter.save()
        painter.setFont(font)
        painter.setPen(QColor(style.DEFAULT_TEXT))
        painter.drawText(label_rect, Qt.AlignVCenter | Qt.AlignLeft, label_elided)
        painter.restore()

        if suffix:
            painter.save()
            painter.setFont(suffix_font)
            painter.setPen(QColor(style.MUTED))
            suffix_x = label_rect.left() + metrics.horizontalAdvance(label_elided) + 10
            suffix_rect = QRect(
                suffix_x, zone.top(), max(zone.right() - self._h_pad - suffix_x, 0), zone.height()
            )
            elided = QFontMetrics(suffix_font).elidedText(suffix, Qt.ElideRight, suffix_rect.width())
            painter.drawText(suffix_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
            painter.restore()

    def _paint_clear_row(self, painter, option, index) -> None:
        bucket: SectionBucket = index.data(_FOLD_BUCKET_ROLE)
        text = index.data(Qt.DisplayRole) or ""
        painter.save()
        font = QFont(option.font)
        if bucket is not None and bucket.absent:
            font.setItalic(True)
        painter.setFont(font)
        painter.setPen(QColor(style.MUTED))
        text_rect = option.rect.adjusted(self._h_pad, 0, -self._h_pad, 0)
        elided = QFontMetrics(font).elidedText(text, Qt.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, elided)
        painter.restore()


class _StreamView(QWidget):
    """The whole page's content: one continuous, scrolling list, the
    single renderer replacing both the old single-section pane
    (``_SectionDetailView``/``_GroupBox``) and the "All sections" backup
    pane (``_AllSectionsView``) -- one dataset, one rendering path, nothing
    left to reconcile between two views.

    Only sections with something in them render, each its own foldable
    header + rows; every clear bucket collapses onto one
    foldable footer line at the bottom instead; a genuinely clean
    document or a Partial document with nothing outstanding anywhere
    (the pinned Partial notice) gets one pinned row above that line instead
    of a bare absence. Caches its last ``render()`` inputs so a click
    (fold/unfold a section, fold/unfold the clear line) can re-render
    itself without the caller re-deriving anything, the same idiom the old
    ``_AllSectionsView`` already used."""

    issue_activated = Signal(tuple)
    task_activated = Signal(object)
    #: Emitted whenever a *per-section* fold toggles (a header click), so
    #: :class:`DiagnosticsPanel` can refresh the column's fold-everything
    #: label -- the label depends on the fold set, and a header click
    #: re-renders only this widget, not the whole panel, so without this
    #: signal the label goes stale (fold every section one by one and it
    #: still reads "Collapse all"). A Qt signal, not a stored bound method,
    #: per the project widget-lifetime rule.
    folds_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(style.SPACING_SM, 4, style.SPACING_SM, 4)
        layout.setSpacing(0)

        self._list = ActivatingList()
        self._list.setObjectName("DiagnosticsStreamList")
        # Same column discipline as cards/page.py's content body: the list
        # itself stops at the page measure, so the hover/selection washes,
        # the header rules and the scrollbar all end at the edge the delegate
        # already wraps text against. Full-bleed, a maximised window painted
        # window-wide hover under 960px text. The column hugs the left (the
        # trailing stretch below -- a QHBox would otherwise centre a lone
        # capped child), like the Inspector's rail-anchored column: the
        # filter column now holds the page's right side, and a stream
        # centred in what is left would drift away from it as the window
        # widens.
        self._list.setMaximumWidth(style.PAGE_MEASURE)
        self._list.setWordWrap(True)
        self._list.setItemDelegate(_DiagnosticsRowDelegate(self._list))
        self._list.itemActivated.connect(self._on_activated)
        self._list.itemClicked.connect(self._on_clicked)
        row = QHBoxLayout()
        # Stretch 1 on the list, 0 on the spacer -- the same trick
        # page_header.set_trailing_accessory uses: the list takes the width
        # first (up to its cap) and only what is left over goes to the
        # spacer that holds it against the left edge. A bare addStretch(1)
        # would split the width evenly and shrink the list to its size hint.
        row.addWidget(self._list, 1)
        row.addStretch(0)
        layout.addLayout(row)

        self._collapsed: set[tuple[str, ...]] = set()
        self._clear_expanded = False
        self._rendered_section_paths: list[tuple[str, ...]] = []
        self._last_buckets: PageBuckets | None = None
        self._last_partition: PartitionedIssues | None = None
        self._last_model: str | None = None
        self._last_filters = _FilterState()
        self._last_filename = ""
        self._last_facts: tuple[FileFact, ...] = ()
        self._last_reach = CheckReach.COMPLETE
        self._file_facts_rendered = False

    def reset_fold_state(self) -> None:
        """Per-section folds and the clear line's own expanded flag -- both
        view-only state that resets only on a *different* document."""
        self._collapsed.clear()
        self._clear_expanded = False

    def render(
        self,
        buckets: PageBuckets,
        partition: PartitionedIssues | None,
        model: str | None,
        filters: _FilterState,
        filename: str = "",
        facts: tuple[FileFact, ...] = (),
        reach: CheckReach = CheckReach.COMPLETE,
    ) -> None:
        self._last_buckets = buckets
        self._last_partition = partition
        self._last_model = model
        self._last_filters = filters
        self._last_filename = filename
        self._last_facts = facts
        self._last_reach = reach
        self._list.clear()

        # Tracked separately from ``_rendered_section_paths`` -- the fold-
        # everything affordance's own "fewer than two rendered SECTIONS"
        # gate (:meth:`collapse_all_label`) stays section-only, so a lone
        # facts group does not conjure a "Collapse all" affordance that
        # would only ever fold that one always-present group.
        # :meth:`toggle_all_folds` still folds the file-facts group too,
        # once the affordance is genuinely shown.
        self._file_facts_rendered = _add_file_facts_group(
            self._list, filename, facts, collapsed=_FILE_FACTS_PATH in self._collapsed
        )

        rendered_paths: list[tuple[str, ...]] = []
        clear_buckets: list[SectionBucket] = []
        for bucket in buckets.buckets:
            if _bucket_is_clear(bucket):
                clear_buckets.append(bucket)
                continue
            collapsed = bucket.path in self._collapsed
            if _add_section(self._list, bucket, partition, filters, collapsed=collapsed):
                rendered_paths.append(bucket.path)
        self._rendered_section_paths = rendered_paths

        # The all-clear row states "No issues" as a verdict, so it also needs
        # the run to have finished -- unreachable today (an aborted run always
        # carries the error that aborted it), but the guard keeps a future
        # bpx's abort shape from turning silence into a clean bill of health.
        if _page_is_clear(buckets) and reach is CheckReach.COMPLETE:
            _add_all_clear_row(self._list, len(buckets.buckets), model=model)
        elif model == "Partial" and buckets.outstanding_count == 0:
            _add_message_row(self._list, _MSG_PARTIAL_NO_TARGET)

        if clear_buckets:
            # Judged per bucket, not blanket per page: after an abort at
            # Parameterisation a clean Header really was checked while State
            # never was, and the line must say both truthfully, in both
            # directions. The Document bucket's empty path asks about the
            # document level itself.
            judged = {
                bucket.path: section_checked(bucket.path[0] if bucket.path else None, reach)
                for bucket in clear_buckets
            }
            checked_count = sum(1 for was in judged.values() if was)
            _add_clear_summary_row(
                self._list,
                checked_count,
                len(clear_buckets) - checked_count,
                self._clear_expanded,
                reach,
            )
            if self._clear_expanded:
                for bucket in clear_buckets:
                    _add_clear_row(self._list, bucket, judged[bucket.path], reach)

    def collapse_all_label(self) -> str | None:
        """The fold-everything affordance's label -- ``None`` hides it
        (fewer than two rendered sections to fold, nothing to collapse);
        otherwise "Collapse all" while any rendered section is expanded,
        else "Expand all"."""
        if len(self._rendered_section_paths) < 2:
            return None
        any_expanded = any(path not in self._collapsed for path in self._rendered_section_paths)
        return "Collapse all" if any_expanded else "Expand all"

    def toggle_all_folds(self) -> None:
        """Fold every currently-rendered section if any is expanded, else
        unfold them all -- one click regardless of how mixed the current
        fold state is. The caller (:class:`DiagnosticsPanel`) re-renders
        afterwards; this only updates the fold set itself.

        Whether *any* is expanded, and whether there is anything to do at
        all, is judged from rendered sections alone -- the
        file-facts group never by itself unlocks or drives this affordance.
        Once the affordance genuinely acts, though, its own path joins the
        targets, so "Collapse all"/"Expand all" folds the file-facts group
        too."""
        if not self._rendered_section_paths:
            return
        targets = set(self._rendered_section_paths)
        if self._file_facts_rendered:
            targets.add(_FILE_FACTS_PATH)
        if any(path not in self._collapsed for path in self._rendered_section_paths):
            self._collapsed.update(targets)
        else:
            self._collapsed.difference_update(targets)

    def _on_activated(self, item: QListWidgetItem) -> None:
        kind = item.data(_KIND_ROLE)
        if kind == "issue":
            self.issue_activated.emit(item.data(_NAV_PATH_ROLE))
        elif kind == "task":
            self.task_activated.emit(item.data(_TASK_ROLE))

    def _on_clicked(self, item: QListWidgetItem) -> None:
        kind = item.data(_KIND_ROLE)
        if kind == "fold_header":
            header: _FoldHeader = item.data(_FOLD_BUCKET_ROLE)
            self._collapsed.symmetric_difference_update({header.path})
        elif kind == "clear_summary":
            self._clear_expanded = not self._clear_expanded
        else:
            return
        if self._last_buckets is not None:
            self.render(
                self._last_buckets,
                self._last_partition,
                self._last_model,
                self._last_filters,
                self._last_filename,
                self._last_facts,
                self._last_reach,
            )
        if kind == "fold_header":
            self.folds_changed.emit()


def _chip_html(svg: str, color: str, text: str, *, on: bool) -> str:
    """*on* controls the chip's own colours -- when a chip is toggled
    off, both its dot and its count text go ``style.MUTED``, on top of the
    "off" QSS state (:data:`_FilterChip`) that greys its card background:
    visibly muted/pressed-out, never merely relabelled."""
    icon_color = color if on else style.MUTED
    text_color = style.DEFAULT_TEXT if on else style.MUTED
    icon = icons.html_img(svg, color=icon_color, size=parameter_row.MARK_BOX)
    return f'{icon}<span style="color:{text_color};">  {_html.escape(text)}</span>'


class _FilterChip(QLabel):
    """One filter item in the side column, also a click-toggle filter.
    Stays a ``QLabel`` (not a ``QPushButton``) so it keeps rendering its
    rich-text icon+count content (a coloured dot plus text,
    :func:`_chip_html`) -- native Qt buttons render ``text()`` as plain
    text, not HTML. Interactivity is layered on with
    :meth:`mousePressEvent`.

    Flat text, no card: in the side column these sit at the same level as
    "Collapse all" under a "FILTER" category label, and a border here would
    make four peer items read as two kinds of thing. Their whole visual
    state is therefore carried by :func:`_chip_html`'s own colours -- an
    off (or zero-count) filter mutes both its dot and its text."""

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
        programmatic resets (:meth:`_FilterColumn.reset_filters`), which
        must not re-enter the filter-change/render path while a *different*
        document's buckets are still being assembled."""
        self._on = on

    def set_zero_count(self, zero: bool) -> None:
        """A chip whose unfiltered count is zero is genuinely disabled
        -- Qt withholds mouse events from a disabled widget, so
        :meth:`mousePressEvent` never even fires. Its muted look comes from
        :func:`_chip_html` like any other off state. This is purely a
        paint/interaction decision layered on top of :attr:`_on`, which
        keeps meaning "the user's own filter choice" regardless of whether
        the current document happens to have anything for it to filter."""
        self.setEnabled(not zero)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if not self.isEnabled():
            return
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.set_on(not self._on)
        self.toggled.emit(self._on)


class _CollapseAllLink(QLabel):
    """The fold-everything affordance ("Collapse all"/"Expand all"), the
    side column's first item. Flat text like its ``_FilterChip``
    neighbours: it is a peer of the three filters, not a control standing
    over them, so it wears no chip -- the app-wide "an action wears a chip"
    rule buys nothing in a column where every item is one level. Stays a
    ``QLabel`` for the same reason ``_FilterChip`` does (a native
    ``QPushButton`` would work here too, since this label carries no
    rich-text content, but sharing the click-via-``mousePressEvent`` idiom
    keeps the column's two interactive-label kinds consistent)."""

    clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiagnosticsCollapseAll")
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event) -> None:  # noqa: N802 -- Qt override
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        self.clicked.emit()


class _FilterColumn(QWidget):
    """The page's right-hand column: "Collapse all", then a "FILTER"
    category label over the three toggleable count filters. Every item sits
    flush to one left edge at one level -- the label is a *category*, not a
    header for a control group, so the fold affordance and the three
    filters read as four peer items rather than a chip above a box.

    Fixed width and gutter follow the app's existing secondary columns (the
    reference-library / compare-with pickers, the workspace rail): a column
    that resized with its counts would reflow the stream beside it every
    time a document's error count crossed a digit. Its own wash is what
    sets it off from the stream -- deliberately no divider, which would
    draw a line up into the page header above.

    Filtering here is purely a VIEW concern -- this widget owns the filter
    *state* (chip on/off) and reports it via :meth:`filter_state`; it never
    touches counts, badges or buckets itself (:class:`DiagnosticsPanel`
    reads the state and re-renders the stream -- filtering stays
    view-only). Likewise the collapse-all label is a dumb affordance:
    :class:`DiagnosticsPanel` decides its text/visibility from the stream's
    own fold state (:meth:`~_StreamView.collapse_all_label`) and reacts to
    its click; this widget only paints whatever label it is given and emits
    the click."""

    #: Emitted whenever a chip is toggled -- DiagnosticsPanel re-renders
    #: only the *stream* on this signal (never a full ``refresh()``), so
    #: toggling can never re-enter the document-wide refresh path.
    filters_changed = Signal()
    #: Emitted on a collapse-all/expand-all click; DiagnosticsPanel owns
    #: what that means (:meth:`_StreamView.toggle_all_folds`).
    collapse_all_clicked = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("DiagnosticsFilterColumn")
        # A plain QWidget subclass ignores stylesheet backgrounds unless
        # told to paint them (see ActivityBar/PageHeader's own note);
        # without this the column's wash silently never draws.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(_COLUMN_WIDTH)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(style.SPACING_LG, 12, style.SPACING_LG, 12)
        layout.setSpacing(6)

        self._counts = (0, 0, 0)

        self._collapse_all = _CollapseAllLink()
        self._collapse_all.clicked.connect(self.collapse_all_clicked)
        layout.addWidget(self._collapse_all)

        # The category's own breathing room, carried by the label rather
        # than a spacer item: with "Collapse all" hidden (fewer than two
        # foldable sections) a spacer would still hold its gap, leaving the
        # column's first item pushed down by chrome that is not there.
        self._category = typography.panel_title("Filter")
        self._category.setContentsMargins(0, style.SPACING_MD, 0, 0)
        layout.addWidget(self._category)

        self._errors = _FilterChip()
        self._warnings = _FilterChip()
        self._outstanding = _FilterChip()
        for chip in (self._errors, self._warnings, self._outstanding):
            chip.toggled.connect(self._on_chip_toggled)
            layout.addWidget(chip)

        layout.addStretch(1)

    def set_counts(self, errors: int, warnings: int, outstanding: int) -> None:
        self._counts = (errors, warnings, outstanding)
        for chip, count in ((self._errors, errors), (self._warnings, warnings), (self._outstanding, outstanding)):
            chip.set_zero_count(count == 0)
        self._refresh_chip_text()
        self._refresh_tooltips()

    def set_collapse_all_label(self, text: str | None) -> None:
        """*text* is ``None`` when :meth:`_StreamView.collapse_all_label`
        says fewer than two sections render -- hides the affordance
        entirely rather than disabling it: "Collapse all" over zero
        foldable sections is chrome announcing nothing, the same bug
        avoided elsewhere on this page."""
        self._collapse_all.setVisible(text is not None)
        if text is not None:
            self._collapse_all.setText(text)

    def _refresh_tooltips(self) -> None:
        """Counts stay truthful regardless of on/off state: they always
        describe the real, unfiltered counts. The state suffix is what tells
        a user these chips are click-to-filter at all -- nothing else on the
        chip says so."""
        errors, warnings, outstanding = self._counts
        for chip, base in (
            (self._errors, style.error_count_tooltip(errors)),
            (self._warnings, style.warning_count_tooltip(warnings)),
            (self._outstanding, style.outstanding_count_tooltip(outstanding)),
        ):
            state = "click to hide" if chip.is_on() else "hidden · click to show"
            chip.setToolTip(f"{base} · {state}")

    def filter_state(self) -> _FilterState:
        return _FilterState(
            error_on=self._errors.is_on(),
            warning_on=self._warnings.is_on(),
            outstanding_on=self._outstanding.is_on(),
        )

    def reset_filters(self) -> None:
        """Back to all-on -- called only on a *different* document
        (:meth:`DiagnosticsPanel.reset_view_state`), never on an ordinary
        refresh, where persisting is the point."""
        for chip in (self._errors, self._warnings, self._outstanding):
            chip.set_on(True)
        self._refresh_chip_text()
        self._refresh_tooltips()

    def _refresh_chip_text(self) -> None:
        errors, warnings, outstanding = self._counts
        self._errors.setText(
            _chip_html(
                icons.DOT,
                style.ERROR,
                f"{errors} error{'s' if errors != 1 else ''}",
                on=self._errors.is_on() and errors > 0,
            )
        )
        self._warnings.setText(
            _chip_html(
                icons.DOT,
                style.WARNING,
                f"{warnings} warning{'s' if warnings != 1 else ''}",
                on=self._warnings.is_on() and warnings > 0,
            )
        )
        self._outstanding.setText(
            _chip_html(
                icons.RING,
                style.MUTED,
                f"{outstanding} incomplete",
                on=self._outstanding.is_on() and outstanding > 0,
            )
        )

    def _on_chip_toggled(self, _on: bool) -> None:
        self._refresh_chip_text()
        self._refresh_tooltips()
        self.filters_changed.emit()


class DiagnosticsPanel(QWidget):
    """Renders the Diagnostics page: one scrolling stream + a filter column.

    Shows an explanatory placeholder instead of the page only when there is
    no document at all -- once a document is open, the stream/column are
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
        # Two columns, not a band over a stream: the stream takes the room
        # that is left (and hugs the left edge itself, see _StreamView),
        # the filter column is fixed beside it.
        content_layout = QHBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        self._stream = _StreamView()
        self._stream.issue_activated.connect(self.issue_activated)
        self._stream.task_activated.connect(self.task_activated)
        self._stream.folds_changed.connect(self._on_folds_changed)
        content_layout.addWidget(self._stream, 1)

        self._side = _FilterColumn()
        self._side.filters_changed.connect(self._on_filters_changed)
        self._side.collapse_all_clicked.connect(self._on_collapse_all_clicked)
        content_layout.addWidget(self._side)

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
        self._filename = ""
        self._facts: tuple[FileFact, ...] = ()
        self._reach = CheckReach.COMPLETE

    def reset_view_state(self) -> None:
        self._stream.reset_fold_state()
        self._side.reset_filters()

    def refresh(
        self,
        buckets: PageBuckets | None,
        partition: PartitionedIssues | None,
        model: str | None,
        filename: str = "",
        facts: tuple[FileFact, ...] = (),
        reach: CheckReach = CheckReach.COMPLETE,
    ) -> None:
        """Rebuild the stream and column from one derivation point's output.

        *buckets* is ``core.page_buckets.bucket_page_content``'s result --
        computed once in ``main_window._refresh_all`` alongside the rail
        badge, so this panel and the badge can never disagree.
        *partition* is passed through only for its ``absorbed_by_task``
        lookup (secondary text); *model* only for the Partial
        notice (see :data:`_MSG_PARTIAL_NO_TARGET`) -- every grouping/count
        this panel renders otherwise comes from *buckets* alone. *filename*/
        *facts* feed the file-facts group (:mod:`ui_qt.file_facts`) --
        both default empty so every existing caller that never mentions them
        (e.g. the keyboard-navigation fixture) renders no such group.
        *reach* is the document's ``validation_reach``:
        the clear line consults it per bucket, so a section beyond an aborted
        run's reach reads "not checked" while a genuinely judged one keeps
        "clear", and the all-clear row only renders for a completed run.
        """
        self._buckets = buckets
        self._partition = partition
        self._model = model
        self._filename = filename
        self._facts = facts
        self._reach = reach
        if buckets is None:
            self._placeholder.setText(_MSG_NO_DOCUMENT)
            self._stack.setCurrentIndex(1)
            return
        self._side.set_counts(buckets.error_count, buckets.warning_count, buckets.outstanding_count)
        self._stack.setCurrentIndex(0)
        self._render_stream()

    def _on_filters_changed(self) -> None:
        """A chip toggled -- re-render only
        the stream, never a full ``refresh()``: filters are view-only and
        must never re-enter the document-wide refresh path (the column's counts
        and the app badge are untouched by this call)."""
        self._render_stream()

    def _on_collapse_all_clicked(self) -> None:
        self._stream.toggle_all_folds()
        self._render_stream()

    def _on_folds_changed(self) -> None:
        """A per-section fold toggled directly (a header click, not the
        collapse-all affordance) -- ``_StreamView`` already re-rendered
        itself; only the column's fold-everything label can be stale, so
        refresh just that, the same narrow update :meth:`_render_stream`
        does at the end of every other path that can move the fold set."""
        self._side.set_collapse_all_label(self._stream.collapse_all_label())

    def _render_stream(self) -> None:
        if self._buckets is None:
            return
        filters = self._side.filter_state()
        self._stream.render(
            self._buckets,
            self._partition,
            self._model,
            filters,
            self._filename,
            self._facts,
            self._reach,
        )
        self._side.set_collapse_all_label(self._stream.collapse_all_label())
