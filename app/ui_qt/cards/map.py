"""Material-map card: the mode strip for ``FloatInt | dict[str, FloatInt]`` fields.

``bpx.schema`` declares a handful of per-material fields (Degradation's LAM
fields, InitialConditions' hysteresis-state fields) as a union: a single scalar
applies to every material, or a dict keyed by particle name overrides it per
material. The kind is declared; the *mode* is the user's choice.

Mode labels are verbatim schema vocabulary (see :mod:`~.modal`): ``FloatInt``
and ``dict[str, FloatInt]``. A ``Raw`` mode is appended only when the committed
value fits neither structured mode, decided once at construction so the strip
never changes under the cursor.

The dict mode is offered even on a single-particle electrode, where it is
guaranteed invalid and has no particle names to suggest (decision F): guidance
informs, it does not lock, and the validator remains the single source of truth
for which materials are legal.
"""

from __future__ import annotations

from core import structure

from ..style import FIXED_UNIT_TOOLTIP
from .bodies import MaterialMapBody, NumberBody, RawJsonBody
from .modal import RAW_MODE, Mode, ModalCard
from .values import is_grid_cell

FLOAT_INT = "FloatInt"
DICT_STR_FLOAT_INT = "dict[str, FloatInt]"

_RAW_NOTICE = (
    "This value has no structured representation, so it is shown as raw JSON. "
    "Choosing another mode starts an empty editor; nothing changes until you commit."
)


def map_is_representable(value: object) -> bool:
    """Whether *value* renders in, and reads back from, the key/value grid.

    A representable map is a dict whose keys are strings and whose every value
    is a grid-shaped scalar (``int``/``float``/``str``, not ``bool``). A value
    that is itself a list or dict has no cell to sit in, so the whole map opens
    in ``Raw`` rather than being flattened -- nothing is invented or dropped.
    """
    if not isinstance(value, dict):
        return False
    return all(isinstance(key, str) for key in value) and all(
        is_grid_cell(item) for item in value.values()
    )


def initial_mode(value: object) -> str:
    """The mode a committed *value* opens in.

    ``None`` -- a freshly added parameter -- opens in the union's first declared
    member, an empty numeric editor. A ``bool`` validates as a number in BPX but
    no numeric editor can round-trip it, so it opens in ``Raw`` rather than being
    rewritten as ``"True"``.
    """
    if value is None:
        return FLOAT_INT
    if isinstance(value, bool):
        return RAW_MODE
    if isinstance(value, (int, float)):
        return FLOAT_INT
    if map_is_representable(value):
        return DICT_STR_FLOAT_INT
    return RAW_MODE


class MapCard(ModalCard):
    """Edits a ``FloatInt | dict[str, FloatInt]`` field through its modes."""

    def __init__(self, parameter, meta) -> None:
        opens_in = initial_mode(parameter.value)
        renamable = structure.can_rename_parameter(parameter.path, parameter.value)
        unit_tooltip = "" if renamable else FIXED_UNIT_TOOLTIP
        modes = [
            Mode(FLOAT_INT, NumberBody(parameter.unit, unit_tooltip)),
            Mode(DICT_STR_FLOAT_INT, MaterialMapBody(parameter.key_suggestions)),
        ]
        if opens_in == RAW_MODE:
            modes.append(Mode(RAW_MODE, RawJsonBody(_RAW_NOTICE)))
        labels = [mode.label for mode in modes]
        super().__init__(parameter, meta, modes, labels.index(opens_in))
