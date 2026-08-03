"""Pure row model for the Source page.

Turns the main document's raw dict -- plus, when one is docked, the reference
snapshot's raw dict -- into one flat, ordered list of display rows the Source
page renders as aligned panes. Frontend-agnostic and side-effect-free, like
:mod:`core.compare`, which stays the single diff engine: every row state here
is looked up from :func:`core.compare.compare`, never recomputed.

Ordering is the main document's own raw order (sections and leaves
interleaved exactly as the JSON file has them, not leaves-first), with
reference-only keys slotted in after the nearest preceding shared key in the
reference's own order -- so both panes read top-to-bottom in file order and
still stay row-aligned. With no reference docked the same builder renders the
single-pane mode: identical rows, no states.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum

from . import bpx_gateway
from .compare import ComparisonResult, RowState, compare
from .tree_model import is_object_node


class RowKind(str, Enum):
    """What one Source-page row is."""

    SECTION = "section"
    PARAM = "param"


_DIFFERENCE_STATES = (RowState.DIFFERS, RowState.FILLABLE, RowState.REF_ONLY)


@dataclass(frozen=True)
class SourceRow:
    """One aligned row of the Source page."""

    kind: RowKind
    #: Full path from the document root; for PARAM rows the last element is
    #: the parameter key itself.
    path: tuple[str, ...]
    #: Whether this row exists on each side; the absent side renders as the
    #: flat gap block. With no reference docked in_reference is always False.
    in_main: bool
    in_reference: bool
    #: PARAM only: the committed raw value on each side. ``None`` when the
    #: side lacks the key -- indistinguishable from a literal null, so
    #: callers branch on in_main/in_reference, never on the value alone.
    main_value: object = None
    ref_value: object = None
    #: PARAM only; ``None`` while no reference is docked.
    state: RowState | None = None

    @property
    def key(self) -> str:
        """The row's own key: last path element."""
        return self.path[-1]

    @property
    def depth(self) -> int:
        """Nesting depth: 0 for a root-level section or leaf."""
        return len(self.path) - 1

    @property
    def closable(self) -> bool:
        """Rendered whole over several lines and closable to a one-line
        ``"key": table`` summary (decision 15): any dict/list leaf value."""
        return self.kind is RowKind.PARAM and (
            isinstance(self.main_value, (dict, list))
            or isinstance(self.ref_value, (dict, list))
        )

    @property
    def is_difference(self) -> bool:
        """A target for the page's difference stepper: a differs/fillable/
        ref-only parameter, or a whole-section ghost header. Main-only is
        never a difference (absence in a reference is not a defect)."""
        if self.kind is RowKind.SECTION:
            return not self.in_main and self.in_reference
        return self.state in _DIFFERENCE_STATES


def format_value(value: object) -> str:
    """One-line JSON rendering of a raw value, exactly as a JSON writer
    would emit it (ensure_ascii keeps µ and friends readable)."""
    return json.dumps(value, ensure_ascii=False)


def _merged_keys(main: dict, ref: dict) -> list[str]:
    """Both sides' keys in one aligned order: main keys in main order,
    reference-only keys inserted after the nearest preceding shared key in
    the reference's own order (before any shared key -> the very front)."""
    trailing: dict[str | None, list[str]] = {}
    anchor: str | None = None
    for key in ref:
        if key in main:
            anchor = key
        else:
            trailing.setdefault(anchor, []).append(key)
    merged = list(trailing.get(None, []))
    for key in main:
        merged.append(key)
        merged.extend(trailing.get(key, []))
    return merged


def _param_row(
    path: tuple[str, ...],
    main: dict,
    ref: dict,
    comparison: ComparisonResult | None,
) -> SourceRow:
    key = path[-1]
    state = None
    if comparison is not None:
        diff = comparison.row(path[:-1], key)
        state = diff.state if diff is not None else None
    return SourceRow(
        kind=RowKind.PARAM,
        path=path,
        in_main=key in main,
        in_reference=key in ref,
        main_value=main.get(key),
        ref_value=ref.get(key),
        state=state,
    )


def _walk(
    path: tuple[str, ...],
    main: dict,
    ref: dict,
    comparison: ComparisonResult | None,
    rows: list[SourceRow],
) -> None:
    for key in _merged_keys(main, ref):
        child_path = path + (key,)
        meta = bpx_gateway.field_meta(child_path)
        main_is_object = key in main and is_object_node(main[key], meta)
        ref_is_object = key in ref and is_object_node(ref[key], meta)
        if main_is_object or ref_is_object:
            rows.append(
                SourceRow(
                    kind=RowKind.SECTION,
                    path=child_path,
                    in_main=main_is_object,
                    in_reference=ref_is_object,
                )
            )
            _walk(
                child_path,
                main[key] if main_is_object else {},
                ref[key] if ref_is_object else {},
                comparison,
                rows,
            )
            # Same key, section on one side but a leaf on the other: the
            # leaf side still owns a row (compare classifies it MAIN_ONLY /
            # REF_ONLY within the parent), rendered after the section.
            if (key in main and not main_is_object) or (
                key in ref and not ref_is_object
            ):
                rows.append(
                    _param_row(
                        child_path,
                        main if not main_is_object else {},
                        ref if not ref_is_object else {},
                        comparison,
                    )
                )
        else:
            rows.append(_param_row(child_path, main, ref, comparison))


def build_rows(main_raw: dict, ref_raw: dict | None = None) -> list[SourceRow]:
    """The Source page's full row list, in render order.

    With ``ref_raw`` docked, rows carry :class:`core.compare.RowState`
    states from the one shared diff engine; with ``None`` (single-pane
    mode) every row has ``state=None`` and ``in_reference=False``.
    Pure: never mutates either input.
    """
    main_root = main_raw if isinstance(main_raw, dict) else {}
    if ref_raw is None:
        comparison = None
        ref_root: dict = {}
    else:
        ref_root = ref_raw if isinstance(ref_raw, dict) else {}
        comparison = compare(main_root, ref_root)
    rows: list[SourceRow] = []
    _walk((), main_root, ref_root, comparison, rows)
    return rows
