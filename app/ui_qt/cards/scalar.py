"""Scalar (number) editing card: a number input with the parameter's unit."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from .base import EditorCard


class ScalarCard(EditorCard):
    """Edits a float/bool scalar via a free-text number field plus unit label."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(self._format(self._original))
        self._edit.textChanged.connect(self.draft_changed.emit)
        layout.addWidget(self._edit, 1)
        if parameter.unit:
            layout.addWidget(QLabel(parameter.unit))

    @staticmethod
    def _format(value: object) -> str:
        return "" if value is None else str(value)

    def value(self) -> object:
        text = self._edit.text().strip()
        try:
            number = float(text)
        except ValueError:
            return text  # let the backend report a type error
        return int(number) if number.is_integer() and "." not in text else number

    def reset(self) -> None:
        self._edit.setText(self._format(self._original))
