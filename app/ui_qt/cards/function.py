"""Function-expression card: the mode strip for ``FloatFunctionTable`` fields.

``bpx.schema`` declares these fields as
``FloatFunctionTable = Union[float, int, Function, InterpolatedTable]``, so a
single parameter may legally hold a number, an expression string, or a table of
``x``/``y`` points. The kind is declared; the *mode* is the user's choice.

Mode labels are verbatim schema vocabulary (see :mod:`~.modal`): ``float`` and
``int`` fold into the one ``FloatInt`` button -- bpx's own alias for exactly
that union, and what the numeric editor already emits.

A ``Raw`` mode is appended only when the *committed* value fits no structured
mode, and that decision is made once at construction so the strip never changes
under the cursor.
"""

from __future__ import annotations

from core import structure
from core.values import is_grid_cell
from ui_qt.style import FIXED_UNIT_TOOLTIP

from .bodies import ExpressionBody, NumberBody, RawJsonBody, TableBody
from .modal import RAW_MODE, ModalCard, Mode

FLOAT_INT = "FloatInt"
FUNCTION = "Function"
INTERPOLATED_TABLE = "InterpolatedTable"

_RAW_NOTICE = (
    "This value has no structured representation, so it is shown as raw JSON. "
    "Choosing another mode starts an empty editor; nothing changes until you commit."
)


def table_is_representable(value: object) -> bool:
    """Whether *value* renders in, and reads back from, a two-column x/y grid.

    A grid is rectangular, so a ragged ``{"x": [1, 2], "y": [1]}`` has no grid
    form -- padding it would invent a data point. Extra keys have none either:
    a two-column grid cannot carry a third list, and committing would silently
    drop it. Both open in ``Raw`` instead, with the value intact.
    """
    if not isinstance(value, dict):
        return False
    if set(value) != {"x", "y"}:
        return False
    xs, ys = value["x"], value["y"]
    if not isinstance(xs, list) or not isinstance(ys, list) or len(xs) != len(ys):
        return False
    return all(is_grid_cell(item) for item in (*xs, *ys))


def initial_mode(value: object) -> str:
    """The mode a committed *value* opens in.

    ``None`` -- a freshly added parameter -- opens in the union's first declared
    member, an empty numeric editor, exactly as an added scalar does. A ``bool``
    is legal BPX (it validates as ``1``) but no numeric editor can round-trip
    it, so it opens in ``Raw`` rather than being rewritten as ``"True"``.
    """
    if value is None:
        return FLOAT_INT
    if isinstance(value, bool):
        return RAW_MODE
    if isinstance(value, (int, float)):
        return FLOAT_INT
    if isinstance(value, str):
        return FUNCTION
    if table_is_representable(value):
        return INTERPOLATED_TABLE
    return RAW_MODE


class FunctionCard(ModalCard):
    """Edits a ``FloatFunctionTable`` field through its legal representations."""

    def __init__(self, parameter, meta) -> None:
        opens_in = initial_mode(parameter.value)
        renamable = structure.can_rename_parameter(parameter.path, parameter.value)
        unit_tooltip = "" if renamable else FIXED_UNIT_TOOLTIP
        self._table_body = TableBody(parameter.unit)
        self._expression_body = ExpressionBody(parameter.unit)
        modes = [
            Mode(FLOAT_INT, NumberBody(parameter.unit, unit_tooltip)),
            Mode(FUNCTION, self._expression_body),
            Mode(INTERPOLATED_TABLE, self._table_body),
        ]
        if opens_in == RAW_MODE:
            modes.append(Mode(RAW_MODE, RawJsonBody(_RAW_NOTICE)))
        labels = [mode.label for mode in modes]
        super().__init__(parameter, meta, modes, labels.index(opens_in))

    def set_reference_curves(self, curves) -> None:
        """Delegate to the ``InterpolatedTable`` mode's own body, whichever
        mode the strip currently shows -- a hidden body simply has nothing
        visible to draw until the strip switches back to it (see
        ``TableBody.set_reference_curves``)."""
        self._table_body.set_reference_curves(curves)

    def set_reference_functions(self, entries) -> None:
        """Delegate to the ``Function`` mode's own body, whichever mode the
        strip currently shows -- mirrors :meth:`set_reference_curves` (see
        ``ExpressionBody.set_reference_functions``)."""
        self._expression_body.set_reference_functions(entries)
