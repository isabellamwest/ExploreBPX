"""Activity bar: narrow left-edge rail that switches the main content area.

Each entry is a checkable :class:`ActivityButton` inside an exclusive
QButtonGroup. The bar emits ``view_requested`` with the QStackedWidget page
index when the active view changes. Adding a future workspace requires one
addWidget call on the stack and one call to ``add_view`` here.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QIcon, QPainter
from PySide6.QtWidgets import QButtonGroup, QSizePolicy, QToolButton, QVBoxLayout, QWidget

from explore_bpx.ui_qt import badges


class ActivityButton(QToolButton):
    """Icon-only activity-bar entry with an optional severity count badge.

    The label is never drawn as text -- it is the tooltip and accessible
    name, which is how the user learns the button's identity. A count badge
    (currently only used by Diagnostics) is painted directly in
    ``paintEvent`` rather than via QSS, since it needs per-instance state
    (count, severity) a stylesheet cannot express.
    """

    def __init__(self, label: str) -> None:
        super().__init__()
        self.setObjectName("ActivityButton")
        self.setText("")
        self.setToolButtonStyle(Qt.ToolButtonIconOnly)
        self.setIconSize(QSize(20, 20))
        self.setFixedHeight(44)
        self.setCheckable(True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setToolTip(label)
        self.setAccessibleName(label)

        self.badge_count = 0
        self.badge_severity: str | None = None

    def set_badge(self, count: int, severity: str | None) -> None:
        """Show a count badge at the icon's bottom-right corner.

        A non-positive *count* clears the badge (and its severity) entirely,
        regardless of what *severity* was passed.
        """
        self.badge_count = count if count > 0 else 0
        self.badge_severity = severity if self.badge_count else None
        self.update()

    def badge_text(self) -> str:
        """The digits painted inside the badge pill, capped at "99+"."""
        if self.badge_count <= 0:
            return ""
        return "99+" if self.badge_count > 99 else str(self.badge_count)

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        if not self.badge_count:
            return

        text = self.badge_text()
        width = badges.badge_width(text)
        height = badges.HEIGHT

        # Anchor to the icon's own rect, not the (much wider) button rect,
        # so the badge reads as attached to the glyph rather than floating
        # in empty rail space to its right.
        icon_rect = QRect(QPoint(0, 0), self.iconSize())
        icon_rect.moveCenter(self.rect().center())

        badge_rect = QRect(0, 0, width, height)
        badge_rect.moveBottomRight(QPoint(icon_rect.right() + 3, icon_rect.bottom() + 3))
        inset = self.rect().adjusted(1, 1, -1, -1)
        if badge_rect.right() > inset.right():
            badge_rect.moveRight(inset.right())
        if badge_rect.bottom() > inset.bottom():
            badge_rect.moveBottom(inset.bottom())
        if badge_rect.left() < inset.left():
            badge_rect.moveLeft(inset.left())
        if badge_rect.top() < inset.top():
            badge_rect.moveTop(inset.top())

        bg, fg = badges.badge_colors(self.badge_severity, solid=True)
        painter = QPainter(self)
        badges.paint_badge(painter, badge_rect, text, bg, fg)
        painter.end()


class ActivityBar(QWidget):
    """Narrow vertical bar that owns workspace switching."""

    view_requested = Signal(int)  # QStackedWidget page index

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("ActivityBar")
        # A plain QWidget subclass ignores stylesheet background/border
        # unless told to paint them; without this, ActivityBar's declared
        # chrome (see style.py) is silently never drawn.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(48)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(4, 8, 4, 8)
        self._layout.setSpacing(4)
        self._layout.addStretch(1)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: list[ActivityButton] = []
        self._buttons_by_page: dict[int, ActivityButton] = {}
        self._labels_by_page: dict[int, str] = {}

    def add_view(self, label: str, page_index: int, icon: QIcon, *, checked: bool = False) -> ActivityButton:
        """Register a view entry and return its button for later updates."""
        btn = ActivityButton(label)
        btn.setIcon(icon)
        btn.setChecked(checked)
        btn.clicked.connect(lambda _checked, i=page_index: self.view_requested.emit(i))
        # Insert before the bottom stretch item.
        insert_pos = self._layout.count() - 1
        self._layout.insertWidget(insert_pos, btn)
        self._group.addButton(btn)
        self._buttons.append(btn)
        self._buttons_by_page[page_index] = btn
        self._labels_by_page[page_index] = label
        return btn

    def label_for(self, page_index: int) -> str:
        """The label registered for *page_index* via ``add_view``.

        The single source of page names -- callers (e.g. the page header)
        read titles from here rather than keeping a second, hardcoded map.
        """
        return self._labels_by_page.get(page_index, "")

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
