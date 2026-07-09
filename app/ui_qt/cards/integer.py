"""Integer editing card: an integer-constrained stepper.

When the currently committed document value is a valid integer the card uses a
``QSpinBox`` (the normal path).  When the committed value cannot be interpreted
as an integer — because an invalid value was previously saved — the card falls
back to a plain ``QLineEdit`` so the raw value remains visible and editable.
This ensures the card is never read-only purely because the document contains
an invalid value.
"""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QSpinBox

from .base import EditorCard


class IntegerCard(EditorCard):
    """Edits an integer value with a stepper, falling back to free text for invalid originals."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        try:
            initial = int(self._original)
            valid_original = True
        except (TypeError, ValueError):
            valid_original = False

        if valid_original:
            self._spin: QSpinBox | None = QSpinBox()
            self._spin.setRange(-1_000_000, 1_000_000)
            self._spin.setValue(initial)
            self._spin.valueChanged.connect(lambda *_: self.draft_changed.emit())
            layout.addWidget(self._spin, 1)
            self._fallback: QLineEdit | None = None
            input_widget = self._spin
        else:
            self._spin = None
            self._fallback = QLineEdit(str(self._original) if self._original is not None else "")
            self._fallback.textChanged.connect(lambda *_: self.draft_changed.emit())
            layout.addWidget(self._fallback, 1)
            input_widget = self._fallback

        if parameter.unit:
            layout.addWidget(QLabel(parameter.unit))
        self._install_keyboard_handler(input_widget)

    def value(self) -> object:
        if self._spin is not None:
            return self._spin.value()
        text = self._fallback.text().strip()
        if not text:
            return None  # honest "no value", matching what AddParameter writes
        try:
            return int(text)
        except ValueError:
            return text  # let the backend report the type error

    def reset(self) -> None:
        if self._spin is not None:
            try:
                self._spin.setValue(int(self._original))
            except (TypeError, ValueError):
                self._spin.setValue(0)
        else:
            self._fallback.setText(str(self._original) if self._original is not None else "")
