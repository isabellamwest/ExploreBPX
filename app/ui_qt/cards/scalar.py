"""Scalar (number) editing card: a number input with the parameter's unit."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from core import structure

from ..style import FIXED_UNIT_TOOLTIP
from .base import EditorCard
from .values import format_value, parse_value


class ScalarCard(EditorCard):
    """Edits a float/bool scalar via a free-text number field plus unit label."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(format_value(self._original))
        self._edit.textChanged.connect(lambda *_: self.draft_changed.emit())
        layout.addWidget(self._edit, 1)
        #: The unit label, or ``None`` when the parameter has no unit --
        #: kept as an attribute (not just laid out) so tests can read its
        #: tooltip directly.
        self._unit_label: QLabel | None = None
        if parameter.unit:
            self._unit_label = QLabel(parameter.unit)
            if not structure.can_rename_parameter(parameter.path, parameter.value):
                self._unit_label.setToolTip(FIXED_UNIT_TOOLTIP)
            layout.addWidget(self._unit_label)
        self._install_keyboard_handler(self._edit)

    def value(self) -> object:
        return parse_value(self._edit.text())

    def reset(self) -> None:
        self._edit.setText(format_value(self._original))
