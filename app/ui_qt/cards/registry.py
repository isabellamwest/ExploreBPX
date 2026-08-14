"""Maps a ``ParameterKind`` to its editing card (one card per kind)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from core.parameter_types import ParameterKind
from core.values import is_grid_cell

from .boolean import BooleanCard
from .enum import EnumCard
from .function import FunctionCard, table_is_representable
from .integer import IntegerCard
from .map import MapCard
from .modal import RawValueCard
from .raw import RawCard
from .scalar import ScalarCard
from .series import SeriesCard
from .table import TableCard
from .text import TextCard
from .unknown import ReadOnlyCard

if TYPE_CHECKING:
    from core.bpx_gateway import FieldMeta
    from core.tree_model import ParameterItem

    from .base import EditorCard

# Kinds with one fixed card. The union kinds (FUNCTION, MAP) own their own mode
# dispatch -- each is a strip that opens on whichever representation the
# committed value has -- so they are handled in ``_build_card`` rather than
# here. The single-representation kinds (SERIES, TABLE) also live there,
# because they fall back to a Raw editor when the stored value cannot be shown
# in their grid.
_REGISTRY = {
    ParameterKind.SCALAR: ScalarCard,
    ParameterKind.INTEGER: IntegerCard,
    ParameterKind.ENUM: EnumCard,
    ParameterKind.UNKNOWN: RawCard,
    ParameterKind.TEXT: TextCard,
    ParameterKind.BOOLEAN: BooleanCard,
}


def series_is_representable(value: object) -> bool:
    """Whether a ``SERIES`` value can be shown in, and read back from, a grid.

    A ``None`` *value* (a freshly added parameter) is an empty grid; a ``None``
    *item* is a blank row. Anything that is not a flat list of cell-shaped
    items -- a dict, a nested list, a bool -- has no grid representation, so the
    registry hands it a Raw JSON editor (which keeps its structure intact)
    rather than let a grid or free-text card destroy it on commit.
    """
    if value is None:
        return True
    if not isinstance(value, list):
        return False
    return all(is_grid_cell(item) for item in value)


#: Notice shown when a single-representation kind's value cannot be shown in its
#: grid and falls back to the Raw JSON editor.
_SERIES_RAW_NOTICE = (
    "This value is not a flat list of numbers, so it cannot be shown as a "
    "series grid. It is shown as raw JSON instead, with its structure intact."
)
_TABLE_RAW_NOTICE = (
    "This value is not a rectangular x/y table, so it cannot be shown as a "
    "table grid. It is shown as raw JSON instead, with its structure intact."
)


def create_card(parameter: ParameterItem, meta: FieldMeta | None) -> EditorCard:
    """Return the editing card for a parameter."""
    return _build_card(parameter, meta)


def _build_card(parameter: ParameterItem, meta: FieldMeta | None) -> EditorCard:
    # FUNCTION and MAP are union-typed kinds. Each card
    # is a mode strip covering every legal representation -- including a
    # conditional Raw mode -- so the registry hands it every value
    # unconditionally and the card decides which mode to open in.
    if parameter.kind is ParameterKind.FUNCTION:
        return FunctionCard(parameter, meta)
    if parameter.kind is ParameterKind.MAP:
        return MapCard(parameter, meta)
    # SERIES and TABLE each have exactly one grid representation, so they need no
    # mode strip -- only a Raw fallback for a value the grid cannot hold, which
    # keeps the value editable without a free-text card corrupting its structure.
    if parameter.kind is ParameterKind.SERIES:
        if series_is_representable(parameter.value):
            return SeriesCard(parameter, meta)
        return RawValueCard(parameter, meta, _SERIES_RAW_NOTICE)
    if parameter.kind is ParameterKind.TABLE:
        if table_is_representable(parameter.value):
            return TableCard(parameter, meta)
        return RawValueCard(parameter, meta, _TABLE_RAW_NOTICE)
    # Every kind a ParameterItem can actually carry is handled above or in
    # _REGISTRY -- ``test_cards.py`` proves the dispatch total, so this
    # default never fires today. It stays as the last resort for a kind
    # added to the enum before its editor exists: an app whose whole job is
    # opening broken files must degrade to a read-only view of the value,
    # never to a KeyError where the Inspector should be.
    return _REGISTRY.get(parameter.kind, ReadOnlyCard)(parameter, meta)
