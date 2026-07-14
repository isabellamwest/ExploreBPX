"""Completion query: what a document expects but does not yet have.

Completion is a pure, stateless projection over ``(raw, model)`` -- the same
shape as :func:`core.structure.addable_child_sections`. It is provably
distinct from validation (see ``PLAN-completion-track.md`` S1/S2): a
section-level ``mode="before"`` validator can raise before pydantic ever
checks that section's own required fields, so an absent field can leave the
validator's diagnostics byte-identical; an absent section always collapses to
one ``missing`` diagnostic, its inner required fields never enumerated; and,
more broadly (found while implementing this module, and folded into the
plan's corrected V1), ``bpx.BPX``'s root ``mode="before"`` validator raises
as soon as ``Parameterisation`` itself fails, which stops pydantic validating
``State``/``Validation`` at all -- so a document with any Parameterisation
problem shows zero diagnostics about State, **including the root-level
demand for State itself**: a ``mode="after"`` root validator raises
*"'State' section must be provided unless using a 'Partial' parameterisation"*
(a root ``value_error`` at ``loc=()``) once Parameterisation validates
cleanly. ``State`` IS required for every concrete model -- the original V1
("required by no model") was a short-circuit artifact: every skeleton probe
also has a broken Parameterisation, so the root validator never reached the
State check. Completion never reads diagnostics to decide what is expected;
it reads the schema and the raw dict directly -- except for this one demand,
which the JSON schema itself does not encode (``State`` is absent from the
root's own ``"required"`` list; the requirement lives only in the root
validator), so :func:`document_completion` special-cases it explicitly.

Terminology (decision B, use exactly): Expected = schema names the field for
this section. Required = schema requires it AND the model is concrete
(SPM/SPMe/DFN). Missing = expected field absent from raw. Outstanding =
Required and (absent OR committed null).

Two functions matter to callers, and they deliberately answer different
questions:

* :func:`completion_for` -- the per-section building block, mirroring
  :func:`core.structure.addable_child_sections`'s shape. Pure over
  ``(path, value, model)``. Returns every *Expected* field, Required or not
  (``MissingField.required`` distinguishes them) -- this is the parameter
  list's "fields to add" suggestions query (decision H), which shows
  optional fields too.
* :func:`document_completion` -- aggregates :func:`completion_for` across the
  whole document into an ordered list of :class:`CompletionTask` for the
  Validation page's Outstanding section. ``MISSING_FIELD`` tasks are
  **Required-only** (decision B: an *absent* Expected-but-optional field is
  never a document-level task; it only ever shows up as a suggestion via
  :func:`completion_for`). ``NULL_FIELD`` tasks are the opposite (decision D,
  REVISED 2026-07-14): every schema-Expected field committed as ``null``
  becomes a task, Required or not -- creating an expected field never makes
  the document look worse, so its calm Outstanding treatment doesn't depend
  on requiredness (the task's own ``required`` flag still drives whether the
  REQUIRED tag renders). ``MISSING_SECTION``/``DECLARE_MODEL`` are inherently
  Required by construction. A *custom* parameter (no schema entry at all)
  never gets a task of any kind -- its ``extra_forbidden`` is name-rejection,
  value-independent, so it must stay a plain, uncalmed Issue.

:func:`partition_issues` is a separate pure function that consumes a
document's already-attached diagnostics plus a task list, and decides which
diagnostics the Outstanding section already accounts for (decision E). It is
the only function here that touches :class:`core.validation.ValidatorDiagnostic`
objects; :func:`completion_for`/:func:`document_completion` never do.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

from . import bpx_gateway
from .bpx_gateway import FieldMeta
from .tree_model import TreeNode, build_tree
from .validation import Severity, ValidatorDiagnostic, merge_union_pairs_by_location

if TYPE_CHECKING:
    from .document import BPXDocument

#: The three models with a full, fixed schema shape. A "Required" flag (decision
#: B) only ever applies under one of these; an undeclared model or Partial
#: never marks anything Required (decision C).
CONCRETE_MODELS = frozenset({"SPM", "SPMe", "DFN"})


@dataclass(frozen=True)
class MissingField:
    """An expected parameter absent (or committed null) from a section."""

    alias: str
    required: bool
    meta: FieldMeta | None


@dataclass(frozen=True)
class SectionCompletion:
    """The completion state of a single section, keyed by ``(path, value, model)``."""

    #: Expected fields with no entry in ``value`` (feeds "fields to add").
    missing_fields: tuple[MissingField, ...]
    #: Every schema-Expected field present but committed as literal None
    #: (decision D, REVISED 2026-07-14 -- second user ruling, live review:
    #: "creating an expected field never makes the document look worse", so
    #: this is no longer gated on ``required``; ``MissingField.required``
    #: still says whether the REQUIRED tag shows). A *custom* parameter --
    #: not in ``expected_fields`` at all -- can never land here: its
    #: ``extra_forbidden`` rejects the name, not the emptiness, so filling a
    #: value fixes nothing and it must stay a plain, uncalmed Issue.
    null_fields: tuple[MissingField, ...]
    #: Required child sections (schema container properties) absent from
    #: ``value``, as full paths.
    missing_child_sections: tuple[tuple[str, ...], ...]
    #: Count of schema-required, non-container fields this section's
    #: definition declares -- the "M" in the Validation page's Outstanding
    #: group header ("<Section> -- N of M remaining", Phase 5). A pure schema
    #: fact: unlike ``MissingField.required``, it is **not** gated by
    #: ``model in CONCRETE_MODELS`` -- the one place this matters is the
    #: ``DECLARE_MODEL`` task's own group (an undeclared/garbage model), where
    #: a gated count would collapse to 0 and read as "N of 0 remaining"
    #: instead of the section's real shape.
    required_total: int


_EMPTY_SECTION = SectionCompletion((), (), (), 0)


def completion_for(path: tuple[str, ...], value: object, model: str | None) -> SectionCompletion:
    """Return the completion state of the section at ``path``.

    Pure over ``(path, value, model)`` -- never touches diagnostics. Delegates
    to :func:`core.bpx_gateway.expected_fields` for the schema shape; a path
    with no single schema definition (a Particle/Validation collection
    itself, decision N) yields an empty result rather than raising.
    Container-link fields (``meta.is_container``) never appear in
    ``missing_fields``/``null_fields`` -- they are sections, reported through
    ``missing_child_sections`` instead (mirrors the add-parameter popup's own
    container filter).
    """
    try:
        fields = bpx_gateway.expected_fields(path, model, value)
    except ValueError:
        return _EMPTY_SECTION

    present = value if isinstance(value, dict) else {}
    missing: list[MissingField] = []
    null_fields: list[MissingField] = []
    missing_child_sections: list[tuple[str, ...]] = []
    required_total = 0

    for expected in fields:
        required = expected.required and model in CONCRETE_MODELS
        if expected.meta.is_container:
            if required and expected.alias not in present:
                missing_child_sections.append(path + (expected.alias,))
            continue
        if expected.required:
            required_total += 1
        if expected.alias not in present:
            missing.append(MissingField(expected.alias, required, expected.meta))
        elif present[expected.alias] is None:
            null_fields.append(MissingField(expected.alias, required, expected.meta))

    return SectionCompletion(
        tuple(missing), tuple(null_fields), tuple(missing_child_sections), required_total
    )


class TaskKind(Enum):
    """What kind of outstanding work a :class:`CompletionTask` names."""

    DECLARE_MODEL = "declare_model"
    MISSING_SECTION = "missing_section"
    MISSING_FIELD = "missing_field"
    NULL_FIELD = "null_field"


@dataclass(frozen=True)
class CompletionTask:
    """One document-level unit of outstanding work."""

    kind: TaskKind
    #: Section path for a section task; full parameter path for a field task.
    path: tuple[str, ...]
    alias: str | None
    required: bool


def document_completion(raw: dict) -> tuple[CompletionTask, ...]:
    """Aggregate :func:`completion_for` across the whole document.

    ``MISSING_FIELD`` is Required-only (decision B): an *absent*
    Expected-but-optional field never appears here, even though
    :func:`completion_for` reports it as a suggestion for the same section.
    ``NULL_FIELD`` is the opposite (decision D, revised): every schema-
    Expected field committed ``null`` becomes a task regardless of
    requiredness. ``MISSING_SECTION``/``DECLARE_MODEL`` are inherently
    Required by construction.

    Rules (decisions C/M, all locked -- see the plan):

    * ``Header`` absent -> exactly one task, ``MISSING_SECTION ("Header",)``.
    * ``Header`` present but ``Model`` absent/unrecognised (not one of
      SPM/SPMe/DFN/Partial) -> exactly one task, ``DECLARE_MODEL`` at
      ``("Header", "Model")``. A garbage value also stays an Issue via the
      validator's own ``literal_error`` -- both are shown, deliberately (V6).
    * ``Model == "Partial"`` -> no tasks (nothing is Required under Partial;
      suggestions still come from :func:`completion_for` per section).
    * A concrete model walks every existing section (schema-resolvable, top-
      level and nested -- including ``Particle/<material>`` and
      ``Validation/<run>`` instances) via :func:`completion_for`. A section's
      own required-but-absent child sections surface as ``MISSING_SECTION``
      with their own fields *not* enumerated (decision M) -- this includes
      the well-known top structure (``Parameterisation``'s ``Cell``,
      electrodes, Electrolyte/Separator) and any deeper required container
      once its parent exists (e.g. ``State``'s ``Initial conditions``/
      ``Thermal environment``, once ``State`` itself has been added).
    * ``State`` absent on a concrete model -> ``MISSING_SECTION ("State",)``,
      required. This is the one section the schema-driven walk above cannot
      find on its own (corrected V1 -- see the module docstring): the
      demand is a root ``mode="after"`` validator, not a schema ``required``
      entry, so it is special-cased here rather than discovered generically.
      Not raised under Partial/undeclared -- the validator's own message
      exempts Partial, and an undeclared model already short-circuits above.

    Task order is document order: a section's own field tasks (schema
    declaration order, via ``expected_fields``) before its child-section
    tasks, before recursing into sections that already exist (walked in the
    raw dict's own key order), with the special-cased ``State`` absence
    reported last (it would otherwise sort after ``Parameterisation`` in the
    raw dict too).
    """
    if not isinstance(raw, dict):
        raw = {}
    header = raw.get("Header")
    if not isinstance(header, dict):
        return (CompletionTask(TaskKind.MISSING_SECTION, ("Header",), None, True),)

    model = header.get("Model")
    if model == "Partial":
        return ()
    if model not in CONCRETE_MODELS:
        return (CompletionTask(TaskKind.DECLARE_MODEL, ("Header", "Model"), "Model", True),)

    tasks: list[CompletionTask] = []
    if not isinstance(raw.get("Parameterisation"), dict):
        tasks.append(CompletionTask(TaskKind.MISSING_SECTION, ("Parameterisation",), None, True))

    _walk_completion(build_tree(raw), model, tasks)

    if not isinstance(raw.get("State"), dict):
        tasks.append(CompletionTask(TaskKind.MISSING_SECTION, ("State",), None, True))

    return tuple(tasks)


def _walk_completion(node: TreeNode, model: str, tasks: list[CompletionTask]) -> None:
    if node.path:
        section = completion_for(node.path, node.value, model)
        for missing in section.missing_fields:
            if not missing.required:
                # completion_for is all-Expected (feeds suggestions); document_completion
                # is Required-only (decision B) -- an optional absence is never a task.
                continue
            tasks.append(
                CompletionTask(
                    TaskKind.MISSING_FIELD, node.path + (missing.alias,), missing.alias, missing.required
                )
            )
        for null_field in section.null_fields:
            tasks.append(
                CompletionTask(
                    TaskKind.NULL_FIELD, node.path + (null_field.alias,), null_field.alias, null_field.required
                )
            )
        for child_path in section.missing_child_sections:
            tasks.append(CompletionTask(TaskKind.MISSING_SECTION, child_path, None, True))
    for child in node.children:
        _walk_completion(child, model, tasks)


#: Top-level components the validator's own ``loc`` convention drops
#: (plan V4, fully mapped 2026-07-14): a diagnostic owned by ``Header`` or by
#: ``Parameterisation`` carries a loc with that leading component stripped
#: (``missing ('BPX',)`` for absent ``Header.BPX``; ``('Cell',)`` for absent
#: ``Parameterisation.Cell``) -- the attachment pass passes these
#: unresolvable, prefix-stripped locs through as ``nav_path`` unchanged.
#: ``State`` and ``Validation`` are the opposite: their prefix is KEPT in
#: full (``('State','Thermal environment')``, ``('Validation','C/20','Time
#: [s]')``). A single-prefix strip therefore double-surfaces every Header
#: task (reviewed defect, fixed here): both prefixed and unprefixed forms
#: must be tried.
_STRIPPED_LOC_PREFIXES = (("Header",), ("Parameterisation",))


def _nav_path_candidates(path: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
    """Every ``nav_path`` a diagnostic for the task/parameter at ``path``
    might carry, per the validator's asymmetric loc convention (V4).

    A task path ``T`` matches a diagnostic nav_path ``N`` iff ``N == T``, or
    ``("Header",) + N == T``, or ``("Parameterisation",) + N == T`` --
    equivalently, ``T`` itself is always a candidate, plus ``T`` with its
    leading component stripped when that component is ``Header`` or
    ``Parameterisation``. ``("State",)``/``("Validation", ...)`` paths have
    no prefix to strip, so they match only themselves unchanged.
    """
    candidates = [path]
    if path[:1] in _STRIPPED_LOC_PREFIXES:
        candidates.append(path[1:])
    return tuple(candidates)


#: The exact wording bpx's root validator raises when a concrete model has no
#: ``State`` (corrected V1). Pinned here -- and by a regression test against
#: the real validator -- so a future bpx wording change fails loudly instead
#: of silently un-absorbing this one diagnostic.
STATE_REQUIRED_MESSAGE_FRAGMENT = "'State' section must be provided"


@dataclass(frozen=True)
class PartitionedIssues:
    """The document's diagnostics, split between the Issues and Outstanding
    surfaces (decision E), plus badge counts derived from ``visible`` only
    (decision G) so the panel and the rail badge can never disagree.

    Absorption re-seats a diagnostic; it never drops it (decision O, user:
    "never remove any validation ever"). ``absorbed_by_task`` is how a caller
    finds, for one Outstanding row, exactly which real validator messages it
    is standing in for -- keyed by the owning :class:`CompletionTask` itself
    (hashable: a frozen dataclass of hashable fields), so a renderer with a
    task in hand (``validation_panel`` already has one per row) can look its
    absorbed diagnostics up directly. ``absorbed`` (the flat list) is kept
    too, unchanged, for callers that only need counts/membership.
    """

    visible: tuple[tuple[ValidatorDiagnostic, tuple[str, ...]], ...]
    absorbed: tuple[tuple[ValidatorDiagnostic, tuple[str, ...]], ...]
    absorbed_by_task: dict[CompletionTask, tuple[tuple[ValidatorDiagnostic, tuple[str, ...]], ...]]
    error_count: int
    warning_count: int


def partition_issues(document: "BPXDocument", tasks: tuple[CompletionTask, ...]) -> PartitionedIssues:
    """Split ``document.iter_issues()`` into ``visible``/``absorbed`` against
    ``tasks`` (decision E), attributing each absorbed diagnostic to the
    specific task that covers it (decision O).

    A diagnostic absorbs into the first task it matches, tried in this order:

    (a) a ``MISSING_SECTION``/``MISSING_FIELD`` task, when the diagnostic's
        ``error_type`` is ``"missing"`` and its nav path matches one of that
        task's :func:`_nav_path_candidates` (reusing the nav path
        :meth:`BPXDocument.iter_issues` already derives -- never re-derived
        here; matching against candidates rather than a single stripped path
        is required because the validator's own loc convention is
        asymmetric, per V4); or
    (b) a ``NULL_FIELD`` task, when the diagnostic is attached to a parameter
        whose path matches one of that task's :func:`_nav_path_candidates`,
        regardless of ``error_type`` -- a committed-null union field raises
        two diagnostics, one per branch (V5), and both absorb into the same
        task; or
    (c) the ``MISSING_SECTION ("State",)`` task, when the diagnostic is the
        root ``value_error`` demanding ``State`` (corrected V1; plan decision
        E's one deliberate exception to the missing-only rule):
        ``error_type == "value_error"``, ``loc == ()``, and the message
        contains :data:`STATE_REQUIRED_MESSAGE_FRAGMENT`. Only matches when
        that task exists -- if ``State`` is present the diagnostic cannot
        occur, and under Partial no such task is ever raised, so the safety
        net below still applies.

    Everything else stays ``visible``, including Partial's union-branch
    ``missing`` errors (no tasks exist under Partial, so nothing matches --
    V9) and warning diagnostics (``PythonWarningDiagnostic`` carries neither
    ``error_type`` nor ``loc`` -- read both via ``getattr``). The validator is
    never silenced, only re-seated -- every absorbed diagnostic is still
    retrievable via ``absorbed``/``absorbed_by_task`` (decision O).

    ``error_count``/``warning_count`` are computed over ``visible`` after
    applying :func:`core.validation.merge_union_pairs_by_location` (decision
    Q): a page/badge count reflects displayed rows, not raw diagnostics, so a
    single null number's float/int pair counts once.
    """
    missing_task_by_path: dict[tuple[str, ...], CompletionTask] = {
        candidate: task
        for task in tasks
        if task.kind in (TaskKind.MISSING_SECTION, TaskKind.MISSING_FIELD)
        for candidate in _nav_path_candidates(task.path)
    }
    null_task_by_path: dict[tuple[str, ...], CompletionTask] = {
        candidate: task
        for task in tasks
        if task.kind is TaskKind.NULL_FIELD
        for candidate in _nav_path_candidates(task.path)
    }
    state_task = next(
        (task for task in tasks if task.kind is TaskKind.MISSING_SECTION and task.path == ("State",)),
        None,
    )

    visible: list[tuple[ValidatorDiagnostic, tuple[str, ...]]] = []
    absorbed: list[tuple[ValidatorDiagnostic, tuple[str, ...]]] = []
    absorbed_by_task: dict[CompletionTask, list[tuple[ValidatorDiagnostic, tuple[str, ...]]]] = {}
    for diagnostic, nav_path in document.iter_issues():
        error_type = getattr(diagnostic, "error_type", None)
        matched_task: CompletionTask | None = None
        if nav_path and error_type == "missing" and nav_path in missing_task_by_path:
            matched_task = missing_task_by_path[nav_path]
        elif nav_path and nav_path in null_task_by_path:
            matched_task = null_task_by_path[nav_path]
        elif (
            state_task is not None
            and not nav_path
            and error_type == "value_error"
            and STATE_REQUIRED_MESSAGE_FRAGMENT in getattr(diagnostic, "message", "")
        ):
            matched_task = state_task

        if matched_task is not None:
            pair = (diagnostic, nav_path)
            absorbed.append(pair)
            absorbed_by_task.setdefault(matched_task, []).append(pair)
        else:
            visible.append((diagnostic, nav_path))

    merged_visible = merge_union_pairs_by_location(tuple(visible))
    error_count = sum(1 for diagnostic, _ in merged_visible if diagnostic.severity == Severity.ERROR)
    warning_count = sum(1 for diagnostic, _ in merged_visible if diagnostic.severity == Severity.WARNING)
    return PartitionedIssues(
        tuple(visible),
        tuple(absorbed),
        {task: tuple(pairs) for task, pairs in absorbed_by_task.items()},
        error_count,
        warning_count,
    )
