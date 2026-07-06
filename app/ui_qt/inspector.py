"""Inspector (right panel): the work surface for one parameter.

The Inspector has two responsibilities, split top-to-bottom:

  - **Primary editing area** (top): title + validity badge, a per-kind value
    editor card, and an optional description.  Editing uses a draft buffer:
    typing validates a candidate dict live (badge updates); Enter commits;
    Escape discards the draft and restores the committed validation state.
  - **Secondary workspace** (bottom): a collapsible, tabbed panel for
    parameter-centric tools (Issues today; Analysis, Documentation, References
    in future).  A vertical splitter above the tab strip resizes the whole
    secondary workspace.

The secondary workspace is workspace state, not parameter state: it starts
collapsed, stays open across parameter changes, and only the user collapses it.
Selecting a parameter refreshes the active tab's content without opening or
closing the workspace.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core import bpx_gateway
from core.tree_model import ParameterItem
from core.validation import Severity
from state.app_state import AppState

from .cards.registry import create_card
from .issues_tab import IssuesTab
from .secondary_workspace import SecondaryWorkspace
from .style import ERROR, OK, WARNING

_DEFAULT_PANEL_HEIGHT = 200


class InspectorPanel(QWidget):
    """Hosts the editing card and the secondary workspace for one parameter."""

    committed = Signal()
    issue_activated = Signal(tuple)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._card = None
        self._panel_height = _DEFAULT_PANEL_HEIGHT
        self._debounce = QTimer(self, singleShot=True, interval=200)
        self._debounce.timeout.connect(self._validate_draft)
        self._build()
        self.show_placeholder()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # Header stays above the splitter so it is always visible.
        header = QHBoxLayout()
        self._title = QLabel("")
        self._title.setObjectName("CardTitle")
        self._badge = QLabel("")
        header.addWidget(self._title, 1)
        header.addWidget(self._badge)
        outer.addLayout(header)

        # Editing area (top splitter pane): the scrollable card + description.
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content_layout = QVBoxLayout(self._content)
        scroll.setWidget(self._content)

        # Secondary workspace (bottom splitter pane).
        self._secondary = SecondaryWorkspace()
        self._issues_tab = IssuesTab()
        self._issues_tab.issue_activated.connect(self.issue_activated)
        self._secondary.add_tab("issues", "Issues", self._issues_tab)
        self._secondary.expanded_changed.connect(self._on_secondary_expanded)

        self._splitter = QSplitter(Qt.Vertical)
        self._splitter.addWidget(scroll)
        self._splitter.addWidget(self._secondary)
        self._splitter.setCollapsible(0, False)
        self._splitter.setCollapsible(1, False)
        self._splitter.setStretchFactor(0, 1)
        self._splitter.setStretchFactor(1, 0)
        self._splitter.splitterMoved.connect(self._remember_panel_height)
        outer.addWidget(self._splitter, 1)

    # ------------------------------------------------------------------
    # Secondary workspace coordination
    # ------------------------------------------------------------------

    def _on_secondary_expanded(self, expanded: bool) -> None:
        if not expanded:
            return
        total = self._splitter.height()
        height = max(self._panel_height, self._secondary.tab_strip_height())
        self._splitter.setSizes([max(total - height, 0), height])

    def _remember_panel_height(self, *_args) -> None:
        if not self._secondary.is_expanded:
            return
        bottom = self._splitter.sizes()[1]
        if bottom > self._secondary.tab_strip_height():
            self._panel_height = bottom

    def show_placeholder(self) -> None:
        self._clear_content()
        self._title.setText("")
        self._badge.setText("")
        self._badge.setStyleSheet("")
        self._content_layout.addWidget(
            QLabel("Select an object from the structure to inspect + edit it.")
        )
        self._issues_tab.show_parameter(None)
        self._secondary.set_count("issues", 0)

    def reset(self) -> None:
        """Reset to the default state for a newly opened document."""
        self.show_placeholder()
        self._secondary.reset()
        self._panel_height = _DEFAULT_PANEL_HEIGHT

    def show_parameter(self, parameter: ParameterItem) -> None:
        self._clear_content()
        meta = bpx_gateway.metadata_index().get(parameter.label)
        self._title.setText(parameter.label)

        self._card = create_card(parameter, meta)
        self._card.draft_changed.connect(self._debounce.start)
        self._card.draft_reset.connect(self._on_reset)
        self._card.commit_requested.connect(self._on_commit)
        self._content_layout.addWidget(self._card)

        if parameter.description:
            self._content_layout.addWidget(QLabel("Description:", objectName="Heading"))
            desc = QTextEdit(parameter.description)
            desc.setReadOnly(True)
            desc.setMaximumHeight(120)
            self._content_layout.addWidget(desc)

        self._content_layout.addStretch(1)
        self._render_issues(parameter.issues, parameter.has_errors)

        # Refresh the secondary workspace's active tab without changing its
        # open/collapsed state (workspace state, not parameter state).
        count = self._issues_tab.show_parameter(parameter)
        self._secondary.set_count("issues", count)


    def _validate_draft(self) -> None:
        if self._card is None or self._state.active is None:
            return
        result = self._state.active.preview_value(self._card.parameter.path, self._card.value())
        errors = [i for i in result.issues if i.severity == Severity.ERROR]
        self._render_issues(result.issues, bool(errors))

    def _on_reset(self) -> None:
        if self._card is None:
            return
        self._debounce.stop()
        self._render_issues(self._card.parameter.issues, self._card.parameter.has_errors)

    def _on_commit(self) -> None:
        if self._card is None or self._state.active is None:
            return
        self._state.active.apply_value(self._card.parameter.path, self._card.value())
        self.committed.emit()

    def _render_issues(self, issues, has_errors: bool) -> None:
        if not issues:
            self._set_badge("Valid", OK)
            return
        self._set_badge("Invalid" if has_errors else "Warning", ERROR if has_errors else WARNING)

    def _set_badge(self, text: str, colour: str) -> None:
        self._badge.setText(text)
        self._badge.setStyleSheet(
            f"color: white; background: {colour}; padding: 2px 8px; border-radius: 3px;"
        )

    def _clear_content(self) -> None:
        self._card = None
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
