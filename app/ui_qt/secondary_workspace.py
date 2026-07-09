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
  - The workspace is parameter-scoped content shown over a document-level
    surface: when there is no parameter to scope it to (the Inspector's
    placeholder), it is force-collapsed via :meth:`suspend`, and restored to
    whatever the user last wanted via :meth:`resume`. Suspension is a
    visibility override, not a change of the user's intent -- collapsing
    while suspended, or expanding again on :meth:`resume`, always reflects
    the *last real user action* (``open``/``collapse``/tab-click), not
    whatever happened while suspended.

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

        # `_intent_expanded` is the user's last real want-open (set only by
        # `open`/`collapse`/tab-clicks); `_suspended` is a visibility override
        # applied while there is no parameter to scope the content to.
        # `is_expanded` (and everything actually rendered) is the derived
        # combination of the two -- see the class docstring.
        self._intent_expanded = False
        self._suspended = False
        self._rendered_visible = False
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
        if not self.is_expanded:
            self.setMaximumHeight(self.tab_strip_height())

    def set_count(self, tab_id: str, count: int) -> None:
        """Show *count* as a suffix on the tab label (hidden when zero)."""
        title = self._titles.get(tab_id)
        if title is None:
            return
        self._buttons[tab_id].setText(f"{title} ({count})" if count else title)

    def open(self, tab_id: str) -> None:
        """Activate *tab_id* and record the user's intent to be expanded.

        Only visibly expands when not currently suspended; while suspended
        the intent is still recorded so a later :meth:`resume` restores it.
        """
        if tab_id not in self._buttons:
            return
        self._active_id = tab_id
        self._intent_expanded = True
        self._render()

    def collapse(self) -> None:
        """Collapse the workspace, leaving the tab strip visible."""
        self._intent_expanded = False
        self._render()

    def reset(self) -> None:
        """Return to the default state: collapsed, no active tab, not suspended."""
        self._active_id = None
        self._intent_expanded = False
        self._suspended = False
        self._render()

    def suspend(self) -> None:
        """Force-collapse because there is no parameter to scope content to.

        Does not touch the user's intent (``open``/``collapse`` state) or the
        active tab -- only the rendered visibility.
        """
        if self._suspended:
            return
        self._suspended = True
        self._render()

    def resume(self) -> None:
        """Undo :meth:`suspend`, restoring the user's last intent.

        Idempotent when not suspended: a direct parameter-to-parameter
        reveal (no intervening placeholder) is a no-op and emits nothing.
        """
        if not self._suspended:
            return
        self._suspended = False
        self._render()

    @property
    def is_expanded(self) -> bool:
        """The workspace's *visible* expanded state: intent minus suspension."""
        return self._intent_expanded and not self._suspended

    @property
    def active_id(self) -> str | None:
        return self._active_id

    def tab_strip_height(self) -> int:
        return self._strip.sizeHint().height()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _on_tab_clicked(self, tab_id: str) -> None:
        # Clicking the active tab while visibly expanded collapses; otherwise
        # switch/expand.
        if self.is_expanded and self._active_id == tab_id:
            self.collapse()
        else:
            self.open(tab_id)

    def _render(self) -> None:
        """Apply the current state to the tab buttons and content stack.

        Emits :attr:`expanded_changed` iff the *rendered* (visible) state
        actually changes -- suspend/resume calls that don't change visibility
        (e.g. ``resume()`` while not suspended, or ``suspend()`` while already
        collapsed) emit nothing.
        """
        visible = self.is_expanded
        for tid, button in self._buttons.items():
            button.setChecked(visible and tid == self._active_id)
        if self._active_id is not None:
            self._content.setCurrentIndex(self._pages[self._active_id])

        if visible == self._rendered_visible:
            return
        self._rendered_visible = visible
        self._content.setVisible(visible)
        self.setMaximumHeight(_MAX_HEIGHT if visible else self.tab_strip_height())
        self.expanded_changed.emit(visible)
