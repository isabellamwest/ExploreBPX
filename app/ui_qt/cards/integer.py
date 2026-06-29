"""Integer editing card: an integer-constrained stepper."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QSpinBox

from .base import EditorCard


class IntegerCard(EditorCard):
    """Edits an integer value with a stepper."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._spin = QSpinBox()
        self._spin.setRange(-1_000_000, 1_000_000)
        try:
            self._spin.setValue(int(self._original))
        except (TypeError, ValueError):
            self._spin.setValue(0)
        self._spin.valueChanged.connect(self.draft_changed.emit)
        layout.addWidget(self._spin, 1)
        if parameter.unit:
            layout.addWidget(QLabel(parameter.unit))

    def value(self) -> object:
        return self._spin.value()

    def reset(self) -> None:
        try:
            self._spin.setValue(int(self._original))
        except (TypeError, ValueError):
            self._spin.setValue(0)
