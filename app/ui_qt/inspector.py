"""Inspector (right panel): the work surface for one parameter.

The Inspector has two responsibilities, split top-to-bottom:

  - **Primary editing area** (top): a self-contained ``ParameterCard`` (title,
    validity badge, per-kind value editor and description) inside a scroll
    area.  Editing uses a draft buffer: typing validates a candidate dict live
    (badge updates); Enter commits; Escape discards the draft and restores the
    committed validation state.  The card owns its own widgets; the Inspector
    owns the validation decisions and drives the badge via
    ``ParameterCard.set_validity``.  The badge is *parameter-scoped* in both
    states -- on selection from ``ParameterItem.issues``, while typing from
    ``DocumentSession.preview_parameter_issues`` -- so a document-level
    diagnostic elsewhere in the file never colours this parameter's badge.
  - **Secondary workspace** (bottom): a collapsible, tabbed panel for
    parameter-centric tools (Issues and Documentation today; Analysis,
    References in future).  Parameter documentation is split by depth: the
    card's ( i ) popover is the quick glance (symbol, meaning, units, types,
    ontology link) while the Documentation tab carries the multi-paragraph
    technical prose, which persists beside the editor instead of dismissing
    on the first outside click.  This supersedes roadmap 2.4's
    popover-not-a-tab decision, which predated page-long content.  A vertical
    splitter above the tab strip resizes the whole secondary workspace.

The secondary workspace is workspace state, not parameter state: it starts
collapsed, stays open across parameter changes, and only the user collapses it.
Selecting a parameter refreshes the active tab's content without opening or
closing the workspace.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from core import bpx_gateway
from core.parameter_metadata import resolve_parameter_metadata
from core.tree_model import ParameterItem
from core.validation import Severity
from state.app_state import AppState

from .cards.parameter_card import ParameterCard
from .documentation_tab import DocumentationTab
from .issues_tab import IssuesTab, issue_count
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

        # Editing area (top splitter pane): the scrollable ParameterCard, or
        # the placeholder label when no parameter is selected.
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
        self._docs_tab = DocumentationTab()
        self._secondary.add_tab("docs", "Documentation", self._docs_tab)
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

    def _on_card_expanded(self, expanded: bool) -> None:
        """Give the whole editing pane to a grid that asked to take it over.

        Clearing the card's top alignment lets it (and its expanding grid) fill
        the pane; the secondary workspace collapses to its tab strip so the grid
        has the room. Collapsing restores both.
        """
        if self._card is None:
            return
        self._content_layout.setAlignment(
            self._card, Qt.Alignment() if expanded else Qt.AlignTop
        )
        if expanded:
            self._secondary.suspend()
        else:
            self._secondary.resume()

    def _on_secondary_expanded(self, expanded: bool) -> None:
        total = self._splitter.height()
        if not total:
            return  # not laid out yet; the default splitter sizes are correct
        if expanded:
            height = max(self._panel_height, self._secondary.tab_strip_height())
        else:
            # Collapsing must give the drawer's space back to the editor.
            # Lowering the secondary's maximum height alone does not make the
            # splitter redistribute sizes it was already handed, so clamp pane 1
            # to its tab strip here -- otherwise the content hides but a dead
            # band of empty space is left where it was.
            height = self._secondary.tab_strip_height()
        self._splitter.setSizes([max(total - height, 0), height])

    def _remember_panel_height(self, *_args) -> None:
        if not self._secondary.is_expanded:
            return
        bottom = self._splitter.sizes()[1]
        if bottom > self._secondary.tab_strip_height():
            self._panel_height = bottom

    def show_placeholder(self) -> None:
        self._clear_content()
        self._content_layout.addWidget(
            QLabel("Select an object from the structure to inspect + edit it.")
        )
        self._issues_tab.show_parameter(None)
        self._docs_tab.show_metadata(None)
        self._secondary.set_count("issues", 0)
        self._secondary.suspend()

    def reset(self) -> None:
        """Reset to the default state for a newly opened document."""
        self.show_placeholder()
        self._secondary.reset()
        self._panel_height = _DEFAULT_PANEL_HEIGHT

    def reveal(self, parameter: ParameterItem | None) -> None:
        """Show *parameter*'s work surface, or the placeholder for none.

        This is the Inspector's part of a navigation reveal; object-level
        targets carry no parameter and fall back to the placeholder.
        """
        if parameter is not None:
            self.show_parameter(parameter)
        else:
            self.show_placeholder()

    def show_parameter(self, parameter: ParameterItem) -> None:
        self._secondary.resume()
        self._clear_content()
        meta = bpx_gateway.field_meta(parameter.path)

        self._card = ParameterCard(parameter, meta)
        self._card.draft_changed.connect(self._debounce.start)
        self._card.draft_reset.connect(self._on_reset)
        self._card.commit_requested.connect(self._on_commit)
        self._card.bulk_commit_requested.connect(self._on_bulk_commit)
        self._card.expand_toggled.connect(self._on_card_expanded)
        # Top-aligned so the card sits at its natural height with space beneath;
        # expanding (a grid takeover) clears the alignment so the card -- and its
        # now-stretching grid -- fills the pane. This replaces a trailing stretch
        # so the switch is a single alignment change, no relayout.
        self._content_layout.addWidget(self._card)
        self._content_layout.setAlignment(self._card, Qt.AlignTop)
        self._render_issues(parameter.issues, parameter.has_errors)
        self._card.set_cell_issues(parameter.issues)

        # Refresh the secondary workspace's tabs without changing its
        # open/collapsed state (workspace state, not parameter state).
        count = self._issues_tab.show_parameter(parameter)
        self._secondary.set_count("issues", count)
        self._docs_tab.show_metadata(resolve_parameter_metadata(parameter.path, meta))

    def has_focused_draft(self, widget) -> bool:
        """True when *widget* is inside a card holding an uncommitted draft.

        The Undo shortcut asks this before reverting the document: a spin box
        or combo box has no undo history of its own, so an unguarded ``Ctrl+Z``
        would skip past the draft in front of the user and revert the previous
        commit -- possibly to a parameter off-screen. The Redo shortcut asks
        the same question before reapplying one, for the same reason. Whether
        the draft is discardable is the card's business (Escape), so the
        Inspector answers only whether one exists here.
        """
        card = self._card
        if card is None or widget is None:
            return False
        return card.is_dirty and card.isAncestorOf(widget)

    def _validate_draft(self) -> None:
        if self._card is None or self._state.active is None:
            return
        if self._card.commit_blocked_reason() is not None:
            # The draft has no value to validate. ``value()`` would fall back to
            # the last representable one, so the badge would report "Valid" for
            # a value the user is not looking at, while the editor shows a parse
            # error beside it. Hold the badge instead: the card explains itself.
            return
        issues = self._state.active.preview_parameter_issues(
            self._card.parameter.path, self._card.value()
        )
        errors = [i for i in issues if i.severity == Severity.ERROR]
        self._render_issues(issues, bool(errors))
        self._card.set_cell_issues(issues)
        # Decision Q (reviewed defect M1): the tab badge must count the same
        # merged rows issues_tab.show_parameter renders, not raw diagnostics
        # -- a committed-null FloatInt's float_type+int_type pair (V5) is one
        # displayed row, so len(issues) here previously disagreed with it.
        self._secondary.set_count("issues", issue_count(issues))

    def _on_reset(self) -> None:
        if self._card is None:
            return
        self._debounce.stop()
        self._render_issues(self._card.parameter.issues, self._card.parameter.has_errors)
        self._card.set_cell_issues(self._card.parameter.issues)
        self._secondary.set_count("issues", issue_count(self._card.parameter.issues))

    def _on_commit(self) -> None:
        if self._card is None or self._state.active is None:
            return
        if self._card.commit_blocked_reason() is not None:
            # The draft has no representation at all (unparseable Raw JSON,
            # duplicate map keys). This is not an *invalid* value -- which the
            # card would happily commit for the validator to report -- it is a
            # value that cannot be written without destroying data. The card
            # shows the reason inline; refuse the commit.
            return
        if not self._card.is_dirty:
            # No-op Enter: the draft equals the committed value (type-aware),
            # so committing would just rewrite it -- most importantly, it
            # would turn a stored null into whatever the card's own idea of
            # "empty" is (e.g. "").
            return
        self._state.active.apply_value(self._card.parameter.path, self._card.value())
        self.committed.emit()

    def _on_bulk_commit(self, command) -> None:
        """Execute a card's multi-parameter command (CSV import) as one step.

        The card hands over a ready-made ``SetValues`` naming every path it
        writes; it travels the same command spine as a single-value commit
        (one document rebuild, one undo entry) and the same ``committed``
        signal refreshes the UI. No dirty/blocked gating applies: the payload
        is confirm-gated by its own dialog and independent of this card's
        draft state.
        """
        if self._state.active is None:
            return
        self._state.active.execute_command(command)
        self.committed.emit()

    def _render_issues(self, issues, has_errors: bool) -> None:
        if not issues:
            self._card.set_validity("Valid", OK)
            return
        self._card.set_validity(
            "Invalid" if has_errors else "Warning", ERROR if has_errors else WARNING
        )

    def _clear_content(self) -> None:
        self._card = None
        while self._content_layout.count():
            item = self._content_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Reparent out of the content widget *now*: deleteLater only
                # reaps when the event loop unwinds to its top level, so a
                # widget merely taken from the layout stays a visible child of
                # _content until then -- successive clears stack ghost labels
                # over the live card. setParent(None) removes it immediately.
                widget.setParent(None)
                widget.deleteLater()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
