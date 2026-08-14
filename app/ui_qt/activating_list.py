"""A ``QListWidget`` where Return activates the current row on every platform.

Qt's own Return-to-activate is not portable. ``QAbstractItemView`` takes its
activation key from the platform's key binding scheme, and macOS's reserves
Return for rename (Finder semantics), mapping activation to Cmd+O instead --
measured on Qt 6.11, where ``keyClick(list, Qt.Key_Return)`` emits no
``activated`` at all. Both issue lists document Enter/Return as the way to jump
to a row, so on macOS they were quietly breaking their own contract: the
keyboard route to a diagnostic simply did nothing.

So the **bare** Return is handled here and never passed to the base class,
which takes the platform's scheme out of the sum for the one chord users
actually press. Emitting ``itemActivated`` rather than a new signal keeps every
existing connection untouched, and double-click continues to arrive through
Qt's own path.

A *modified* Return is deliberately still handed to the base class, so what it
does remains Qt's own and stays platform-dependent (Windows activates on
Shift+Return; macOS does not). Claiming otherwise would mean swallowing chords
a future feature may want, to standardise something nobody presses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidget

if TYPE_CHECKING:
    from PySide6.QtGui import QKeyEvent

#: Return and the keypad's Enter. The keypad sets ``KeypadModifier``, so it is
#: masked out before asking whether the chord was bare -- a modified Return
#: (Shift, Cmd, Ctrl) still belongs to the base class.
_ACTIVATE_KEYS = (Qt.Key_Return, Qt.Key_Enter)


class ActivatingList(QListWidget):
    """See module docstring."""

    def keyPressEvent(self, event: QKeyEvent) -> None:
        bare = not (event.modifiers() & ~Qt.KeypadModifier)
        if event.key() in _ACTIVATE_KEYS and bare:
            item = self.currentItem()
            if item is not None:
                self.itemActivated.emit(item)
            event.accept()
            return
        super().keyPressEvent(event)
