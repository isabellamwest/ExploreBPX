"""Enum editing card: a dropdown constrained to the schema's enum values.

Commit model. Picking a value **from the opened dropdown** commits it
immediately: opening the menu and choosing an entry is a complete, deliberate
act (this is how the document's ``Model`` is switched, and requiring a further
Enter made that change look like it silently didn't take). Arrowing through
values on the *closed* combo stays a draft under the app-wide contract --
Enter commits, Escape reverts -- because a step-through is browsing, not
choosing. ``QComboBox.activated`` alone cannot make that distinction (it fires
for closed-combo arrow steps too, which would commit every step), so the combo
tracks whether its popup was open when the activation happened.
"""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QHBoxLayout

from explore_bpx.ui_qt.style import VALUE_INPUT_MAX_WIDTH

from .base import EditorCard


class _EnumCombo(QComboBox):
    """A combo box that knows whether an activation came from its popup."""

    def __init__(self) -> None:
        super().__init__()
        self.popup_was_open = False

    def showPopup(self) -> None:
        self.popup_was_open = True
        super().showPopup()


class EnumCard(EditorCard):
    """Edits an enum value via a dropdown of the schema's allowed values."""

    def __init__(self, parameter, meta) -> None:
        super().__init__(parameter, meta)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._combo = _EnumCombo()
        values = list(meta.enum_values) if meta else []
        if self._original not in values and self._original is not None:
            values.append(str(self._original))
        self._combo.addItems([str(v) for v in values])
        self._select(self._original)
        self._combo.setMaximumWidth(VALUE_INPUT_MAX_WIDTH)
        self._combo.currentTextChanged.connect(lambda *_: self.draft_changed.emit())
        # A capped combo elides its own current item with no way to read the
        # rest; the tooltip carries it verbatim.
        self._combo.currentTextChanged.connect(self._combo.setToolTip)
        self._combo.setToolTip(self._combo.currentText())
        self._combo.activated.connect(self._on_activated)
        layout.addWidget(self._combo, 1)
        # Zero-stretch: see ScalarCard -- deterministic input width, so the
        # reference row's box can match it exactly.
        layout.addStretch(0)
        self._install_keyboard_handler(self._combo)

    def reference_value_width(self) -> int | None:
        return VALUE_INPUT_MAX_WIDTH

    def _on_activated(self, _index: int) -> None:
        """A pick from the opened popup commits; a closed-combo step does not.

        ``currentTextChanged`` (the draft) always fires before ``activated``,
        so the commit sees the new value. Re-picking the current value is
        handled by the Inspector's no-op guard (an untouched/equal draft
        commits nothing).
        """
        if self._combo.popup_was_open:
            self._combo.popup_was_open = False
            self.commit_requested.emit()

    def _select(self, value: object) -> None:
        if value is None:
            self._combo.setCurrentIndex(-1)
            return
        index = self._combo.findText(str(value))
        self._combo.setCurrentIndex(index)

    def value(self) -> object:
        # currentIndex() < 0 is a genuine no-selection state, not "the empty
        # string"; currentText() returns "" there regardless, so it must be
        # checked explicitly rather than trusted.
        if self._combo.currentIndex() < 0:
            return None
        return self._combo.currentText()

    def reset(self) -> None:
        self._select(self._original)
