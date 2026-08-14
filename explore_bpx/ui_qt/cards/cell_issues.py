"""Map validator diagnostics onto the grid cells they blame.

The validator is the source of truth; the UI only *presents* its diagnostics.
For a list-valued field it already says which element is wrong -- a bad series
entry reports ``('Validation', 'run', 'Time [s]', '1', 'float')``, a bad table
point ``('…', 'OCP [V]', 'InterpolatedTable', 'y', '1')`` -- so a grid can tint
exactly that cell and show the validator's own message on hover.

No BPX knowledge is invented here. If a diagnostic carries no element index
(a whole-field type error, a model-level check) it simply maps to no cell and
stays where it already is: the parameter's validity badge and Issues tab.

Only ``PydanticErrorDiagnostic`` ever carries a ``loc`` at all -- warnings and
caught-exception diagnostics have none (see ``explore_bpx/core/validation.py``) -- and
its severity is always ``ERROR``, so a tinted cell is always an error, never a
warning; the tint's colour needs no severity check to be correct.
"""

from __future__ import annotations

#: A grid cell, as ``(row, column)``.
Cell = tuple[int, int]

#: The two columns of an ``InterpolatedTable`` grid, in display order.
_TABLE_COLUMNS = ("x", "y")


def series_cells(issues, alias: str) -> dict[Cell, str]:
    """Cells blamed by *issues* in a one-column series grid keyed by *alias*.

    The element index is the first integer following the parameter's own alias
    in the diagnostic's location.
    """
    found: dict[Cell, list[str]] = {}
    for issue in issues:
        row = _index_after(_loc(issue), alias)
        if row is not None:
            found.setdefault((row, 0), []).append(_message(issue))
    return {cell: "\n".join(_unique(messages)) for cell, messages in found.items()}


def experiment_cells(issues, aliases: tuple[str, ...]) -> dict[Cell, str]:
    """Cells blamed by *issues* in an N-named-column Validation-run grid.

    Generalises :func:`series_cells` (one column) and :func:`table_cells` (a
    fixed ``x``/``y`` pair) to any number of named columns -- ``ExperimentCard``
    shows whichever subset of Time/Current/Voltage/Temperature the run holds,
    in schema order, and the column index a diagnostic maps to depends on
    which of those are actually present. The location names the column's own
    alias and then the element index, exactly like ``series_cells``.
    """
    found: dict[Cell, list[str]] = {}
    for issue in issues:
        loc = _loc(issue)
        for column, alias in enumerate(aliases):
            row = _index_after(loc, alias)
            if row is not None:
                found.setdefault((row, column), []).append(_message(issue))
                break
    return {cell: "\n".join(_unique(messages)) for cell, messages in found.items()}


def table_cells(issues) -> dict[Cell, str]:
    """Cells blamed by *issues* in a two-column ``x``/``y`` table grid.

    The location names the column (``x`` or ``y``) and then the row index.
    """
    found: dict[Cell, list[str]] = {}
    for issue in issues:
        loc = _loc(issue)
        for column, name in enumerate(_TABLE_COLUMNS):
            row = _index_after(loc, name)
            if row is not None:
                found.setdefault((row, column), []).append(_message(issue))
                break
    return {cell: "\n".join(_unique(messages)) for cell, messages in found.items()}


# ----------------------------------------------------------------------


def _loc(issue) -> tuple[str, ...]:
    """A diagnostic's location, or ``()`` for kinds that carry none."""
    return tuple(getattr(issue, "loc", ()) or ())


def _message(issue) -> str:
    return getattr(issue, "message", "") or ""


def _index_after(loc: tuple[str, ...], name: str) -> int | None:
    """The integer immediately following *name* in *loc*, if any.

    ``loc`` parts arrive stringified, so ``'1'`` is the index 1. A part that is
    not a plain integer (``'float'``, ``'InterpolatedTable'``) is not an index.
    ``str(candidate)`` guards a part that is not already a string -- today's
    validator always stringifies ``loc``, but a bare ``int`` must never raise
    ``AttributeError`` here instead of simply not matching.
    """
    for position, part in enumerate(loc[:-1]):
        if part == name:
            candidate = str(loc[position + 1])
            if candidate.isdigit():
                return int(candidate)
    return None


def _unique(messages: list[str]) -> list[str]:
    """De-duplicate while preserving order: one union member per failed type
    yields several near-identical messages for the same cell."""
    seen: set[str] = set()
    ordered: list[str] = []
    for message in messages:
        if message not in seen:
            seen.add(message)
            ordered.append(message)
    return ordered
