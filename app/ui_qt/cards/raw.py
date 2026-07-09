"""Raw fallback editing card for parameters with no known BPX kind.

``ParameterKind.UNKNOWN`` is reached only for a value-less, metadata-less
parameter (e.g. a freshly-added custom parameter before the user has typed a
value; see ``core.parameter_types.classify``). This card lets that value be
authored via free text rather than trapping the user in a read-only view.

``value()`` mirrors :class:`~.scalar.ScalarCard` and :class:`~.function.FunctionCard`:
text that parses as a plain number becomes an ``int``/``float``; anything else
is passed through as a raw string. This is the app's existing lenient
raw-value convention -- the card never decides validity, it hands the typed
text to the same commit path every other card uses, and the BPX validator
remains the source of truth for whether the result is legal. Reusing this
convention also means that once a value is committed, the next classification
of the parameter picks up the normal SCALAR/FUNCTION editor for it.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLineEdit

from .base import EditorCard


class RawCard(EditorCard):
    """Edits an ``UNKNOWN``-kind value via free text."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(self._format(self._original))
        self._edit.textChanged.connect(lambda *_: self.draft_changed.emit())
        layout.addWidget(self._edit, 1)
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
            return text  # let the backend/validator report a type error
        return int(number) if number.is_integer() and "." not in text else number

    def reset(self) -> None:
        self._edit.setText(self._format(self._original))
