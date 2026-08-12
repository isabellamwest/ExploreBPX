"""One-line labels that elide instead of clipping, tooltip carrying the rest.

Grew up privately inside ``workspace_panel``; promoted here once other panes
(source page headers, dialog legends) needed the same guarantee -- a squeezed
label must shorten itself visibly, never run out of its box.
"""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFontMetrics
from PySide6.QtWidgets import QLabel


class ElidedLabel(QLabel):
    """A one-line label that elides on the right and keeps the whole text in
    its tooltip. The sibling of :class:`PathLabel`, which elides the other
    way because a path's end is the part that identifies it."""

    def __init__(self, object_name: str | None = None) -> None:
        super().__init__()
        if object_name is not None:
            self.setObjectName(object_name)
        self._full_text = ""
        self.setMinimumWidth(0)

    def sizeHint(self) -> QSize:  # noqa: N802 - Qt naming
        # Prefer the *full* text's width, not the currently-elided text's:
        # a zero-stretch label whose hint tracked its shown text would ratchet
        # down (layout grants the hint, resize re-elides to it) and never
        # recover the room a wider row actually has.
        hint = super().sizeHint()
        metrics = QFontMetrics(self.font())
        return QSize(metrics.horizontalAdvance(self._full_text) + 2, hint.height())

    def setText(self, text: str) -> None:  # noqa: N802 - Qt naming
        self._full_text = text
        self.setToolTip(text)
        self._apply_elision()

    def full_text(self) -> str:
        return self._full_text

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        super().setText(
            metrics.elidedText(self._full_text, Qt.ElideRight, max(self.width(), 1))
        )


class PathLabel(QLabel):
    """A file path elided from the *left*, keeping the file name visible.

    Word wrap cannot help here: a Windows path has no spaces to break at, so
    a long one simply ran off the row and lost exactly the end that
    identifies it. Elides head-first (the sibling of ``main_window``'s
    ``_IdentityLabel``, which elides the other way for a title), with the
    full path always one hover away.
    """

    def __init__(self, path: str, object_name: str = "WorkspaceCardValue") -> None:
        super().__init__()
        self.setObjectName(object_name)
        self._full_text = path
        self.setToolTip(path)
        self.setMinimumWidth(0)
        self._apply_elision()

    def set_path(self, path: str) -> None:
        self._full_text = path
        self.setToolTip(path)
        self._apply_elision()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        super().resizeEvent(event)
        self._apply_elision()

    def _apply_elision(self) -> None:
        metrics = QFontMetrics(self.font())
        self.setText(metrics.elidedText(self._full_text, Qt.ElideLeft, max(self.width(), 1)))
