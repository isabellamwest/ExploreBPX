"""Inspector (right panel): the work surface for one parameter.

The Inspector is one scrolling page, top to bottom:

  - **Surface slot** (top): a self-contained ``ParameterCard`` (header band
    with title and validity mark, per-kind value editor and description) --
    or the placeholder/ghost/experiment/empty-state surface a reveal calls
    for.  Editing uses a draft buffer: typing validates a candidate dict live
    (the header's validity dot/text update); Enter commits; Escape discards
    the draft and restores the committed validation state.  The card owns its
    own widgets; the Inspector owns the validation decisions and drives the
    mark via ``ParameterCard.set_validity``.  The mark is *parameter-scoped*
    in both states -- on selection from ``ParameterItem.issues``, while
    typing from ``DocumentSession.preview_parameter`` -- so a document-level
    diagnostic elsewhere in the file never colours this parameter's mark.
    When ``bpx`` aborted before judging this parameter's section
    (``validation_completed`` is False), an issue-free parameter reads as
    neutral "Not validated" rather than a false green "Valid".
  - **Issues section**: a full-bleed tinted section listing the shown
    parameter's validation issues, present only while it *has* issues
    (committed or live-preview) -- an issue-free parameter's page simply has
    no Issues band.  The row count sits in the section's title row.
  - **Documentation section**: a resident, collapsible tinted section for
    the multi-paragraph technical prose.  Parameter documentation is split
    by depth: the card's ( i ) popover is the quick glance (symbol, meaning,
    units, types, ontology link); this section persists beside the editor
    instead of dismissing on the first outside click.

Both sections replaced the old bottom tab drawer ("secondary workspace"):
same content, in the page's own flow instead of behind tabs.  The
Documentation section's open/collapsed state is workspace state, not
parameter state: it starts collapsed, keeps the user's choice across
parameter changes, and only ``reset`` (a newly opened document) collapses it
again.  A grid takeover (``expand_toggled``) hides both sections so the grid
gets the whole pane, and restores them on collapse.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QLabel,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from core import bpx_gateway
from core.command_service import CommandError
from core.commands import PullParameter, RenameKey
from core.compare import ComparisonResult, RowState
from core.parameter_metadata import resolve_parameter_metadata
from core.parameter_types import ParameterKind, classify
from core.tree_model import ParameterItem
from core.validation import Severity
from state.app_state import AppState
from state.reference_snapshot import ReferenceSnapshot

from .cards.experiment import ExperimentCard, is_validation_run_path
from .cards.ghost_card import GhostParameterCard
from .cards.parameter_card import ParameterCard
from .documentation_view import DocumentationView
from .group_box import TintedSection
from .issues_view import IssuesView
from .style import ERROR, MUTED, OK, WARNING
from .validation_empty_state import ValidationEmptyState


class InspectorPanel(QWidget):
    """Hosts the editing surface and the Issues/Documentation sections."""

    committed = Signal()
    issue_activated = Signal(tuple)

    def __init__(self, state: AppState) -> None:
        super().__init__()
        self._state = state
        self._card = None
        #: Reference comparison state, set only by
        #: ``set_comparison`` -- ``None`` whenever no reference is docked or
        #: its decoration is hidden.
        self._comparison: ComparisonResult | None = None
        self._reference: ReferenceSnapshot | None = None
        self._debounce = QTimer(self, singleShot=True, interval=200)
        self._debounce.timeout.connect(self._validate_draft)
        self._build()
        self.show_placeholder()

    def _build(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # One scrolling page: the surface slot (the card, or the placeholder
        # when no parameter is selected), then the Issues and Documentation
        # sections as full-bleed tinted bands, then the white tail. Zero
        # margins: each card carries its own header band and gutter
        # (cards/page.py) and the section washes must span edge to edge.
        scroll = QScrollArea()
        scroll.setObjectName("InspectorScroll")
        scroll.setWidgetResizable(True)
        self._content = QWidget()
        self._content.setObjectName("InspectorContent")
        self._content_layout = QVBoxLayout(self._content)
        self._content_layout.setContentsMargins(0, 0, 0, 0)
        # The 16px white gap between stacked tinted sections (the Workspace
        # page's rhythm).
        self._content_layout.setSpacing(16)
        scroll.setWidget(self._content)

        # Surface slot: the one child a reveal replaces. A fixed container
        # keeps the page's child order stable so section/tail bookkeeping
        # never depends on what is currently showing.
        self._surface = QWidget()
        self._surface_layout = QVBoxLayout(self._surface)
        self._surface_layout.setContentsMargins(0, 0, 0, 0)
        self._surface_layout.setSpacing(0)
        self._content_layout.addWidget(self._surface)

        # Issues section: present only while the shown parameter has issues;
        # the merged row count sits in the caps-title row's suffix, the same
        # spot the parameter-list header carries its count.
        self._issues_view = IssuesView()
        self._issues_view.issue_activated.connect(self.issue_activated)
        self._issues_count = QLabel("")
        self._issues_count.setObjectName("InspectorIssuesCount")
        self._issues_section = TintedSection(
            "Issues", object_name="InspectorIssuesSection", suffix=self._issues_count
        )
        self._issues_section.body_layout.addWidget(self._issues_view)
        self._issues_section.hide()
        self._content_layout.addWidget(self._issues_section)

        # Documentation section: resident and collapsible. Starts collapsed
        # -- a slim tinted band -- and keeps the user's open/collapsed
        # choice across parameter changes (workspace state, not parameter
        # state); only ``reset`` collapses it again.
        self._docs_view = DocumentationView()
        self._docs_section = TintedSection(
            "Documentation", object_name="InspectorDocsSection", collapsible=True
        )
        self._docs_section.body_layout.addWidget(self._docs_view)
        self._docs_section.set_collapsed(True)
        self._docs_section.hide()
        self._content_layout.addWidget(self._docs_section)

        self._content_layout.addStretch(1)
        #: Index of the trailing stretch (the page's white tail). Its
        #: stretch and the surface slot's are swapped whenever the surface
        #: must own the leftover space instead (a centred placeholder, a
        #: grid takeover) -- see ``_set_surface_fills``.
        self._tail_index = self._content_layout.count() - 1

        #: Whether the current surface is parameter-scoped (sections may
        #: show at all) and whether a grid has taken the pane over (they
        #: must not).
        self._sections_active = False
        self._grid_expanded = False
        self._issue_row_count = 0

        outer.addWidget(scroll, 1)

    # ------------------------------------------------------------------
    # Surface slot and section coordination
    # ------------------------------------------------------------------

    def _set_surface(self, widget: QWidget, *, fills: bool) -> None:
        """Install *widget* as the surface slot's content.

        *fills* hands the slot the page's leftover space (a centred
        placeholder); otherwise the widget sits at its natural height and
        the white tail keeps the leftover. Always clears ``_card`` and the
        grid-takeover flag -- callers set ``_card`` after installing.
        """
        self._clear_surface()
        self._surface_layout.addWidget(widget)
        self._set_surface_fills(fills)

    def _set_surface_fills(self, fills: bool) -> None:
        self._content_layout.setStretch(0, 1 if fills else 0)
        self._content_layout.setStretch(self._tail_index, 0 if fills else 1)

    def _on_card_expanded(self, expanded: bool) -> None:
        """Give the whole editing pane to a grid that asked to take it over.

        The surface slot claims the page's leftover space (so the card --
        and its now-stretching grid -- fills the pane) and the Issues/
        Documentation sections get out of the way. Collapsing restores both.
        """
        if self._card is None:
            return
        self._grid_expanded = expanded
        self._set_surface_fills(expanded)
        self._update_sections()

    def _update_sections(self) -> None:
        """Apply the two section-visibility rules: only a parameter-scoped
        surface shows sections at all, and a grid takeover hides them; the
        Issues section additionally needs at least one row."""
        show = self._sections_active and not self._grid_expanded
        self._issues_section.setVisible(show and self._issue_row_count > 0)
        self._docs_section.setVisible(show)

    def _show_issue_rows(self, issues, path: tuple[str, ...] | None) -> None:
        """Rebuild the Issues section -- rows, title-row count, visibility.

        The one path every issues display goes through, committed or
        live-preview, so the section's count and its rows can never
        disagree (the view's merged row count is the only count shown).
        """
        self._issue_row_count = self._issues_view.show_issues(issues, path)
        self._issues_count.setText(str(self._issue_row_count))
        self._update_sections()

    def _activate_sections(self, parameter: ParameterItem, meta) -> None:
        """Scope both sections to *parameter*. Never touches the
        Documentation section's open/collapsed state (workspace state, not
        parameter state)."""
        self._sections_active = True
        self._show_issue_rows(parameter.issues, parameter.path)
        self._docs_view.show_metadata(resolve_parameter_metadata(parameter.path, meta))
        self._update_sections()

    def _deactivate_sections(self) -> None:
        """No parameter-scoped surface: clear and hide both sections."""
        self._sections_active = False
        self._show_issue_rows((), None)
        self._docs_view.show_metadata(None)
        self._update_sections()

    def show_placeholder(self) -> None:
        placeholder = QLabel("Select an object from the structure to inspect + edit it.")
        placeholder.setObjectName("InspectorPlaceholder")
        # The one surface with no page header of its own: centred in the
        # pane (an empty state), not typeset at the top-left of a page.
        placeholder.setAlignment(Qt.AlignCenter)
        self._set_surface(placeholder, fills=True)
        self._deactivate_sections()

    def reset(self) -> None:
        """Reset to the default state for a newly opened document."""
        self.show_placeholder()
        self._docs_section.set_collapsed(True)

    def set_comparison(
        self, comparison: ComparisonResult | None, reference: ReferenceSnapshot | None
    ) -> None:
        """Set the reference comparison state.

        Called by ``MainWindow`` -- the single place computing this state --
        on every document change and every reference dock/undock/hide
        toggle. Refreshes the *currently shown* card in place, without
        rebuilding it: a ``ParameterCard`` gets its reference block
        refreshed (never touching its own draft/commit machinery); a
        ``GhostParameterCard`` -- which exists only because a comparison was
        showing -- falls back to the placeholder once *comparison* goes
        ``None`` (hidden, undocked, or no document).
        """
        self._comparison = comparison
        self._reference = reference
        if isinstance(self._card, ParameterCard):
            self._apply_reference_block(self._card.parameter)
        elif isinstance(self._card, GhostParameterCard) and comparison is None:
            self.show_placeholder()

    def _apply_reference_block(self, parameter: ParameterItem) -> None:
        """Populate/hide the current card's reference block from *parameter*.

        No-op-safe to call whenever the current card is a ``ParameterCard``,
        whichever comparison state is active; hides the block outright with
        no comparison, no docked reference, or a MAIN_ONLY row (the
        reference has no such key at all).
        """
        if self._card is None:
            return
        if self._comparison is None or self._reference is None:
            self._card.set_reference(None, None, None)
            return
        section_path = tuple(parameter.path[:-1])
        row = self._comparison.row(section_path, parameter.path[-1])
        if row is None or row.state is RowState.MAIN_ONLY:
            self._card.set_reference(None, None, None)
            return
        meta = bpx_gateway.field_meta(parameter.path)
        kind = classify(row.ref_value, meta)
        self._card.set_reference(row.ref_value, row.state, kind)

    def show_ghost_parameter(self, section_path: tuple[str, ...], key: str) -> None:
        """Show the read-only ghost card for a REF_ONLY row: a parameter
        the docked reference has and the main document does not. Falls
        back to the placeholder if the comparison
        has moved on since the row was selected (e.g. the reference was
        just undocked)."""
        if self._comparison is None or self._reference is None:
            self.show_placeholder()
            return
        row = self._comparison.row(section_path, key)
        if row is None or row.state is not RowState.REF_ONLY:
            self.show_placeholder()
            return
        meta = bpx_gateway.field_meta(section_path + (key,))
        kind = classify(row.ref_value, meta)
        card = GhostParameterCard(section_path, key, row.ref_value, kind)
        card.copy_up_requested.connect(self._on_ghost_copy_up)
        self._set_surface(card, fills=False)
        self._card = card
        self._deactivate_sections()

    def reveal(self, parameter: ParameterItem | None) -> None:
        """Show *parameter*'s work surface, or the placeholder for none.

        This is the Inspector's part of a navigation reveal; object-level
        targets carry no parameter and fall back to the placeholder -- except
        the bare ``("Validation",)`` container with zero runs, which gets its
        own guided empty state instead (see
        ``_show_validation_empty_state``). With at least one run, or for
        every other object-level target, the placeholder is unchanged.

        A target whose owning object is a Validation run routes to the
        unified ``ExperimentCard`` instead -- whether navigation resolved to
        one of the run's own array columns (focused there) or to the bare run
        node (``parameter is None``, nothing focused). Any *other* parameter
        under a run (a custom, non-array field) keeps today's single-parameter
        card: only a genuine array reroutes.
        """
        run_path = self._experiment_run_path(parameter)
        if run_path is not None:
            self._show_experiment(run_path, parameter)
        elif parameter is not None:
            self.show_parameter(parameter)
        elif self._is_empty_validation_container():
            self._show_validation_empty_state()
        else:
            self.show_placeholder()

    def _is_empty_validation_container(self) -> bool:
        """Whether this reveal targets the bare ``("Validation",)`` node and
        it currently has zero runs -- the one case the guided empty state
        replaces the placeholder for (see ``reveal``)."""
        session = self._state.active
        if session is None or session.selected_path != ("Validation",):
            return False
        node = session.document.find(("Validation",)) if session.document else None
        return node is not None and not node.children

    def _experiment_run_path(self, parameter: ParameterItem | None) -> tuple[str, ...] | None:
        """The Validation-run path this reveal targets, or ``None``.

        ``reveal`` only ever receives a parameter (or ``None``) -- never the
        object-level path a bare node selection resolved to -- so the bare-
        node case is read back from session state instead:
        ``NavigationService.navigate`` always calls ``session.select`` (or
        ``select_parameter``, which also updates ``selected_path``) *before*
        emitting, so ``selected_path`` already holds the fresh object path by
        the time this runs.
        """
        if parameter is not None:
            owner = tuple(parameter.path[:-1])
            if is_validation_run_path(owner) and parameter.kind is ParameterKind.SERIES:
                return owner
            return None
        session = self._state.active
        if session is not None and session.selected_path is not None:
            if is_validation_run_path(session.selected_path):
                return session.selected_path
        return None

    def _show_experiment(self, run_path: tuple[str, ...], parameter: ParameterItem | None) -> None:
        """Build and show the unified ``ExperimentCard`` for *run_path*.

        Re-derives the run's :class:`~core.tree_model.TreeNode` from the
        *current* document on every call (never cached across a rebuild), so
        a rename or undo/redo while the card is open cannot leave it stale --
        the same reveal-after-command pattern every other card relies on.
        """
        session = self._state.active
        node = session.document.find(run_path) if session and session.document else None
        if node is None:
            self.show_placeholder()
            return
        focused_alias = parameter.label if parameter is not None else None
        document_name = (
            session.backing_file.name if session.backing_file else session.document.filename
        )
        card = ExperimentCard(node, focused_alias, document_name=document_name)
        card.bulk_commit_requested.connect(self._on_bulk_commit)
        card.expand_toggled.connect(self._on_card_expanded)
        self._set_surface(card, fills=False)
        self._card = card

        # The sections stay scoped to one parameter, so they show the
        # focused array's own issues/documentation (mirroring the
        # single-parameter card), or hide entirely for a bare run-node
        # reveal.
        if parameter is not None:
            self._activate_sections(parameter, bpx_gateway.field_meta(parameter.path))
        else:
            self._deactivate_sections()

    def _show_validation_empty_state(self) -> None:
        """Build and show the guided empty state for a zero-run Validation
        section (see ``reveal``/``_is_empty_validation_container``).

        Mirrors ``show_placeholder``'s section state (nothing to show
        issues/documentation for), not a real card's -- this is a
        substitute for the placeholder, not a parameter work surface.
        """
        card = ValidationEmptyState()
        card.bulk_commit_requested.connect(self._on_bulk_commit)
        self._set_surface(card, fills=False)
        self._card = card
        self._deactivate_sections()

    def show_parameter(self, parameter: ParameterItem) -> None:
        meta = bpx_gateway.field_meta(parameter.path)

        card = ParameterCard(parameter, meta)
        card.draft_changed.connect(self._debounce.start)
        card.draft_reset.connect(self._on_reset)
        card.commit_requested.connect(self._on_commit)
        card.bulk_commit_requested.connect(self._on_bulk_commit)
        card.expand_toggled.connect(self._on_card_expanded)
        card.rename_requested.connect(self._on_card_rename_requested)
        card.copy_up_requested.connect(self._on_copy_up)
        # The card sits at its natural height with the page's white tail
        # beneath; expanding (a grid takeover) hands the surface slot the
        # leftover space instead -- see _on_card_expanded.
        self._set_surface(card, fills=False)
        self._card = card
        self._render_issues(
            parameter.issues, parameter.has_errors, self._committed_validation_completed()
        )
        self._card.set_cell_issues(parameter.issues)

        # Refresh both sections; the Documentation section's open/collapsed
        # state is untouched (workspace state, not parameter state).
        self._activate_sections(parameter, meta)
        # Populate-after-build: the reference block
        # is entirely outside the draft/commit signals just wired above, so
        # this can never trip the card's own _touched machinery.
        self._apply_reference_block(parameter)

    def open_rename_editor(self) -> None:
        """Expand the current card's inline rename row, if it has one.

        Used by the parameter-list row's "Rename…" context-menu action:
        called after navigating so the target parameter's card is already
        showing, this opens the same header editor the card's own pencil
        button opens -- one rename surface, not two. A no-op when the
        current card carries no rename row at all (a non-``ParameterCard``,
        or a ``ParameterCard`` for a non-renamable, schema-named parameter).
        """
        opener = getattr(self._card, "open_rename_editor", None)
        if callable(opener):
            opener()

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

    def has_pending_draft(self) -> bool:
        """True when the showing card holds an uncommitted draft.

        Unlike :meth:`has_focused_draft` this asks nothing about focus: the
        file-level actions (Save, Open, New, close) need to know a draft
        exists whether or not the card still has the keyboard, because all
        four would otherwise walk straight past it.
        """
        return self._card is not None and self._card.is_dirty

    def apply_pending_draft(self) -> bool:
        """Commit the showing card's draft, as Enter would. True if safe.

        Returns False only when a draft exists but *cannot* be written
        (:meth:`EditorCard.commit_blocked_reason` -- unparseable Raw JSON,
        duplicate map keys). The card is already showing that reason inline,
        so the caller aborts rather than saving a document that does not
        include what the user is looking at. No draft, or one that applies
        cleanly, both answer True.
        """
        if not self.has_pending_draft():
            return True
        if self._card.commit_blocked_reason() is not None:
            return False
        self._on_commit()
        return True

    def _validate_draft(self) -> None:
        if self._card is None or self._state.active is None:
            return
        if self._card.commit_blocked_reason() is not None:
            # The draft has no value to validate. ``value()`` would fall back to
            # the last representable one, so the badge would report "Valid" for
            # a value the user is not looking at, while the editor shows a parse
            # error beside it. Hold the badge instead: the card explains itself.
            return
        preview = self._state.active.preview_parameter(
            self._card.parameter.path, self._card.value()
        )
        issues = preview.issues
        errors = [i for i in issues if i.severity == Severity.ERROR]
        self._render_issues(issues, bool(errors), preview.validation_completed)
        self._card.set_cell_issues(issues)
        # Live preview drives the Issues section like a commit would: rows,
        # count and visibility all rebuilt from the previewed issues, so the
        # section appears/disappears while typing and its count can never
        # disagree with its rows (the merged-row rule lives in the view).
        self._show_issue_rows(issues, self._card.parameter.path)

    def _on_reset(self) -> None:
        if self._card is None:
            return
        self._debounce.stop()
        self._render_issues(
            self._card.parameter.issues,
            self._card.parameter.has_errors,
            self._committed_validation_completed(),
        )
        self._card.set_cell_issues(self._card.parameter.issues)
        self._show_issue_rows(self._card.parameter.issues, self._card.parameter.path)

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

    def _on_card_rename_requested(self, path: tuple, new_key: str) -> None:
        """Execute the card header's rename row as a ``RenameKey`` command.

        A refusal (empty/unchanged name, or a name already taken by a
        sibling -- ``core.command_service`` decides, never this layer) is
        reported back to the still-showing card as an inline error instead
        of a dialog, the same convention other cards use for a blocked
        commit; nothing here duplicates the command service's own gating.
        """
        if self._state.active is None:
            return
        try:
            self._state.active.execute_command(RenameKey(tuple(path), new_key))
        except CommandError as exc:
            if self._card is not None:
                self._card.show_rename_error(str(exc))
            return
        self.committed.emit()

    def _on_copy_up(self) -> None:
        """Execute the current ``ParameterCard``'s "Copy up": copy the
        docked reference's raw value verbatim into the main document at
        this parameter's path.

        The reference value comes from the stored comparison, not any value
        cached on the card, so this always reflects the comparison last
        computed. Guards defensively against a stale/absent comparison or an
        EQUAL row (the button is already disabled for EQUAL from the UI side
        -- ``ReferenceValueBlock.set_content`` -- this is a backstop, not a
        second implementation of that rule). Reuses the ``committed`` signal
        so ``MainWindow`` runs its standard post-commit refresh, which
        recomputes the comparison from the new document.
        """
        if self._card is None or self._state.active is None:
            return
        if self._comparison is None or self._reference is None:
            return
        parameter = self._card.parameter
        section_path = parameter.path[:-1]
        row = self._comparison.row(section_path, parameter.path[-1])
        if row is None or row.state in (RowState.MAIN_ONLY, RowState.EQUAL):
            return
        self._state.active.execute_command(PullParameter(parameter.path, row.ref_value))
        self.committed.emit()

    def _on_ghost_copy_up(self) -> None:
        """Execute a ghost row's "Copy up": a REF_ONLY
        row has no parameter in the main document yet, so this always adds
        one. The ``GhostParameterCard`` retains ``section_path``/``key`` --
        there is no committed parameter to read a path from -- and, as in
        ``_on_copy_up``, the value is re-resolved from the stored comparison
        rather than the card's own cached copy.
        """
        if not isinstance(self._card, GhostParameterCard) or self._state.active is None:
            return
        if self._comparison is None or self._reference is None:
            return
        section_path, key = self._card.section_path, self._card.key
        row = self._comparison.row(section_path, key)
        if row is None or row.state is not RowState.REF_ONLY:
            return
        self._state.active.execute_command(PullParameter(section_path + (key,), row.ref_value))
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

    def _committed_validation_completed(self) -> bool:
        """The committed document's word on whether ``bpx`` judged it fully."""
        session = self._state.active
        if session is None or session.document is None:
            return True
        return session.document.validation_completed

    def _render_issues(self, issues, has_errors: bool, completed: bool = True) -> None:
        if not issues:
            # No issue attached is only a clean bill of health if bpx actually
            # ran to completion; after a staged abort (bad Header masking the
            # body, bad Parameterisation masking State/Validation) this
            # parameter was never judged, and claiming "Valid" would be false.
            if completed:
                self._card.set_validity("Valid", OK)
            else:
                self._card.set_validity("Not validated", MUTED)
            return
        self._card.set_validity(
            "Invalid" if has_errors else "Warning", ERROR if has_errors else WARNING
        )

    def _clear_surface(self) -> None:
        self._card = None
        self._grid_expanded = False
        while self._surface_layout.count():
            item = self._surface_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                # Reparent out of the content widget *now*: deleteLater only
                # reaps when the event loop unwinds to its top level, so a
                # widget merely taken from the layout stays a visible child of
                # _content until then -- successive clears stack ghost labels
                # over the live card. setParent(None) removes it immediately.
                #
                # hide() must come first: setParent(None) marks a widget hidden
                # only if it is *already* visible, and a widget added to a
                # visible layout is merely queued to be shown. Reparenting one
                # in that queued state lets the pending show land on it once it
                # is parentless -- a decorated top-level window titled "python",
                # flashing for the frame before deleteLater reaps it.
                widget.hide()
                widget.setParent(None)
                widget.deleteLater()
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
