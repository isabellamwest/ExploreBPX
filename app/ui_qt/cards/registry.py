"""Maps a ``ParameterKind`` to its editing card (one card per kind)."""

from __future__ import annotations

from core.bpx_gateway import FieldMeta
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem

from .base import EditorCard
from .enum import EnumCard
from .integer import IntegerCard
from .scalar import ScalarCard
from .unknown import ReadOnlyCard

_REGISTRY = {
    ParameterKind.SCALAR: ScalarCard,
    ParameterKind.INTEGER: IntegerCard,
    ParameterKind.ENUM: EnumCard,
}


def create_card(parameter: ParameterItem, meta: FieldMeta | None) -> EditorCard:
    """Return the editing card for a parameter, falling back to read-only."""
    card_cls = _REGISTRY.get(parameter.kind, ReadOnlyCard)
    return card_cls(parameter, meta)
