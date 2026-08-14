"""A small collapsible "How this works" help block for the grid editors.

The table/series grid is powerful -- type-to-edit, paste, add/remove rows,
expand-to-import -- but none of that is obvious from looking at it. This widget
puts a quiet, collapsed-by-default disclosure under the grid: a modeller who
already knows the moves never sees the text, and one who doesn't can open it in
place without a dialog or a trip to the docs.

It is content-only: each card passes the bullet lines relevant to *its* grid
(a Validation series mentions CSV import and sibling columns; an x/y table
mentions points), so nothing here claims a capability a given grid lacks.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QToolButton, QVBoxLayout, QWidget

from ui_qt.style import MUTED


class WrappedHelp(QLabel):
    """Muted help text that is never given less height than it needs.

    A wrapping ``QLabel`` reports its height as a function of its width, and
    that dependency does not survive every layout it can end up inside -- the
    mode strip's ``QStackedLayout`` in particular, where the Function
    editor's syntax hint was handed one line's height and painted its second
    line half-cut. Pinning the minimum to the wrapped height at the width it
    actually got makes the layout honour it.

    Converges: height never feeds back into width here, so one resize
    settles it.
    """

    def __init__(self, text: str = "", parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self.setWordWrap(True)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self.setMinimumHeight(self.heightForWidth(self.width()))


class GridHint(QWidget):
    """A disclosure toggle over a muted bullet list, collapsed by default."""

    def __init__(self, bullets: tuple[str, ...], parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._toggle = QToolButton()
        self._toggle.setObjectName("GridHintToggle")
        self._toggle.setAutoRaise(True)
        self._toggle.setCheckable(True)
        self._toggle.setCursor(Qt.PointingHandCursor)
        self._toggle.setStyleSheet(f"QToolButton {{ border: none; color: {MUTED}; }}")
        self._toggle.toggled.connect(self._on_toggled)
        layout.addWidget(self._toggle, 0, Qt.AlignLeft)

        self._body = WrappedHelp("\n".join(f"•  {line}" for line in bullets))
        self._body.setObjectName("GridHintBody")
        self._body.setStyleSheet(f"color: {MUTED}; padding: 2px 0 2px 14px;")
        self._body.hide()
        layout.addWidget(self._body)

        self._on_toggled(False)

    def _on_toggled(self, shown: bool) -> None:
        # A leading disclosure triangle beside the words -- a named action, not
        # a bare glyph (the app's convention).
        self._toggle.setText(("▾  " if shown else "▸  ") + "How this works")
        self._body.setVisible(shown)
