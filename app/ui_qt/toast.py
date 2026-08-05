"""Toast: a transient, auto-dismissing status message overlaid on a window.

The app has no other toast mechanism today -- this is the one home for it.
Used first by the reference-open flow (M1); any future feature wanting a
quiet "did that work" confirmation reuses this same widget rather than
inventing its own.
"""

from __future__ import annotations

import html
from typing import Callable

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtWidgets import QLabel, QWidget

from . import style, typography

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

        self._message = ""
        self._action_text: str | None = None
        self._action: Callable[[], None] | None = None
        self.linkActivated.connect(self._on_link_activated)

    def show_message(
        self,
        text: str,
        action_text: str | None = None,
        action: Callable[[], None] | None = None,
    ) -> None:
        """Show *text*, replacing any message currently visible, and
        (re)start the auto-dismiss timer.

        With *action_text*/*action* the pill gains one trailing link that
        runs *action* and dismisses. A plain message stays mouse-transparent
        (clicks fall through to the window beneath); only a message carrying
        an action accepts the mouse at all.
        """
        self._message = text
        self._action_text = action_text if action is not None else None
        self._action = action
        if self._action is not None and action_text:
            self.setTextFormat(Qt.RichText)
            self.setTextInteractionFlags(Qt.LinksAccessibleByMouse)
            self.setText(
                f"{html.escape(text)}&nbsp;&nbsp;"
                f'<a href="action" style="color: {style.TOAST_ACTION};'
                f' {typography.semibold_qss()}">{html.escape(action_text)}</a>'
            )
        else:
            self.setTextFormat(Qt.PlainText)
            self.setTextInteractionFlags(Qt.NoTextInteraction)
            self.setText(text)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, self._action is None)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()
        self._timer.start(DISMISS_DELAY_MS)

    def message(self) -> str:
        """The plain message text, without any action-link markup."""
        return self._message

    def action_text(self) -> str | None:
        """The action link's label, or ``None`` for a plain message."""
        return self._action_text

    def _on_link_activated(self, _href: str) -> None:
        action = self._action
        self.hide()
        if action is not None:
            action()

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
