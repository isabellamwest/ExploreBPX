"""Series editing card: a one-column grid over a BPX ``list[FloatInt]``.

``SERIES`` is the kind of the four Validation experiment arrays (``Time [s]``,
``Current [A]``, ``Voltage [V]``, ``Temperature [K]``). It has exactly one legal
representation, so the card shows a grid and no mode strip.

The column header is the parameter's label, which already carries the unit
(``Time [s]``), so the grid needs no separate unit affordance.
"""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout

from .base import EditorCard
from .grid import NumericGrid


class SeriesCard(EditorCard):
    """Edits a list of numbers as a single grid column."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._grid = NumericGrid((parameter.label,))
        # Populate before wiring ``changed``: seeding must not mark the card
        # touched, or construction alone would make a bare Enter commit.
        self._grid.set_values(self._rows(self._original))
        self._grid.changed.connect(lambda: self.draft_changed.emit())
        layout.addWidget(self._grid)

        self._install_keyboard_handler(self._grid.focus_widget())

    @staticmethod
    def _rows(value: object) -> list[list[object]]:
        """One grid row per list item. A ``None`` value is an empty grid.

        A freshly added parameter holds ``None``, the honest "no value". It
        renders as an empty grid, and because an untouched card is never dirty,
        Enter on it commits nothing -- the stored ``null`` survives.
        """
        if value is None:
            return []
        return [[item] for item in value]

    def value(self) -> object:
        """The column's cells verbatim. An empty grid is ``[]``, not ``None``.

        Cells are whatever the user typed: a number, or the raw string of a
        mistyped one, or ``None`` for a blank row. Nothing is coerced -- the
        validator reports the type error.
        """
        return [row[0] for row in self._grid.values()]

    def reset(self) -> None:
        self._grid.set_values(self._rows(self._original))
