"""Toast: a transient, auto-dismissing status message overlaid on a window.

The app has no other toast mechanism today -- this is the one home for it.
Used first by the reference-open flow (M1); any future feature wanting a
quiet "did that work" confirmation reuses this same widget rather than
inventing its own.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

from . import style

#: How long a message stays visible before auto-dismissing.
DISMISS_DELAY_MS = 4000

#: Gap between the pill's bottom edge and the window's bottom edge.
_BOTTOM_MARGIN = 24


class Toast(QLabel):
    """A pill-shaped message overlaid bottom-centre of *parent*.

    One message at a time: calling :meth:`show_message` again replaces
    whatever is currently visible and restarts the auto-dismiss timer. Never
    takes keyboard or mouse focus, and repositions itself whenever *parent*
    resizes (via an event filter installed on it).
    """

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setObjectName("Toast")
        self.setAlignment(Qt.AlignCenter)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setFocusPolicy(Qt.NoFocus)
        self.setStyleSheet(style.toast_qss())
        self.hide()
        parent.installEventFilter(self)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.hide)

    def show_message(self, text: str) -> None:
        """Show *text*, replacing any message currently visible, and
        (re)start the auto-dismiss timer."""
        self.setText(text)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(DISMISS_DELAY_MS)

    def eventFilter(self, watched, event) -> bool:  # noqa: N802 - Qt override
        if watched is self.parentWidget() and event.type() == QEvent.Resize:
            self._reposition()
        return super().eventFilter(watched, event)

    def _reposition(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        x = (parent.width() - self.width()) // 2
        y = parent.height() - self.height() - _BOTTOM_MARGIN
        self.move(max(x, 0), max(y, 0))
