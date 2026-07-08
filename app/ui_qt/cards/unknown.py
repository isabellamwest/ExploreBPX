"""Read-only fallback card for kinds without an editor (section/table).

Structural kinds display their value read-only so the inspector still works
for the whole tree. ``SECTION`` is a container, not a value to edit here, and
``TABLE`` editing is separate roadmap work; both fall back to this card.
"""

from __future__ import annotations

import json

from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout

from .base import EditorCard


class ReadOnlyCard(EditorCard):
    """Displays a value read-only; not yet editable."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        view = QPlainTextEdit(self._format(parameter.value))
        view.setReadOnly(True)
        layout.addWidget(view)

    @staticmethod
    def _format(value: object) -> str:
        try:
            return json.dumps(value, indent=2, ensure_ascii=False)
        except TypeError:
            return str(value)

    def value(self) -> object:
        return self._original

    def reset(self) -> None:
        pass

    @property
    def is_editable(self) -> bool:
        return False
