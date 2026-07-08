"""Activity bar: narrow left-edge rail that switches the main content area.

Each entry is a checkable QToolButton inside an exclusive QButtonGroup.
The bar emits ``view_requested`` with the QStackedWidget page index when the
active view changes.  Adding a future workspace requires one addWidget call on
the stack and one call to ``add_view`` here.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QSizePolicy, QToolButton, QVBoxLayout, QWidget


class ActivityBar(QWidget):
    """Narrow vertical bar that owns workspace switching."""

    view_requested = Signal(int)  # QStackedWidget page index

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ActivityBar")
        self.setFixedWidth(72)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 8, 4, 8)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[QToolButton] = []
        self._buttons_by_page: dict[int, QToolButton] = {}

    def add_view(self, label: str, page_index: int, *, checked: bool = False) -> QToolButton:
        """Register a view entry and return its button for later label updates."""
        btn = QToolButton()
        btn.setText(label)
        btn.setCheckable(True)
        btn.setChecked(checked)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setObjectName("ActivityButton")
        btn.clicked.connect(lambda _checked, i=page_index: self.view_requested.emit(i))
        # Insert before the bottom stretch item.
        insert_pos = self._layout.count() - 1
        self._layout.insertWidget(insert_pos, btn)
        self._group.addButton(btn)
        self._buttons.append(btn)
        self._buttons_by_page[page_index] = btn
        return btn

    def select(self, page_index: int) -> None:
        """Mark the entry for *page_index* as the checked/active one.

        For programmatic navigation that must make a view current without
        the user having clicked its button. Does not emit ``view_requested``
        -- the caller already knows the target page and is only asking the
        rail's visual state to follow.
        """
        btn = self._buttons_by_page.get(page_index)
        if btn is not None:
            btn.setChecked(True)
