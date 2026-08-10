"""A ``QListWidget`` that hugs its own content height.

Extracted from the Diagnostics page's group boxes once the Inspector's
Issues section needed the identical behaviour: the list reports its natural
content height (the sum of its own rows' delegate ``sizeHint``s) as its
``sizeHint`` instead of the generic scroll-area default, and carries
``QSizePolicy.Minimum`` vertically -- so it hugs exactly its own rows in a
``QVBoxLayout`` rather than stretching to fill whatever space a sibling
stretch factor would otherwise hand it (a one-row Issues box must not
become a ~300px empty card). Any overflow scrolls in the *outer* pane, so
callers turn the list's own scrollbars off.

``updateGeometry()`` must be called after any change that can alter row
count/height -- every caller does, right after populating.
"""

from __future__ import annotations

from PySide6.QtCore import QSize

from .activating_list import ActivatingList


class ContentSizedList(ActivatingList):
    """See module docstring. Return activates, per :class:`ActivatingList`."""

    def sizeHint(self) -> QSize:  # noqa: N802 (Qt override)
        width = super().sizeHint().width()
        height = 2 * self.frameWidth() + sum(
            self.sizeHintForRow(row) for row in range(self.count())
        )
        return QSize(width, height)
