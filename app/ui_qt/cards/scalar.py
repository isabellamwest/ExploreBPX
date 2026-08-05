"""Scalar (number) editing card: a number input with the parameter's unit."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit

from core import structure
from core.values import format_value, parse_value

from ..style import FIXED_UNIT_TOOLTIP, VALUE_INPUT_MAX_WIDTH
from .base import EditorCard


class ScalarCard(EditorCard):
    """Edits a float/bool scalar via a free-text number field plus unit label."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._edit = QLineEdit(format_value(self._original))
        self._edit.setMaximumWidth(VALUE_INPUT_MAX_WIDTH)
        self._edit.textChanged.connect(lambda *_: self.draft_changed.emit())
        layout.addWidget(self._edit, 1)
        #: The unit label, or ``None`` when the parameter has no unit --
        #: kept as an attribute (not just laid out) so tests can read its
        #: tooltip directly.
        self._unit_label: QLabel | None = None
        if parameter.unit:
            self._unit_label = QLabel(parameter.unit)
            self._unit_label.setObjectName("UnitLabel")
            if not structure.can_rename_parameter(parameter.path, parameter.value):
                self._unit_label.setToolTip(FIXED_UNIT_TOOLTIP)
            layout.addWidget(self._unit_label)
        # Zero-stretch: the input grows to its full cap before the spacer
        # takes anything, so its width is deterministic and the reference
        # row's read-only box (same cap) aligns with it exactly.
        layout.addStretch(0)
        self._install_keyboard_handler(self._edit)

    def reference_value_width(self) -> int | None:
        return VALUE_INPUT_MAX_WIDTH

    def value(self) -> object:
        return parse_value(self._edit.text())

    def reset(self) -> None:
        self._edit.setText(format_value(self._original))
