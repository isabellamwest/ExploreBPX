"""Pure comparison engine between a main document's raw dict and a reference
snapshot's raw dict.

Frontend-agnostic and side-effect-free: :func:`compare` never mutates its
inputs, imports nothing from ``state``/``ui_qt``, and knows no BPX spec logic
beyond structural traversal -- it walks the raw dict exactly the way
:mod:`core.tree_model` builds the explorer tree (:func:`tree_model.is_object_node`
decides section vs. leaf), so its sections line up with the app's own tree
sections without hardcoding a single section name.

Matching is by full literal key at each nesting level (locked decision 1):
``"Thickness [m]"`` and ``"Thickness [micron]"`` are two different keys, never
unit-converted or fuzzy-matched. Difference is raw inequality of the committed
value (locked decision 2), via :func:`raw_equal` -- structural equality on the
parsed JSON, but type-aware at the leaves (:func:`core.values.values_equal`)
so ``true`` (a ``bool``) never counts as equal to ``1`` (an ``int``), and
``1`` (an ``int``) never counts as equal to ``1.0`` (a ``float``): both are
real, type-changing edits in the app's own convention, not a no-op. No
numeric tolerance, no normalisation.

"Empty" reuses the app's existing notion from :mod:`core.completion` (its
``NULL_FIELD`` rule): a committed literal ``None``. Nothing new is invented.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import bpx_gateway
from .tree_model import is_object_node
from .values import values_equal


class RowState(str, Enum):
    """The comparison outcome of one key within a section."""

    EQUAL = "equal"
    DIFFERS = "differs"
    FILLABLE = "fillable"
    MAIN_ONLY = "main_only"
    REF_ONLY = "ref_only"


_DIFFER_STATES = (RowState.DIFFERS, RowState.FILLABLE)


def raw_equal(main_value: object, ref_value: object) -> bool:
    """Structural equality on two raw JSON values, type-aware at the leaves."""
    if isinstance(main_value, dict) and isinstance(ref_value, dict):
        if main_value.keys() != ref_value.keys():
            return False
        return all(raw_equal(main_value[key], ref_value[key]) for key in main_value)
    if isinstance(main_value, list) and isinstance(ref_value, list):
        return len(main_value) == len(ref_value) and all(
            raw_equal(a, b) for a, b in zip(main_value, ref_value)
        )
    return values_equal(main_value, ref_value)


def _is_empty(value: object) -> bool:
    return value is None


@dataclass(frozen=True)
class RowDiff:
    """One key's comparison outcome within a SectionDiff."""

    state: RowState
    #: The reference's raw value, when the key is present there
    #: (EQUAL/DIFFERS/FILLABLE/REF_ONLY); ``None`` for MAIN_ONLY (the
    #: reference has no such key at all -- a literal ``None`` there would be
    #: indistinguishable from "the ref value is null", so callers must
    #: branch on ``state``, never on this alone).
    ref_value: object = None


@dataclass(frozen=True)
class SectionDiff:
    """One section path's comparison outcome.

    A "section" here is exactly a core.tree_model object node -- something
    core.tree_model.is_object_node would render as a navigable tree section,
    not a leaf parameter -- so a UI walking this result lines up with the
    app's own explorer tree one-to-one.
    """

    #: Full path from the document root, e.g. ("Parameterisation", "Cell").
    path: tuple[str, ...]
    #: Whether this section exists (as an object node) in the main document.
    in_main: bool
    #: Whether this section exists (as an object node) in the reference.
    in_reference: bool
    #: Direct leaf keys owned by this section (child object nodes are their
    #: own separate SectionDiff), union of both sides.
    rows: dict[str, RowDiff] = field(default_factory=dict)

    @property
    def is_ghost(self) -> bool:
        """Whole section absent from the main, present in the reference."""
        return not self.in_main and self.in_reference

    @property
    def is_main_only(self) -> bool:
        """Whole section present in the main, absent from the reference."""
        return self.in_main and not self.in_reference

    @property
    def differ_count(self) -> int:
        """Rows that differ, including fillable (locked decision 2/3)."""
        return sum(1 for row in self.rows.values() if row.state in _DIFFER_STATES)

    @property
    def ref_only_count(self) -> int:
        """Ghost rows directly in this section (every row, for a ghost
        section whose main side is entirely absent)."""
        return sum(1 for row in self.rows.values() if row.state is RowState.REF_ONLY)

    @property
    def main_only_count(self) -> int:
        """Main-only rows directly in this section (every row, for a
        main-only section whose reference side is entirely absent)."""
        return sum(1 for row in self.rows.values() if row.state is RowState.MAIN_ONLY)

    @property
    def ghost_keys(self) -> tuple[str, ...]:
        """Keys present only in the reference, in this section."""
        return tuple(key for key, row in self.rows.items() if row.state is RowState.REF_ONLY)

    @property
    def has_equal_row(self) -> bool:
        """At least one row matches the reference exactly. Used by the tree's
        pale "equal" gutter bar to tell a genuinely-compared, all-matching
        section from a pure container (no rows of its own at all)."""
        return any(row.state is RowState.EQUAL for row in self.rows.values())


@dataclass(frozen=True)
class ComparisonResult:
    """The full comparison between a main raw dict and a reference raw dict.

    Computed once by compare(); cheap to query section-by-section afterwards
    (no incremental recompute -- a caller re-runs compare() after any edit
    and reads whatever section/totals it currently needs).
    """

    sections: dict[tuple[str, ...], SectionDiff]

    def section(self, path: tuple[str, ...]) -> SectionDiff | None:
        """The comparison for the section at path, or None if path is an
        object node in neither the main nor the reference."""
        return self.sections.get(path)

    def row(self, section_path: tuple[str, ...], key: str) -> RowDiff | None:
        """The comparison for key directly inside the section at
        section_path, or None if that section/key combination was never
        seen on either side."""
        section = self.sections.get(section_path)
        return section.rows.get(key) if section is not None else None

    @property
    def ghost_sections(self) -> tuple[SectionDiff, ...]:
        """Whole sections absent from the main, present in the reference."""
        return tuple(section for section in self.sections.values() if section.is_ghost)

    @property
    def main_only_sections(self) -> tuple[SectionDiff, ...]:
        """Whole sections present in the main, absent from the reference."""
        return tuple(section for section in self.sections.values() if section.is_main_only)

    @property
    def differ_count(self) -> int:
        """Whole-file count of DIFFERS + FILLABLE rows."""
        return sum(section.differ_count for section in self.sections.values())

    @property
    def ref_only_count(self) -> int:
        """Whole-file count of REF_ONLY rows, including every row inside a
        ghost section."""
        return sum(section.ref_only_count for section in self.sections.values())

    @property
    def main_only_count(self) -> int:
        """Whole-file count of MAIN_ONLY rows, including every row inside a
        main-only section."""
        return sum(section.main_only_count for section in self.sections.values())


def _collect_sections(raw: dict) -> dict[tuple[str, ...], dict[str, object]]:
    """Every section path reachable in raw, mapped to the direct leaf
    keys/values it owns.

    Mirrors core.tree_model._build_node's own object-node/leaf split exactly
    (core.tree_model.is_object_node, schema-metadata-first with a shape
    fallback): a child that is itself an object node recurses into its own
    entry instead of being listed as a leaf here, so a section's rows here
    always match the app's own parameter-list rows for that section.
    """
    if not isinstance(raw, dict):
        raw = {}
    sections: dict[tuple[str, ...], dict[str, object]] = {}

    def walk(path: tuple[str, ...], value: dict) -> None:
        leaves: dict[str, object] = {}
        for key, child_value in value.items():
            child_path = path + (key,)
            child_meta = bpx_gateway.field_meta(child_path)
            if is_object_node(child_value, child_meta):
                walk(child_path, child_value)
            else:
                leaves[key] = child_value
        sections[path] = leaves

    walk((), raw)
    return sections


def _diff_rows(main_leaves: dict[str, object], ref_leaves: dict[str, object]) -> dict[str, RowDiff]:
    rows: dict[str, RowDiff] = {}
    for key, main_value in main_leaves.items():
        if key not in ref_leaves:
            rows[key] = RowDiff(RowState.MAIN_ONLY)
            continue
        ref_value = ref_leaves[key]
        if raw_equal(main_value, ref_value):
            rows[key] = RowDiff(RowState.EQUAL, ref_value)
        elif _is_empty(main_value) and not _is_empty(ref_value):
            rows[key] = RowDiff(RowState.FILLABLE, ref_value)
        else:
            rows[key] = RowDiff(RowState.DIFFERS, ref_value)
    for key, ref_value in ref_leaves.items():
        if key not in main_leaves:
            rows[key] = RowDiff(RowState.REF_ONLY, ref_value)
    return rows


def compare(main_raw: dict, ref_raw: dict) -> ComparisonResult:
    """Compare a main document's raw dict against a reference snapshot's raw
    dict. Pure: never mutates either input.

    Traverses both independently into sections (_collect_sections), then
    walks every section path either side has, in the main's own document
    order followed by any reference-only section order -- dict iteration
    order never affects the result itself (every state/count exposed here is
    order-independent), only the presentation order a future caller might
    read sections in.
    """
    main_sections = _collect_sections(main_raw)
    ref_sections = _collect_sections(ref_raw)

    order: list[tuple[str, ...]] = []
    seen: set[tuple[str, ...]] = set()
    for path in list(main_sections) + list(ref_sections):
        if path not in seen:
            seen.add(path)
            order.append(path)

    sections: dict[tuple[str, ...], SectionDiff] = {}
    for path in order:
        in_main = path in main_sections
        in_reference = path in ref_sections
        rows = _diff_rows(main_sections.get(path, {}), ref_sections.get(path, {}))
        sections[path] = SectionDiff(
            path=path, in_main=in_main, in_reference=in_reference, rows=rows
        )

    return ComparisonResult(sections=sections)


def matching_table_rows(
    main_rows: list[list[object]], ref_rows: list[list[object]]
) -> list[bool]:
    """For each row in *ref_rows*, whether an identical ``(x, y)`` pair
    exists somewhere in *main_rows* -- exact equality per cell
    (:func:`values.values_equal`), the same leaf rule :func:`raw_equal` uses
    for a whole value. Order-independent: a matching main row need not sit
    at the same index as the reference row it matches.

    Presentational, not part of the ``compare()`` traversal above: the
    reference card's read-only table grid (``ui_qt.cards``) uses this to
    mark a reference row that genuinely differs from every row the main
    draft holds, distinct from one that happens to coincide with one.
    Never mutates either input.
    """
    return [
        any(values_equal(mx, rx) and values_equal(my, ry) for mx, my in main_rows)
        for rx, ry in ref_rows
    ]


def merged_row_state(rows: list[RowDiff | None]) -> RowState | None:
    """The single state one key wears against **all** pinned references.

    Every surface that shows one mark per key against several references --
    the parameter-list row bar, the tree gutter (design rule 6) -- needs the
    same rule, so it lives here once rather than being re-derived per widget.

    Disagreement resolves toward the louder fact, because a mark that stays
    quiet while some reference disagrees would be a lie:

    * any reference differing (``DIFFERS``/``FILLABLE``) wins outright;
    * failing that, any reference agreeing gives ``EQUAL``;
    * ``REF_ONLY`` next (the key exists in some reference and not in main);
    * ``MAIN_ONLY`` last (some reference was compared and simply lacks it);
    * ``None`` when no reference has anything to say about this key at all.

    ``DIFFERS`` and ``FILLABLE`` cannot genuinely conflict -- they are told
    apart by whether the *main* value is empty, and every reference is
    compared against the same main -- so the first differing state found is
    returned as-is rather than being flattened to one of the two.
    """
    seen = [row.state for row in rows if row is not None]
    for state in seen:
        if state in _DIFFER_STATES:
            return state
    for candidate in (RowState.EQUAL, RowState.REF_ONLY, RowState.MAIN_ONLY):
        if candidate in seen:
            return candidate
    return None


def merged_ghost_keys(sections: list[SectionDiff | None]) -> tuple[str, ...]:
    """The union of one section's ghost keys across every pinned reference,
    ordered by the pin that first contributed each key.

    A key only some references carry is still a ghost row -- it exists
    somewhere the main document does not have it -- so the union, not the
    intersection, is what the parameter list renders.
    """
    keys: list[str] = []
    for section in sections:
        if section is None:
            continue
        for key in section.ghost_keys:
            if key not in keys:
                keys.append(key)
    return tuple(keys)


@dataclass(frozen=True)
class ValueGroup:
    """One Card Ledger row (multi-reference track, design rule 3): every
    pinned reference whose value at a key is identical, grouped together."""

    #: Pin-order indices, into the caller's own reference list, of every
    #: reference sharing ``value`` at this key.
    indices: tuple[int, ...]
    #: The shared raw value (whatever :func:`raw_equal` says every member's
    #: ``RowDiff.ref_value`` is equal to).
    value: object
    #: Whether ``value`` equals the main document's own value at this key --
    #: read straight off the group's ``RowState`` (see below), never
    #: recomputed against a separately-supplied main value.
    equals_main: bool


def group_reference_values(rows: list[RowDiff | None]) -> tuple[ValueGroup, ...]:
    """Group one key's per-reference :class:`RowDiff`\\ s by identical value
    (Card Ledger, design rule 3), for a caller with N pinned references and
    one ``compare()`` result per reference.

    *rows* is one entry per pinned reference, in pin order: the row for this
    key from that reference's own ``ComparisonResult.row()``, or ``None``
    when the reference has no comparison there at all (its own section is
    absent). A ``None`` entry and a ``MAIN_ONLY`` row (this particular
    reference has no value for the key -- the opposite-direction case of
    ``None``) both contribute nothing: there is no reference value to show or
    pull. A ``REF_ONLY`` row (the key exists in no reference's main-only
    sense -- the ghost-card case) groups exactly like any other state, since
    ``ghost_card.py`` reuses this same helper.

    Grouping uses :func:`raw_equal`, the same rule ``compare()`` itself uses,
    so identical nested tables/functions group exactly as identical scalars
    do. Order is preserved twice over: groups appear in the order their
    first member was pinned, and each group's own ``indices`` stay pin-order
    too. ``equals_main`` is read straight off the shared ``RowState``
    (``EQUAL``): identical values were necessarily compared against the same
    main value, so every member of a group already carries the same outcome.
    """
    groups: list[ValueGroup] = []
    for index, row in enumerate(rows):
        if row is None or row.state is RowState.MAIN_ONLY:
            continue
        for position, group in enumerate(groups):
            if raw_equal(group.value, row.ref_value):
                groups[position] = ValueGroup(group.indices + (index,), group.value, group.equals_main)
                break
        else:
            groups.append(ValueGroup((index,), row.ref_value, row.state is RowState.EQUAL))
    return tuple(groups)
