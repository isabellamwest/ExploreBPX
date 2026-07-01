"""Base class for editing cards.

A card edits a *draft* of one parameter value. It never touches the document;
it emits ``draft_changed`` while the user types (for live validation) and
``commit_requested`` when the user presses Enter or activates an inline action.

Keyboard contract (for editable cards):
- Enter / Return  → emit ``commit_requested`` (Inspector commits to document).
- Escape          → restore to original value, emit ``draft_changed`` (Inspector
                    re-validates immediately so the badge reflects the reset state).
- Inline Reset    → same as Escape, triggered by the Reset button in the card.

Cards register input widgets with ``_install_keyboard_handler`` in their
``__init__`` and include the Reset button from ``_build_reset_button`` in their
layout. ``ReadOnlyCard`` does neither.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, Qt, Signal
from PySide6.QtWidgets import QPushButton, QWidget

from core.bpx_gateway import FieldMeta
from core.tree_model import ParameterItem


class EditorCard(QWidget):
    """Abstract value editor for a single :class:`ParameterItem`."""

    draft_changed = Signal()
    commit_requested = Signal()

    def __init__(self, parameter: ParameterItem, meta: FieldMeta | None) -> None:
        super().__init__()
        self.parameter = parameter
        self.meta = meta
        self._original = parameter.value

    def value(self) -> object:
        """Return the current draft value in raw-dict form."""
        raise NotImplementedError

    def reset(self) -> None:
        """Restore the editor to the original (last committed) value."""
        raise NotImplementedError

    @property
    def is_editable(self) -> bool:
        return True

    # ------------------------------------------------------------------
    # Keyboard handling helpers
    # ------------------------------------------------------------------

    def _install_keyboard_handler(self, widget: QWidget) -> None:
        """Watch *widget* for Enter (commit) and Escape (revert) key presses."""
        widget.installEventFilter(self)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # noqa: N802
        if event.type() == QEvent.KeyPress:
            # For combo boxes: pass Enter/Escape through when the popup is open
            # so that dropdown selection and dismissal work normally.
            try:
                from PySide6.QtWidgets import QComboBox  # local import avoids circularity
                if isinstance(obj, QComboBox) and obj.view().isVisible():
                    return super().eventFilter(obj, event)
            except Exception:
                pass

            key = event.key()
            if key in (Qt.Key_Return, Qt.Key_Enter):
                self.commit_requested.emit()
                return True
            if key == Qt.Key_Escape:
                self.reset()
                self.draft_changed.emit()
                return True
        return super().eventFilter(obj, event)

    def _build_reset_button(self) -> QPushButton:
        """Return a small Reset button that restores the last committed value."""
        btn = QPushButton("Reset")
        btn.setObjectName("InlineReset")
        btn.setFocusPolicy(Qt.NoFocus)
        btn.clicked.connect(self._on_inline_reset)
        return btn

    def _on_inline_reset(self) -> None:
        self.reset()
        self.draft_changed.emit()

