"""Small header bar naming the currently active top-level page.

Sits above the workspace stack, spanning only the content column (not the
activity bar), so the content area always identifies which of Workspace /
Editor / Validation is showing -- the activity bar's buttons became
icon-only, so this is now the only place that names the page in text.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget


class PageHeader(QWidget):
    """34px bar showing the active page's name, upper-cased."""

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("PageHeader")
        # A plain QWidget subclass ignores stylesheet background/border
        # unless told to paint them; without this, PageHeader's declared
        # chrome (see style.py) is silently never drawn.
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(34)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)

        self._title = QLabel()
        self._title.setObjectName("PageHeaderTitle")
        font = self._title.font()
        font.setLetterSpacing(QFont.PercentageSpacing, 108)
        self._title.setFont(font)
        layout.addWidget(self._title)
        layout.addStretch(1)

        self._raw_title = ""

    def set_title(self, text: str) -> None:
        """Set the page name shown, displayed upper-cased."""
        self._raw_title = text
        self._title.setText(text.upper())

    def title(self) -> str:
        """The raw (non-upper-cased) title, for tests."""
        return self._raw_title
