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
from .values import is_grid_cell

# Interim until the remaining per-kind cards land; see docs/03-features.md §4
# "Input system". Kinds whose card depends on the stored value's shape --
# MAP, SERIES -- are dispatched in ``_card_class`` instead. FUNCTION now owns
# its own shape dispatch: ``FunctionCard`` is a mode strip that opens on
# whichever representation the committed value has.
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
    return all(is_grid_cell(item) for item in value)


def _card_class(parameter: ParameterItem) -> type[EditorCard]:
    # SERIES has exactly one representation (a one-column grid), so it needs no
    # mode strip -- only a fallback for a value that grid cannot represent.
    if parameter.kind is ParameterKind.SERIES:
        return SeriesCard if series_is_representable(parameter.value) else ReadOnlyCard
    # FUNCTION is a union-typed kind (docs/01-architecture.md). Its card is a
    # mode strip covering every legal representation -- including a conditional
    # Raw mode -- so the registry hands it every value unconditionally and the
    # card decides which mode to open in.
    if parameter.kind is ParameterKind.FUNCTION:
        return FunctionCard
    # MAP remains a shim until Phase 4c's MapCard lands: dispatch on the stored
    # value's shape so a dict-shaped value is never handed to a free-text card
    # that would commit its Python ``repr`` and corrupt it.
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
