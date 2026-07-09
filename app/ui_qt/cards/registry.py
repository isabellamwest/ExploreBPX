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
from .text import TextCard
from .unknown import ReadOnlyCard

# Interim until the remaining per-kind cards land; see docs/03-features.md §4
# "Input system". SERIES is spelled out explicitly (rather than relying on
# the ReadOnlyCard default below) so the mapping stays honest about what
# today's fallback actually covers.
_REGISTRY = {
    ParameterKind.SCALAR: ScalarCard,
    ParameterKind.INTEGER: IntegerCard,
    ParameterKind.ENUM: EnumCard,
    ParameterKind.UNKNOWN: RawCard,
    ParameterKind.TEXT: TextCard,
    ParameterKind.BOOLEAN: BooleanCard,
    ParameterKind.SERIES: ReadOnlyCard,
}


def create_card(parameter: ParameterItem, meta: FieldMeta | None) -> EditorCard:
    """Return the editing card for a parameter, falling back to read-only."""
    card_cls = _card_class(parameter)
    return card_cls(parameter, meta)


def _card_class(parameter: ParameterItem) -> type[EditorCard]:
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
