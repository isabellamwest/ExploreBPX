"""Frontend-agnostic bucketing for the Validation page's rail (Stage A of the
rail redesign, ``PLAN-completion-track.md`` S4b, decisions F2/F3).

The rail replaces the old stacked Issues/Outstanding page with a summary
strip plus a per-section rail; each rail entry needs its own Issues +
Outstanding content, pre-split and counted, so the UI layer never has to
re-derive grouping/absorption rules of its own (that duplication is exactly
what put the old ``diagnostics_panel.py`` grouping helpers -- ``_display_path``,
``_owning_section``, ``_group_outstanding_tasks`` -- out of sync with each
other in the first place: Issues grouped by a bare display label,
Outstanding grouped by the task's full owning path, and the two only
happened to agree by construction, never by a shared rule). This module is
that shared rule, moved inward.

:func:`bucket_page_content` is the single entry point: it consumes exactly
what ``DiagnosticsPanel.refresh`` receives today (``raw``/``model``/
``partition``/``tasks``, all already computed once in
``main_window._refresh_all``) and returns an ordered :class:`PageBuckets` --
one :class:`SectionBucket` per rail entry, an optional Document bucket
first when occupied, everything else in document order. Nothing is lost
(F3): every visible diagnostic and every task lands in exactly one bucket --
there is no drop path, and the module's own totals are summed FROM the
buckets, never read from ``partition``/``tasks`` directly, so a caller cannot
render a strip that disagrees with the rail (F3's own reconciliation
invariant, and the direct descendant of decision G).

Assignment rule (F3), reusing one existing normalization (decision E) for
both diagnostics and tasks. ``diagnostics_panel._relative_location`` already
established the shape of the rule for Issues display (see the
diffusivity-warning-bug memory note): strip a leading ``"Parameterisation"``
-- a structural wrapper -- but keep ``"Header"``/``"State"``/``"Validation"``
in full, since each of those names a real, human-meaningful section on its
own. :func:`_bucket_path_for` generalises that exact rule from a bare label
to the canonical path Stage B still needs for ``completion_for`` lookups.

That alone is enough whenever a path is already *canonical* -- a resolved
parameter's own ``.path``, or a task's, both always carry their true prefix.
It is NOT enough for an unresolved diagnostic's raw, validator-derived
``loc``: V4's asymmetric convention means a ``Header``- or
``Parameterisation``-owned diagnostic that never resolved to an existing
parameter (its target field is exactly what is missing) arrives with that
prefix already stripped by the validator itself -- the same fact
``completion._STRIPPED_LOC_PREFIXES``/``_nav_path_candidates`` exists to
reverse for absorption matching. :func:`_resolve_bucket_path` is F3's three
tiers made concrete, reusing that same fact rather than a second scheme
(decision E): "display section when the path resolves" is
:func:`_bucket_path_for` applied directly whenever the path's own presumed
parent already exists in ``raw`` (no stripping occurred, or none needs
correcting); "else nearest existing ancestor's bucket" tries reinstating
each stripped prefix and keeps it only when ``bpx_gateway``'s own schema --
the same authority :func:`completion.completion_for` defers to -- confirms
the leaf actually belongs to that reinstated section (never guessed from
raw shape alone, which cannot tell "Header" from "Parameterisation" for a
leaf that exists in neither); "else Document" is the final fallback, reached
only when nothing above resolves anything (an empty path, or a
``MISSING_SECTION`` task for an entirely absent ``Parameterisation`` with no
child segment to promote).
"""

from __future__ import annotations

from dataclasses import dataclass

from . import bpx_gateway, completion, structure
from .completion import CompletionTask, PartitionedIssues, TaskKind
from .validation import Severity, ValidatorDiagnostic, merge_union_pairs_by_location

#: One (diagnostic, nav_path) pair, exactly as ``PartitionedIssues.visible``
#: and ``BPXDocument.iter_issues()`` already carry them.
IssuePair = tuple[ValidatorDiagnostic, tuple[str, ...]]

#: The Document bucket's sentinel path. No real section bucket can ever carry
#: an empty path (every schema/raw/task-forced key contributes at least one
#: path component), so this cannot collide with one.
DOCUMENT_BUCKET_PATH: tuple[str, ...] = ()


@dataclass(frozen=True)
class SectionBucket:
    """One rail entry's content: a section's Issues + Outstanding, already
    resolved to exactly the rows the pane needs (F2's banded group boxes).

    ``issues`` are already display-merged (decision Q's float/int union-pair
    collapse) at the whole-page level before bucketing -- callers must not
    re-merge or un-merge them, or a bucket's count could drift from the
    page-level totals :class:`PageBuckets` reports.
    """

    #: Canonical section path (e.g. ``("Parameterisation", "Cell")``,
    #: ``("Header",)``, ``("State",)``); :data:`DOCUMENT_BUCKET_PATH` for the
    #: Document bucket.
    path: tuple[str, ...]
    #: Rail display name -- the section's own leaf name; ``"Document"`` for
    #: the sentinel bucket.
    label: str
    #: Whether the section itself is absent from ``raw`` (decision M: an
    #: absent section's fields are never enumerated, so ``required_total`` is
    #: ``None`` whenever this is ``True``). Always ``False`` for the Document
    #: bucket -- "absent" has no meaning for the document root.
    absent: bool
    #: Document order, already display-merged (decision Q) -- see the class
    #: docstring.
    issues: tuple[IssuePair, ...]
    #: Decision R's required group, document order, ``task.required`` True.
    required_tasks: tuple[CompletionTask, ...]
    #: Decision R's optional sub-group, document order, ``task.required`` False.
    optional_tasks: tuple[CompletionTask, ...]
    #: The "M" in "N of M remaining" (``len(required_tasks)`` is the "N").
    #: ``None`` when the section is absent (decision M -- fields are never
    #: enumerated) or for the Document bucket (no section shape to count).
    required_total: int | None
    #: Post-absorption counts (decision E/G), from this bucket's own
    #: ``issues`` only.
    error_count: int
    warning_count: int

    @property
    def outstanding_count(self) -> int:
        return len(self.required_tasks) + len(self.optional_tasks)


@dataclass(frozen=True)
class PageBuckets:
    """The whole Validation page's content, pre-split into rail buckets, in
    render order (Document first when occupied, then document order).

    Totals are summed FROM ``buckets`` -- never read back from ``partition``/
    ``tasks`` -- so the summary strip and the rail can never disagree with
    the pane's own content (F3's reconciliation invariant; the badge itself
    still derives from ``partition`` directly, per decision G, but must equal
    these same totals by construction).
    """

    buckets: tuple[SectionBucket, ...]
    error_count: int
    warning_count: int
    outstanding_count: int


def _task_owning_path(task: CompletionTask) -> tuple[str, ...]:
    """The canonical path a task is about.

    A ``MISSING_SECTION`` task names an absent section directly, so it is
    about that path itself. Every other kind names a field inside a section
    that necessarily exists (fields are only ever enumerated for present
    sections, decision M), so it is about that field's parent.
    """
    if task.kind is TaskKind.MISSING_SECTION:
        return task.path
    return task.path[:-1]


def strip_parameterisation_prefix(path: tuple[str, ...]) -> tuple[str, ...]:
    """Drop a leading ``"Parameterisation"`` -- a structural wrapper, never
    a real section name a human would read (its children -- ``"Cell"``,
    ``"Negative electrode"``, ...-- are the meaningful names). Every other
    path passes through unchanged, including ``"Header"``/``"State"``/
    ``"Validation"``, which ARE real section names and must survive.

    The one shared owner of this normalization (decision E: never invent a
    second path-matching scheme) -- :func:`_bucket_path_for` builds its
    bucket-assignment truncation on it below, and
    ``ui_qt.diagnostics_panel._relative_location`` reuses it verbatim to
    compute an issue row's location *within* its bucket, so the two can
    never drift apart on what "strip the wrapper" means.
    """
    if path[:1] == ("Parameterisation",):
        return path[1:]
    return path


def _bucket_path_for(path: tuple[str, ...]) -> tuple[str, ...]:
    """The canonical rail bucket a full document path belongs to.

    See the module docstring for the rule and why it needs no separate
    "ancestor" tier. A leading ``"Parameterisation"`` is dropped and its
    child promoted (``("Parameterisation", "Cell", ...)`` becomes a
    two-segment bucket path); every other path (``"Header"``, ``"State"``,
    ``"Validation"``, or an unrecognised custom top-level key) is truncated
    to its own first segment -- one bucket per section, however deep the
    diagnostic/task actually sits (``("State", "Initial conditions")`` and
    ``("State", "Thermal environment")`` both land under ``("State",)``,
    matching how Issues already group every ``State``-prefixed diagnostic
    together regardless of depth).
    """
    if not path:
        return DOCUMENT_BUCKET_PATH
    if path[0] == "Parameterisation":
        stripped = strip_parameterisation_prefix(path)
        if not stripped:
            return DOCUMENT_BUCKET_PATH
        return ("Parameterisation",) + stripped[:1]
    return path[:1]


def _section_present(raw: dict, path: tuple[str, ...]) -> bool:
    """Whether the key named by ``path`` exists in ``raw`` -- regardless of
    its value's type/validity. A garbage ``"Cell": 5`` is present, just
    wrong: decision M's "absent" means the key itself is missing, never that
    its value is invalid (that stays a plain Issue, per decision E's safety
    net -- nothing here silences it)."""
    node: object = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return False
        node = node[key]
    return True


def _value_at(raw: dict, path: tuple[str, ...]) -> dict:
    """Read-only nested lookup, defaulting to ``{}`` for any unresolved or
    non-dict segment -- used only to fetch an existing section's value for a
    ``completion_for`` call. Duplicates ``diagnostics_panel``'s own helpers
    (this stage's brief: duplicate inward, Stage B removes the UI copy)."""
    node: object = raw
    for key in path:
        if not isinstance(node, dict) or key not in node:
            return {}
        node = node[key]
    return node if isinstance(node, dict) else {}


def _expected_aliases(path: tuple[str, ...], model: str | None, value: object) -> frozenset[str]:
    """The schema-expected field/section names at ``path``, or an empty set
    when ``path`` has no single schema definition -- mirrors
    :func:`completion.completion_for`'s own ``ValueError`` handling, since
    both defer to the same :func:`bpx_gateway.expected_fields` authority."""
    try:
        fields = bpx_gateway.expected_fields(path, model, value)
    except ValueError:
        return frozenset()
    return frozenset(field.alias for field in fields)


def _resolve_bucket_path(raw: dict, model: str | None, path: tuple[str, ...]) -> tuple[str, ...]:
    """F3's assignment rule for one path -- see the module docstring for the
    reasoning; this is its concrete implementation.

    ``path`` is either a diagnostic's nav_path or a task's owning path
    (:func:`_task_owning_path`). The fast path handles every already-
    canonical path (a resolved parameter's ``.path``, or any task path): if
    the section the naive interpretation names already exists in ``raw``,
    that interpretation is correct and no schema lookup is needed. The slow
    path only ever runs for an unresolved, V4-stripped diagnostic loc (its
    presumed section does not exist -- almost always because the leaf itself
    is exactly what is missing): it tries reinstating each prefix the
    validator is known to drop (``"Header"``, then ``"Parameterisation"``)
    and accepts one only when the schema actually names this leaf under that
    reinstated section, never by raw shape alone -- raw presence cannot
    distinguish "belongs to Header" from "belongs to Parameterisation" for a
    leaf that exists in neither yet.
    """
    if not path:
        return DOCUMENT_BUCKET_PATH
    if path[0] == "Parameterisation":
        return _bucket_path_for(path)

    naive_parent = path[:-1] if len(path) > 1 else path
    if _section_present(raw, naive_parent):
        return path[:1]

    leaf = path[-1]
    for prefix in (("Header",), ("Parameterisation",)):
        section_path = prefix + path[:-1]
        if leaf in _expected_aliases(section_path, model, _value_at(raw, section_path)):
            return _bucket_path_for(section_path + (leaf,))
    return path[:1]


def _parameterisation_child_order(raw: dict, model: str | None) -> list[str]:
    """The child key order to walk ``Parameterisation`` in, for bucketing.

    :func:`structure.required_sections` (the schema authority
    ``document_factory``/``command_service`` already use to scaffold a new
    document) names ``Parameterisation``'s children in a fixed, model-
    specific order (Cell, Negative electrode, Positive electrode,
    Electrolyte, Separator) -- schema order, not ``raw``'s own key order.
    Using it here (rather than a plain ``raw["Parameterisation"].keys()``
    walk) is what gives an absent-but-required child (a deleted SPMe
    ``Electrolyte``) its natural schema position instead of stranding it
    wherever ``document_completion``'s task walk happens to first name it
    (an implementation detail of that walk, not a position a reader would
    expect -- see :func:`_bucket_order`'s own docstring for the case this
    replaces). A schema-required child is listed here whether or not it is
    actually present, so it becomes a bucket in that position either way;
    any child ``raw`` actually has that the schema does not name (a custom
    section, or anything at all under Partial/undeclared, whose schema list
    is empty) is appended after, in ``raw``'s own order.
    """
    schema_order = [
        path[-1]
        for path in structure.required_sections(model)
        if len(path) == 2 and path[0] == "Parameterisation"
    ]
    parameterisation = raw.get("Parameterisation") if isinstance(raw, dict) else None
    present = list(parameterisation) if isinstance(parameterisation, dict) else []
    ordered = list(schema_order)
    for child_key in present:
        if child_key not in ordered:
            ordered.append(child_key)
    return ordered


def _bucket_order(
    raw: dict,
    model: str | None,
    tasks: tuple[CompletionTask, ...],
    merged_visible: tuple[IssuePair, ...],
) -> list[tuple[str, ...]]:
    """Ordered, de-duplicated bucket paths, first-appearance order.

    Three passes, each only adding a bucket path not already seen:

    1. ``raw`` itself, top-level key order (``Parameterisation``'s children
       walked via :func:`_parameterisation_child_order` -- schema order, so
       this pass alone produces sensible "document order" for everything
       schema-required, present or not -- flattened to their own bucket via
       :func:`_bucket_path_for`; a custom top-level dict, e.g. ``"Electrodes"``,
       gets its own bucket for free since nothing here treats it specially).
    2. ``tasks``, in ``document_completion``'s own document order -- a
       fallback for anything pass 1 did not already introduce (in practice
       only a nested absent section pass 1's schema list does not cover on
       its own, e.g. ``State``'s own required children once ``State`` itself
       is a bucket -- those still collapse into the ``State`` bucket via
       :func:`_bucket_path_for`, so this rarely adds a genuinely new entry).
    3. ``merged_visible``, in document order -- a safety net for a
       diagnostic naming a bucket neither pass above introduced. In practice
       this never fires for a resolvable path (its section already exists in
       ``raw`` or was already forced by a task), but F3 promises no drop
       path, so it is not skipped.

    :data:`DOCUMENT_BUCKET_PATH` is collected like any other bucket path
    here; :func:`bucket_page_content` moves it to the front.
    """
    order: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()

    def add(path: tuple[str, ...]) -> None:
        if path not in seen:
            seen.add(path)
            order.append(path)

    if isinstance(raw, dict):
        for key, value in raw.items():
            if key == "Parameterisation" and isinstance(value, dict):
                for child_key in _parameterisation_child_order(raw, model):
                    add(("Parameterisation", child_key))
            else:
                add((key,))

    for task in tasks:
        add(_resolve_bucket_path(raw, model, _task_owning_path(task)))

    for _diagnostic, nav_path in merged_visible:
        add(_resolve_bucket_path(raw, model, nav_path))

    return order


def bucket_page_content(
    raw: dict | None,
    model: str | None,
    partition: PartitionedIssues | None,
    tasks: tuple[CompletionTask, ...],
) -> PageBuckets:
    """Bucket a document's post-absorption diagnostics and completion tasks
    into the Validation page rail's per-section content (F2/F3).

    ``raw``/``model``/``partition``/``tasks`` are exactly what
    ``main_window._refresh_all`` already computes once per refresh
    (``core.completion.document_completion``/``partition_issues``) and feeds
    ``DiagnosticsPanel.refresh`` today -- this function does not touch
    ``bpx_gateway`` or a live document itself, only these four already-derived
    values, so it stays a pure projection like the rest of ``core.completion``.

    ``partition.visible`` is merged exactly once here (decision Q, matching
    the page-level Issues section today) before distributing pairs into
    buckets, so a bucket's own ``error_count``/``warning_count`` and the
    returned totals agree with each other and with the (not-yet-built) rail
    badge by construction.
    """
    if not isinstance(raw, dict):
        raw = {}
    merged_visible: tuple[IssuePair, ...] = (
        merge_union_pairs_by_location(partition.visible) if partition is not None else ()
    )

    order = _bucket_order(raw, model, tasks, merged_visible)
    if DOCUMENT_BUCKET_PATH in order:
        order = [DOCUMENT_BUCKET_PATH] + [path for path in order if path != DOCUMENT_BUCKET_PATH]

    issues_by_bucket: dict[tuple[str, ...], list[IssuePair]] = {}
    for pair in merged_visible:
        issues_by_bucket.setdefault(_resolve_bucket_path(raw, model, pair[1]), []).append(pair)

    required_by_bucket: dict[tuple[str, ...], list[CompletionTask]] = {}
    optional_by_bucket: dict[tuple[str, ...], list[CompletionTask]] = {}
    for task in tasks:
        key = _resolve_bucket_path(raw, model, _task_owning_path(task))
        target = required_by_bucket if task.required else optional_by_bucket
        target.setdefault(key, []).append(task)

    buckets: list[SectionBucket] = []
    for path in order:
        bucket_issues = tuple(issues_by_bucket.get(path, ()))
        required_tasks = tuple(required_by_bucket.get(path, ()))
        optional_tasks = tuple(optional_by_bucket.get(path, ()))
        error_count = sum(1 for diagnostic, _ in bucket_issues if diagnostic.severity == Severity.ERROR)
        warning_count = sum(1 for diagnostic, _ in bucket_issues if diagnostic.severity == Severity.WARNING)

        if path == DOCUMENT_BUCKET_PATH:
            buckets.append(
                SectionBucket(
                    path=path,
                    label="Document",
                    absent=False,
                    issues=bucket_issues,
                    required_tasks=required_tasks,
                    optional_tasks=optional_tasks,
                    required_total=None,
                    error_count=error_count,
                    warning_count=warning_count,
                )
            )
            continue

        absent = not _section_present(raw, path)
        required_total = (
            None
            if absent
            else completion.completion_for(path, _value_at(raw, path), model).required_total
        )
        buckets.append(
            SectionBucket(
                path=path,
                label=path[-1],
                absent=absent,
                issues=bucket_issues,
                required_tasks=required_tasks,
                optional_tasks=optional_tasks,
                required_total=required_total,
                error_count=error_count,
                warning_count=warning_count,
            )
        )

    return PageBuckets(
        buckets=tuple(buckets),
        error_count=sum(bucket.error_count for bucket in buckets),
        warning_count=sum(bucket.warning_count for bucket in buckets),
        outstanding_count=sum(bucket.outstanding_count for bucket in buckets),
    )
