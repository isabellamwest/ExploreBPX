"""Enum editing card: a dropdown constrained to the schema's enum values."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout

from .base import EditorCard


class EnumCard(EditorCard):
    """Edits an enum value via a dropdown of the schema's allowed values."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._combo = QComboBox()
        values = list(meta.enum_values) if meta else []
        if self._original not in values and self._original is not None:
            values.append(str(self._original))
        self._combo.addItems([str(v) for v in values])
        self._select(self._original)
        self._combo.currentTextChanged.connect(lambda *_: self.draft_changed.emit())
        layout.addWidget(self._combo, 1)
        self._install_keyboard_handler(self._combo)

    def _select(self, value: object) -> None:
        index = self._combo.findText(str(value))
        if index >= 0:
            self._combo.setCurrentIndex(index)

    def value(self) -> object:
        return self._combo.currentText()

    def reset(self) -> None:
        self._select(self._original)
