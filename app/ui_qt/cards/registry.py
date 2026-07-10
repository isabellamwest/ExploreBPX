"""Maps a ``ParameterKind`` to its editing card (one card per kind)."""

from __future__ import annotations

from core.bpx_gateway import FieldMeta
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem

from .base import EditorCard
from .boolean import BooleanCard
from .enum import EnumCard
from .function import FunctionCard
from .integer import IntegerCard
from .raw import RawCard
from .scalar import ScalarCard
from .series import SeriesCard
from .text import TextCard
from .unknown import ReadOnlyCard

# Interim until the remaining per-kind cards land; see docs/03-features.md §4
# "Input system". Kinds whose card depends on the stored value's shape --
# FUNCTION, MAP, SERIES -- are dispatched in ``_card_class`` instead.
_REGISTRY = {
    ParameterKind.SCALAR: ScalarCard,
    ParameterKind.INTEGER: IntegerCard,
    ParameterKind.ENUM: EnumCard,
    ParameterKind.UNKNOWN: RawCard,
    ParameterKind.TEXT: TextCard,
    ParameterKind.BOOLEAN: BooleanCard,
}


def create_card(parameter: ParameterItem, meta: FieldMeta | None) -> EditorCard:
    """Return the editing card for a parameter, falling back to read-only."""
    card_cls = _card_class(parameter)
    return card_cls(parameter, meta)


def _is_grid_cell(value: object) -> bool:
    """Whether a stored item can round-trip through a grid cell.

    ``None`` qualifies: it is a blank cell, which reads back as ``None``. It has
    to, because the grid *produces* blank cells -- adding a row writes one --
    and a card that could not re-render its own output would turn itself
    read-only the moment the user added a row.

    ``bool`` does not, even though it is an ``int`` subclass. A grid renders
    ``True`` as the text ``"True"``, which reads back as the *string*
    ``"True"``, so committing an untouched neighbouring cell would silently
    rewrite a stored ``true``. The value is legal BPX (it validates as ``1``),
    so it is shown read-only rather than corrupted.
    """
    if value is None:
        return True
    return isinstance(value, (int, float, str)) and not isinstance(value, bool)


def series_is_representable(value: object) -> bool:
    """Whether a ``SERIES`` value can be shown in, and read back from, a grid.

    A ``None`` *value* (a freshly added parameter) is an empty grid; a ``None``
    *item* is a blank row. Anything that is not a flat list of cell-shaped
    items -- a dict, a nested list, a bool -- has no grid representation, so the
    registry keeps it read-only rather than let the card destroy it on commit.
    """
    if value is None:
        return True
    if not isinstance(value, list):
        return False
    return all(_is_grid_cell(item) for item in value)


def _card_class(parameter: ParameterItem) -> type[EditorCard]:
    # SERIES has exactly one representation (a one-column grid), so it needs no
    # mode strip -- only a fallback for a value that grid cannot represent.
    if parameter.kind is ParameterKind.SERIES:
        return SeriesCard if series_is_representable(parameter.value) else ReadOnlyCard
    # FUNCTION and MAP are union-typed kinds (docs/01-architecture.md): the
    # kind is declared by the schema, but their real per-kind cards -- a
    # mode-strip card for FUNCTION, MapCard for MAP -- are Phase 4 work. Until
    # then, dispatch on the stored value's shape so today's UX doesn't
    # regress, and so a table/map-shaped value is never handed to a free-text
    # card that would commit its Python ``repr`` and corrupt it.
    if parameter.kind is ParameterKind.FUNCTION:
        if isinstance(parameter.value, dict):
            return ReadOnlyCard  # table-valued function; real mode strip is Phase 4
        return FunctionCard
    if parameter.kind is ParameterKind.MAP:
        value = parameter.value
        if isinstance(value, dict):
            return ReadOnlyCard  # per-material map display; real MapCard is Phase 4
        if value is None:
            return RawCard
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return ScalarCard
        return RawCard  # any other invalid stored shape: let free text repair it
    return _REGISTRY.get(parameter.kind, ReadOnlyCard)
