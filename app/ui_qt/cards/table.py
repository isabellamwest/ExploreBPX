"""Table card: an interpolated x/y table with no mode strip.

``ParameterKind.TABLE`` is reached only for a metadata-less value whose shape is
an ``x``/``y`` interpolated table -- i.e. a User-defined parameter, since every
*declared* table field is a ``FloatFunctionTable`` and classifies as ``FUNCTION``
(see :mod:`core.parameter_types`). It has one legal representation, so the card
shows the grid and its live preview and no strip.

Reuses :class:`~.bodies.TableBody` -- the same editor the ``InterpolatedTable``
mode of :class:`~.function.FunctionCard` uses -- so a User-defined table looks
and behaves identically to a declared one, chart and all. A value the grid
cannot represent (a ragged table) is handed to :class:`~.modal.RawValueCard` by
the registry instead.
"""

from __future__ import annotations

from .bodies import TableBody
from .modal import Mode, ModalCard

INTERPOLATED_TABLE = "InterpolatedTable"


class TableCard(ModalCard):
    """Edits an ``x``/``y`` table as a grid over a live preview, with no strip."""

    def __init__(self, parameter, meta) -> None:
        self._table_body = TableBody()
        super().__init__(parameter, meta, [Mode(INTERPOLATED_TABLE, self._table_body)], 0)

    def set_reference_table(self, rows: list[list[object]] | None) -> None:
        self._table_body.set_reference_rows(rows)
