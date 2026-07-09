"""Function-expression editing card.

BPX parameters declared with ``allows_function`` can hold either a constant
numeric value or a function-expression string.  Classification no longer
switches editor by stored-value shape (see ``core.parameter_types``), so this
card is now the FUNCTION kind's card for every legal representation except a
table-valued (dict) one -- see the interim dispatch in ``cards/registry.py``
-- including a plain numeric constant, which previously routed to
``ScalarCard``.

Keyboard contract (inherited from :class:`~.base.EditorCard`):
- Enter / Return  → emit ``commit_requested``.
- Escape          → restore to original value, emit ``draft_reset``.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from .base import EditorCard


class FunctionCard(EditorCard):
    """Edits a function-expression value via a free-text field.

    ``value()`` mirrors :class:`~.scalar.ScalarCard`: if the committed text
    parses as a plain number the result is a ``float`` (or ``int``), allowing
    a seamless transition back to the scalar editor on the next document
    rebuild.  Otherwise the raw string is returned and validation reports any
    type error.
    """

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(self._format(self._original))
        self._edit.textChanged.connect(lambda *_: self.draft_changed.emit())
        layout.addWidget(self._edit, 1)
        if parameter.unit:
            layout.addWidget(QLabel(parameter.unit))
        self._install_keyboard_handler(self._edit)

    @staticmethod
    def _format(value: object) -> str:
        return "" if value is None else str(value)

    def value(self) -> object:
        text = self._edit.text().strip()
        if not text:
            return None  # honest "no value", matching what AddParameter writes
        try:
            number = float(text)
        except ValueError:
            return text  # expression string or invalid text — let validation decide
        return int(number) if number.is_integer() and "." not in text else number

    def reset(self) -> None:
        self._edit.setText(self._format(self._original))
