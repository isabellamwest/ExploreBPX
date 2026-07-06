"""Inspector secondary workspace: a collapsible, tabbed panel at the bottom of
the Inspector for parameter-centric tools (Issues today; Analysis, Documentation
and References in future).

This widget is a **generic container**.  It knows nothing about issues, BPX, or
any specific tool — callers register tabs with :meth:`add_tab` and drive their
content directly.

State model.  The workspace is **workspace state, not parameter state**:

  - It starts collapsed and only the tab strip is visible.
  - The tab strip is always visible so the tools stay discoverable.
  - Expanded/collapsed and active-tab state persist across parameter changes;
    selecting a different parameter never opens or closes the workspace.
  - Only the user collapses it, by clicking the active tab again.

Panel height is owned by the surrounding splitter (see ``InspectorPanel``); this
widget only reports :meth:`tab_strip_height` and locks its own maximum height
while collapsed so the splitter cannot reveal empty space.

Future direction — ParameterTool protocol
------------------------------------------
When a second concrete tool exists (Analysis, Documentation, etc.), consider
evolving toward a ``ParameterTool`` protocol so tools register generically::

    class ParameterTool:
        id: str
        title: str
        def supports(self, parameter) -> bool: ...
        def update(self, parameter) -> None: ...

``SecondaryWorkspace`` would then route ``show_parameter`` calls to all
registered tools and only surface the tab when ``supports()`` returns True.
Do not build this abstraction before at least one further concrete tool is ready.
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QSizePolicy,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

# Qt's sentinel for "no maximum" (QWIDGETSIZE_MAX); PySide6 does not export it.
_MAX_HEIGHT = 16777215


class SecondaryWorkspace(QWidget):
    """A tab strip over a collapsible content stack."""

    expanded_changed = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("SecondaryWorkspace")

        self._expanded = False
        self._active_id: str | None = None
        self._titles: dict[str, str] = {}
        self._buttons: dict[str, QToolButton] = {}
        self._pages: dict[str, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Tab strip: always visible.
        self._strip = QWidget()
        self._strip.setObjectName("SecondaryTabStrip")
        self._strip_layout = QHBoxLayout(self._strip)
        self._strip_layout.setContentsMargins(0, 0, 0, 0)
        self._strip_layout.setSpacing(0)
        self._strip_layout.addStretch(1)
        self._group = QButtonGroup(self)
        self._group.setExclusive(False)
        layout.addWidget(self._strip)

        # Content host: hidden while collapsed.
        self._content = QStackedWidget()
        self._content.setObjectName("SecondaryContent")
        layout.addWidget(self._content, 1)

        self._content.hide()
        self.setMinimumHeight(self.tab_strip_height())
        self.setMaximumHeight(self.tab_strip_height())

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_tab(self, tab_id: str, title: str, widget: QWidget) -> None:
        """Register *widget* under *tab_id* with the given *title*."""
        button = QToolButton()
        button.setObjectName("SecondaryTab")
        button.setText(title)
        button.setCheckable(True)
        button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        button.clicked.connect(lambda _=False, tid=tab_id: self._on_tab_clicked(tid))
        # Insert before the trailing stretch so tabs sit left-aligned.
        self._strip_layout.insertWidget(self._strip_layout.count() - 1, button)
        self._group.addButton(button)

        page_index = self._content.addWidget(widget)

        self._titles[tab_id] = title
        self._buttons[tab_id] = button
        self._pages[tab_id] = page_index

        self.setMinimumHeight(self.tab_strip_height())
        if not self._expanded:
            self.setMaximumHeight(self.tab_strip_height())

    def set_count(self, tab_id: str, count: int) -> None:
        """Show *count* as a suffix on the tab label (hidden when zero)."""
        title = self._titles.get(tab_id)
        if title is None:
            return
        self._buttons[tab_id].setText(f"{title} ({count})" if count else title)

    def open(self, tab_id: str) -> None:
        """Activate *tab_id* and expand the workspace."""
        if tab_id not in self._buttons:
            return
        self._activate(tab_id)
        self._set_expanded(True)

    def collapse(self) -> None:
        """Collapse the workspace, leaving the tab strip visible."""
        self._set_expanded(False)

    def reset(self) -> None:
        """Return to the default state: collapsed, no active tab."""
        self._activate(None)
        self._set_expanded(False)

    @property
    def is_expanded(self) -> bool:
        return self._expanded

    @property
    def active_id(self) -> str | None:
        return self._active_id

    def tab_strip_height(self) -> int:
        return self._strip.sizeHint().height()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_tab_clicked(self, tab_id: str) -> None:
        # Clicking the active tab collapses; otherwise switch/expand.
        if self._expanded and self._active_id == tab_id:
            self._set_expanded(False)
        else:
            self.open(tab_id)

    def _activate(self, tab_id: str | None) -> None:
        self._active_id = tab_id
        for tid, button in self._buttons.items():
            button.setChecked(tid == tab_id)
        if tab_id is not None:
            self._content.setCurrentIndex(self._pages[tab_id])

    def _set_expanded(self, expanded: bool) -> None:
        if expanded and self._active_id is None:
            return
        if expanded == self._expanded:
            # Still refresh checked-state so the active tab reads correctly.
            if not expanded:
                self._sync_unchecked()
            return

        self._expanded = expanded
        self._content.setVisible(expanded)
        if expanded:
            self.setMaximumHeight(_MAX_HEIGHT)
        else:
            self._sync_unchecked()
            self.setMaximumHeight(self.tab_strip_height())
        self.expanded_changed.emit(expanded)

    def _sync_unchecked(self) -> None:
        for button in self._buttons.values():
            button.setChecked(False)
