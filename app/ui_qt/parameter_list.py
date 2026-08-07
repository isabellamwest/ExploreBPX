"""Parameter list (middle panel): direct parameters of the selected object.

The pane's own section header -- a tinted wash naming the selected object
and counting its parameters -- also hosts the section-scoped "+ Add" entry
point: a quiet button in the header's right-aligned suffix, enabled only
when a document is loaded and an object is selected, that opens
:class:`~.add_parameter_popup.AddParameterPopup` anchored underneath it.
This is deliberately the only add-parameter surface; creation is never
offered by a row's right-click.

A row's right-click context menu instead offers actions on that *existing*
row: "Remove parameter" (also reachable via the Delete key once a row is
current), and -- gated by ``core.structure.can_rename_parameter``/
``can_duplicate_parameter`` -- "Rename…" and "Duplicate". True for content
inside the open ``Parameterisation/User-defined`` bucket, Particle materials,
Validation runs, and any parameter leaf the schema defines nowhere, wherever
it lives. "Move up"/"Move down" are offered for every real row, individually
disabled at the first/last sibling. Context menus never create; creation
controls are never hidden behind a right-click (see the parameter-list pane
section of docs/architecture.md).

"Rename…" does not open its own popup: it opens (or focuses) the same
inline card-header editor the row's own parameter card offers via a pencil
button (:class:`~.cards.parameter_card.ParameterCard`) -- one rename surface,
not two independently-drifting ones.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from core import completion, structure
from core.bpx_gateway import field_meta
from core.compare import (
    RowDiff,
    RowState,
    group_reference_values,
    merged_ghost_keys,
    merged_row_state,
)
from core.completion import MissingField
from core.parameter_types import classify
from core.tree_model import TreeNode

from . import parameter_row, style, typography
from .add_parameter_popup import AddParameterPopup, suggestion_row_html, suggestion_row_text
from .cards.experiment import is_validation_run_path
from .comparison_strip import ComparisonStrip
from .reference_identity import ReferencePin
from .group_box import TintedSectionHeader
from .parameter_row import ParameterRowDelegate

#: RowState -> gutter-bar variant (:data:`parameter_row.REF_BAR_ROLE`).
#: DIFFERS and FILLABLE both read "the reference disagrees or has something
#: this file doesn't" (solid bar); EQUAL is the quiet pale bar, so "same"
#: and "not in the reference" (MAIN_ONLY, no bar at all) stay tellable
#: apart. Comparison is information, not a severity: no warning tint.
_ROW_BAR_VARIANTS = {
    RowState.DIFFERS: "differs",
    RowState.FILLABLE: "differs",
    RowState.EQUAL: "equal",
}

#: Models under which the "fields to add" group may appear at all: Partial
#: suggests every expected field (none Required); a concrete model suggests
#: with Required flags as-is. An undeclared/garbage model is deliberately
#: excluded here even though ``completion_for`` would happily resolve one --
#: the one visible completion task there is "declare a model", not a list
#: of suggestions against a model the user hasn't picked.
#: Header's own group is exempt from this gate (see
#: ``_append_missing_fields_group``): its fields don't depend on the model.
_COMPLETION_GROUP_MODELS = completion.CONCRETE_MODELS | {"Partial"}


def _missing_field_html(field: MissingField) -> str:
    """One suggestion row's rich-text fragment: a leading "+" (this row's
    action) followed by the add-parameter popup's own Suggested-row
    rendering (:func:`suggestion_row_html`, "suggested" tier) -- reused
    verbatim, REQUIRED tag included, so the popup and this group speak one
    visual language rather than two independently drifting ones."""
    plus = f'<span style="{typography.semibold_qss()} color:{style.ACCENT};">+</span>&nbsp;'
    return plus + suggestion_row_html(field.alias, field.meta, "suggested", field.required)


class _ParameterListView(QListWidget):
    """A ``QListWidget`` whose Delete key removes the current row.

    A small subclass -- matching the local key-handling convention already
    used by :class:`~.add_parameter_popup._PopupInput` -- rather than a
    ``QAction`` shortcut. A ``QAction``'s live keyboard binding only fires
    while the widget genuinely holds Qt's application focus, which makes it
    unreliable to drive deterministically; overriding the key event handles
    Delete directly and always acts on whichever row is current, exactly
    like Enter/Escape on the editor cards. This is therefore the *only*
    Delete binding -- the context-menu action deliberately declares none.
    """

    delete_requested = Signal()
    #: Return/Enter on whichever row is current. Only the "fields to add"
    #: group's suggestion rows act on this (mirrors the add-parameter
    #: popup's Enter-to-activate) -- the panel decides what, if anything, the
    #: current row does; a real parameter row had no Enter behaviour before
    #: this and still has none.
    activate_current_requested = Signal()

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key_Delete:
            self.delete_requested.emit()
            return
        if event.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.activate_current_requested.emit()
            return
        super().keyPressEvent(event)


class ParameterListPanel(QWidget):
    """Lists a node's parameters; emits the selected parameter's path."""

    parameter_selected = Signal(tuple)
    #: (section_path, key, seed) -- seed is ``None`` for a schema suggestion
    #: (either the popup's or this panel's own "fields to add" rows) and the
    #: type-matching seed (0.0/""/False/table/list) for the add-parameter
    #: popup's inline custom-parameter form.
    add_parameter_requested = Signal(tuple, str, object)
    remove_parameter_requested = Signal(tuple)  # parameter_path
    #: (parameter_path,): open/focus the row's inline card-header rename editor.
    rename_parameter_requested = Signal(tuple)
    #: (parameter_path,): duplicate the row via ``core.commands.DuplicateParameter``.
    duplicate_parameter_requested = Signal(tuple)
    #: (parameter_path, direction): reorder the row via ``core.commands.MoveParameter``.
    #: ``direction`` is ``"up"`` or ``"down"``.
    move_parameter_requested = Signal(tuple, str)
    #: (section_path, key): a REF_ONLY ghost row was selected -- distinct
    #: from ``parameter_selected`` because a ghost row names no real
    #: document parameter for ``NavigationService`` to resolve.
    ghost_selected = Signal(tuple, str)

    #: Item-data roles marking a synthetic "fields to add" row -- a group
    #: header or one field suggestion -- as distinct from a real parameter
    #: row. Every synthetic row also sets role 256 (the parameter-path role
    #: real rows carry) to ``None``, so the selection/removal/context-menu
    #: handlers -- which all read role 256 -- treat a synthetic row as
    #: "nothing to act on" instead of acting on a bogus path.
    _GROUP_ROW_KIND_ROLE = Qt.UserRole + 300  # "header" | "suggestion" | "ghost"
    _GROUP_ROW_ALIAS_ROLE = Qt.UserRole + 301  # suggestion rows only
    _GHOST_KEY_ROLE = Qt.UserRole + 302  # ghost rows only: the reference-only key

    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._node: TreeNode | None = None
        self._model: str | None = None
        #: Whether the "fields to add" group is expanded, keyed by section
        #: path: a rebuild of the *same* section (every "+" commits a
        #: command, which rebuilds) preserves the flag, while navigating to
        #: a different section reads a fresh (default-collapsed) entry.
        self._expanded: dict[tuple[str, ...], bool] = {}
        #: Parameter paths with a *page-visible* issue, mapped to the row's
        #: worst severity ("error"/"warning"), set by
        #: ``MainWindow._refresh_all`` from ``core.completion.partition_issues``
        #: alongside ``show_node``/``reveal`` -- never computed here. The dot
        #: marker reads this instead of ``parameter.has_errors`` (validator-
        #: verbatim), so an absorbed diagnostic's own parameter shows calm
        #: (grey, no dot) here even though the card badge/Issues tab still
        #: report it verbatim.
        self._visible_issue_severities: dict[tuple[str, ...], str] = {}
        #: The pinned references with their comparisons and badge identity,
        #: set only by ``MainWindow._apply_comparison`` -- empty whenever
        #: nothing is pinned or no document is open. Every mark below is an
        #: aggregate across all of them (``core.compare.merged_row_state`` /
        #: ``merged_ghost_keys``), never the first pin's opinion alone.
        self._pins: list[ReferencePin] = []
        #: True while the active session refuses edits (D3's "Open as-is"):
        #: the add button hides, rows offer no menu or Delete, and the
        #: "fields to add" invitations are not appended.
        self._read_only = False

        self._count_label = QLabel()
        self._count_label.setObjectName("ParameterListHeaderCount")

        self._add_button = QPushButton("+ Add")
        self._add_button.setObjectName("AddParameterButton")
        self._add_button.setFlat(True)
        self._add_button.setCursor(Qt.PointingHandCursor)
        self._add_button.setEnabled(False)
        self._add_button.clicked.connect(self._open_add_popup)

        suffix = QWidget()
        suffix_layout = QHBoxLayout(suffix)
        suffix_layout.setContentsMargins(0, 0, 0, 0)
        suffix_layout.setSpacing(8)
        suffix_layout.addWidget(self._count_label)
        suffix_layout.addWidget(self._add_button)

        self._header = TintedSectionHeader(
            "", object_name="ParameterListHeader", suffix=suffix
        )
        self._header.hide()  # no section selected yet
        layout.addWidget(self._header)

        # Comparison strip: a second, slimmer wash sitting directly beneath
        # the section header wash -- two adjacent full-width tints, no gap
        # or line between them (``layout.setSpacing(0)`` above).
        self._strip = ComparisonStrip()
        layout.addWidget(self._strip)

        self._list = _ParameterListView()
        self._list.setObjectName("ParameterListView")
        # A long label (name plus unit) wraps onto a second line rather than
        # being cut off -- matching the add-parameter popup's rows, and
        # rendered by the same shared delegate.
        self._list.setWordWrap(True)
        self._list.setItemDelegate(ParameterRowDelegate(self._list))
        self._list.itemClicked.connect(self._on_clicked)
        self._list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._list.customContextMenuRequested.connect(self._on_context_menu_requested)
        self._list.delete_requested.connect(self._remove_current_parameter)
        self._list.activate_current_requested.connect(self._on_activate_current)
        layout.addWidget(self._list)

        # The single action behind the context menu's "Remove parameter"
        # entry. It carries no ``QKeySequence``: the live Delete accelerator
        # is ``_ParameterListView.keyPressEvent`` above, so a shortcut here
        # would be a second, redundant binding whose only effect is to print
        # a hint beside the label. Both paths land on the same
        # ``_remove_current_parameter`` handler.
        self._remove_action = QAction("Remove parameter", self)
        self._remove_action.triggered.connect(self._remove_current_parameter)

        self._popup = AddParameterPopup(self)
        self._popup.custom_parameter_requested.connect(self._on_custom_parameter_requested)

    def set_visible_issue_severities(self, severities: dict[tuple[str, ...], str]) -> None:
        """Set the page-visible-issue parameter paths, mapped to severity.

        Call from ``_refresh_all`` before ``show_node``/``reveal`` render any
        rows -- stored, not applied immediately, since the panel is usually
        empty (``show_node(None)``) at refresh time and the real render
        happens later via a navigation ``reveal``. A stateless setter (like
        ``self._model``) rather than an extra ``show_node``/``reveal``
        parameter every caller must thread through.
        """
        self._visible_issue_severities = severities

    def set_comparison(self, pins: list[ReferencePin]) -> None:
        """Set the pinned-reference state and re-render whatever section is
        currently shown.

        Called by ``MainWindow`` -- the single place computing this state --
        on every document change and every pin/remove. Empty with nothing
        pinned or no document open.
        """
        self._pins = list(pins)
        self._strip.set_state(pins)
        if self._node is not None:
            self.show_node(self._node, self._model)

    def _rows_for(self, section_path: tuple[str, ...], key: str) -> list[RowDiff | None]:
        """One entry per pinned reference, in pin order: that reference's
        comparison for *key*, or ``None`` where it has nothing to say."""
        return [
            pin.comparison.row(section_path, key) if pin.comparison is not None else None
            for pin in self._pins
        ]

    def _sections_for(self, section_path: tuple[str, ...]) -> list:
        """One entry per pinned reference, in pin order: that reference's
        ``SectionDiff`` at *section_path*, or ``None``."""
        return [
            pin.comparison.section(section_path) if pin.comparison is not None else None
            for pin in self._pins
        ]

    def _reference_tooltip_lines(self, rows: list[RowDiff | None]) -> list[str]:
        """One "<names>: <value>" line per distinct reference value, in the
        order the values were first pinned.

        Names, not badge letters: a tooltip is plain text with no colour to
        carry, so the file's own name is the only identity that survives
        there.
        """
        lines = []
        for group in group_reference_values(rows):
            names = ", ".join(self._pins[index].name for index in group.indices)
            lines.append(f"{names}: {parameter_row.value_tooltip(group.value)}")
        return lines

    def set_read_only(self, read_only: bool) -> None:
        """Whether the session refuses edits. Takes effect on the next
        ``show_node`` -- ``MainWindow._refresh_all`` sets it before any row
        renders, so no stale affordance survives a session change."""
        self._read_only = read_only

    def show_node(self, node: TreeNode | None, model: str | None = None) -> None:
        self._node = node
        self._model = model
        self._add_button.setVisible(not self._read_only)
        self._add_button.setEnabled(node is not None and not self._read_only)
        self._list.clear()
        if node is None:
            # No section selected: hide the header entirely rather than show
            # an empty wash (there is nothing to title or count).
            self._header.hide()
            return
        self._header.show()
        self._header.set_title(node.label)
        # Same count the tree's own whole-document total aggregates per
        # section (``Document.parameter_count``: the sum, across every
        # section, of ``len(node.parameters)``) -- real rows only, not the
        # ghost rows or "fields to add" suggestions appended below.
        self._count_label.setText(str(len(node.parameters)))
        for parameter in node.parameters:
            severity = self._visible_issue_severities.get(parameter.path)
            is_empty = parameter.value is None
            item = QListWidgetItem(parameter.label)
            item.setData(256, parameter.path)
            item.setData(
                parameter_row.HTML_ROLE,
                parameter_row.build_parameter_row_html(
                    parameter.label, severity=severity, is_empty=is_empty
                ),
            )
            # Right-aligned value preview (raw-verbatim, delegate-elided);
            # the tooltip carries the full committed value so an elided
            # 20-decimal mantissa is still one hover away.
            preview, ghost = parameter_row.value_preview(parameter.value, parameter.kind)
            item.setData(parameter_row.VALUE_ROLE, preview)
            item.setData(parameter_row.VALUE_GHOST_ROLE, ghost)
            if not is_empty:
                item.setToolTip(parameter_row.value_tooltip(parameter.value))
            if self._pins:
                rows = self._rows_for(node.path, parameter.path[-1])
                state = merged_row_state(rows)
                variant = _ROW_BAR_VARIANTS.get(state) if state is not None else None
                if variant is not None:
                    item.setData(parameter_row.REF_BAR_ROLE, variant)
                if variant == "differs":
                    # The list says "differs"; the hover says from what, and
                    # with several pinned, which references say what. The main
                    # value's own tooltip line (set above) stays first.
                    existing = item.toolTip()
                    lines = ([existing] if existing else []) + self._reference_tooltip_lines(rows)
                    item.setToolTip("\n".join(lines))
            self._list.addItem(item)
        self._append_ghost_rows(node)
        if not self._read_only:
            # The group is one long invitation to add fields; a read-only
            # session offers no adds, so it is not appended at all.
            self._append_missing_fields_group(node, model)

    def _append_ghost_rows(self, node: TreeNode) -> None:
        """Append REF_ONLY ghost rows for this section, per the merge rule:
        synthetic, read-only rows for keys the reference has and the main
        document does not. Rendered via the same
        synthetic-row precedent as the "fields to add" group -- role 256
        stays ``None`` so removal/context-menu/Enter-to-activate all treat
        them as non-existent parameters (see :meth:`_activate_item`).

        The keys are the *union* across pinned references: a key only one
        reference carries is still something the main document lacks."""
        if not self._pins:
            return
        for key in merged_ghost_keys(self._sections_for(node.path)):
            self._list.addItem(self._make_ghost_item(node.path, key))

    def _make_ghost_item(self, section_path: tuple[str, ...], key: str) -> QListWidgetItem:
        rows = self._rows_for(section_path, key)
        groups = group_reference_values(rows)
        # The preview shows the first-pinned reference's value; the tooltip
        # spells out every distinct one, so a row summarising several
        # references never silently picks a winner without saying so.
        ref_value = groups[0].value if groups else None
        meta = field_meta(section_path + (key,))
        kind = classify(ref_value, meta)
        preview, _ghost = parameter_row.value_preview(ref_value, kind)
        item = QListWidgetItem(key)
        item.setData(256, None)
        item.setData(self._GROUP_ROW_KIND_ROLE, "ghost")
        item.setData(self._GHOST_KEY_ROLE, key)
        item.setData(parameter_row.HTML_ROLE, parameter_row.build_ghost_row_html(key))
        item.setData(parameter_row.VALUE_ROLE, preview)
        # Always italic, even for a plain scalar -- ghost rows read ghosted
        # end to end, unlike a real row's VALUE_GHOST_ROLE, which only
        # ghosts a null/derived-summary value.
        item.setData(parameter_row.VALUE_GHOST_ROLE, True)
        item.setData(parameter_row.REF_BAR_ROLE, "ref_only")
        item.setToolTip("\n".join(self._reference_tooltip_lines(rows)))
        return item

    def _append_missing_fields_group(self, node: TreeNode, model: str | None) -> None:
        """Append the "fields to add" group after the real rows.

        Purely derived at render time from :func:`core.completion.completion_for`
        -- never written into ``TreeNode.parameters``, so the tree/parameter
        model keeps meaning "what is in the document". Suppressed for an
        undeclared/garbage model (the sole completion task there is "declare
        a model", not a suggestion list against a model nobody picked) and
        whenever the section has no missing fields at all (no disabled
        placeholders, no "0 fields to add"). Header's own group is exempt
        from the model gate: Title/Model/BPX resolve identically regardless
        of model, so Header is collateral of a gate aimed at other sections,
        not a section this gate is meant to silence.

        The merge rule: a spec field the reference has renders as a ghost
        row *only* -- it is filtered out of this group even though it is
        still schema-missing from the main, so one key never shows as two
        rows.
        """
        if model not in _COMPLETION_GROUP_MODELS and node.path != ("Header",):
            return
        # A Validation run's ExperimentCard already renders every schema
        # column (required ones as typable columns, Temperature behind its
        # own "+"), so a "fields to add" group here would duplicate columns
        # already on screen -- and clicking its "+ Time [s]" wrote [] while
        # the card looked identical before and after.
        if is_validation_run_path(node.path):
            return
        missing = completion.completion_for(node.path, node.value, model).missing_fields
        if self._pins:
            ghost_keys = frozenset(merged_ghost_keys(self._sections_for(node.path)))
            missing = tuple(field for field in missing if field.alias not in ghost_keys)
        if not missing:
            return
        expanded = self._expanded.get(node.path, False)
        self._list.addItem(self._make_group_header_item(len(missing), expanded))
        if expanded:
            for field in missing:
                self._list.addItem(self._make_suggestion_item(field))

    def _make_group_header_item(self, count: int, expanded: bool) -> QListWidgetItem:
        arrow = "▾" if expanded else "▸"
        noun = "field" if count == 1 else "fields"
        item = QListWidgetItem(f"{arrow} {count} {noun} to add")
        item.setData(256, None)
        item.setData(self._GROUP_ROW_KIND_ROLE, "header")
        item.setForeground(QColor(style.MUTED))
        font = typography.semibold(self._list.font())
        item.setFont(font)
        return item

    def _make_suggestion_item(self, field: MissingField) -> QListWidgetItem:
        item = QListWidgetItem(f"+ {suggestion_row_text(field.alias, field.meta, field.required)}")
        item.setData(256, None)
        item.setData(self._GROUP_ROW_KIND_ROLE, "suggestion")
        item.setData(self._GROUP_ROW_ALIAS_ROLE, field.alias)
        item.setData(parameter_row.HTML_ROLE, _missing_field_html(field))
        return item

    def reveal_missing_alias(self, alias: str) -> bool:
        """Expand the "fields to add" group and select/scroll to *alias*'s
        suggestion row; return False if the current section has no such
        missing field (already added, suppressed model, or never expected).

        Unlike :meth:`reveal`, which only ever addresses a real row that
        already exists in the document, this addresses a field that isn't
        there yet -- what an Outstanding "Go to ›" action for a missing
        field calls.
        """
        if self._node is None:
            return False
        self._expanded[self._node.path] = True
        self.show_node(self._node, self._model)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if (
                item.data(self._GROUP_ROW_KIND_ROLE) == "suggestion"
                and item.data(self._GROUP_ROW_ALIAS_ROLE) == alias
            ):
                self._list.setCurrentRow(row)
                self._list.scrollToItem(item)
                return True
        return False

    def reset_expansion_state(self) -> None:
        """Forget every "fields to add" group's expansion, across every
        section path.

        Call only from a document-REPLACE path (open/new/drop) -- never from
        :meth:`show_node`/:meth:`reveal`/a same-document refresh, which must
        keep the survive-same-section-rebuild behaviour. Without this,
        opening a different document would inherit a previous
        document's expanded sections wherever their paths happen to collide
        (e.g. both have a "Cell"), and the dict would grow unboundedly across
        a session of many opens.
        """
        self._expanded.clear()

    def _toggle_missing_fields_group(self) -> None:
        if self._node is None:
            return
        path = self._node.path
        self._expanded[path] = not self._expanded.get(path, False)
        self.show_node(self._node, self._model)

    def reveal(
        self,
        node: TreeNode | None,
        parameter_path: tuple[str, ...] | None,
        model: str | None = None,
    ) -> None:
        """Show *node*'s parameters and select/scroll to *parameter_path*.

        This is the parameter list's part of a navigation reveal; it re-lists
        the target object's parameters and highlights the target row when the
        navigation is parameter-level. *model* is the document's declared
        model, needed (alongside the section path) to look up BPX-alias
        suggestions for the add-parameter popup.
        """
        self.show_node(node, model)
        if parameter_path is None:
            return
        target = tuple(parameter_path)
        for row in range(self._list.count()):
            item = self._list.item(row)
            if item.data(256) == target:
                self._list.setCurrentRow(row)
                self._list.scrollToItem(item)
                return

    def _on_clicked(self, item: QListWidgetItem) -> None:
        self._activate_item(item)

    def _on_activate_current(self) -> None:
        """Return/Enter on the current row: only a "fields to add" suggestion
        row acts on this (mirrors the add-parameter popup's Enter-to-activate).
        A real parameter row has no Enter behaviour, matching today's app --
        selection there is click-driven only."""
        item = self._list.currentItem()
        if item is None or item.data(self._GROUP_ROW_KIND_ROLE) != "suggestion":
            return
        self._activate_item(item)

    def _activate_item(self, item: QListWidgetItem) -> None:
        """Route one row's activation (click or Enter) by kind.

        A real row (role 256 carries its parameter path) selects it,
        unchanged. The group header toggles expansion. A suggestion row
        requests the add through ``add_parameter_requested`` -- the exact
        signal/path the add-parameter popup's own Suggested rows use, so both
        surfaces share one undo step and one reveal/focus behaviour. A ghost
        row is selectable but names no real document parameter, so it
        requests ``ghost_selected`` instead -- the Inspector shows its
        read-only ghost card, never the normal editing card.
        """
        kind = item.data(self._GROUP_ROW_KIND_ROLE)
        if kind == "header":
            self._toggle_missing_fields_group()
            return
        if kind == "suggestion":
            if self._node is not None and not self._read_only:
                alias = item.data(self._GROUP_ROW_ALIAS_ROLE)
                self.add_parameter_requested.emit(self._node.path, alias, None)
            return
        if kind == "ghost":
            if self._node is not None:
                self.ghost_selected.emit(self._node.path, item.data(self._GHOST_KEY_ROLE))
            return
        self.parameter_selected.emit(item.data(256))

    def _on_context_menu_requested(self, pos: QPoint) -> None:
        """Show the row menu for the real parameter under *pos*, or nothing.

        A right-click always acts on whatever row it lands on -- never a
        stale prior selection -- so the target row is made current first,
        which is also what visibly shows it as the menu's target. Empty
        space -- including an empty list, or no object/document loaded at
        all -- has no row under the cursor, so this opens no menu; a
        disabled menu is not shown either, matching the app's "no disabled
        placeholders" convention. A synthetic "fields to add" row (role 256
        is ``None``) is not an existing parameter either, so it offers no
        menu.
        """
        if self._read_only:
            return
        item = self._list.itemAt(pos)
        path = item.data(256) if item is not None else None
        if path is None:
            return
        self._list.setCurrentItem(item)
        menu = self._build_row_menu(path)
        menu.exec(self._list.mapToGlobal(pos))

    def _build_row_menu(self, path: tuple[str, ...]) -> QMenu:
        """The legal row actions for the real parameter at *path*, in the
        order the design specifies: Rename…/Duplicate (only where the
        backend allows -- ``core.structure``), a separator, Move up/down
        (always offered, disabled at the first/last real row), a separator,
        then the unchanged Remove parameter.
        """
        menu = QMenu(self)
        parameters = self._node.parameters if self._node is not None else ()
        parameter = next((p for p in parameters if p.path == path), None)
        value = parameter.value if parameter is not None else None
        if structure.can_rename_parameter(path, value):
            rename_action = menu.addAction("Rename…")
            rename_action.triggered.connect(
                lambda _checked=False, p=path: self.rename_parameter_requested.emit(p)
            )
        if structure.can_duplicate_parameter(path, value):
            duplicate_action = menu.addAction("Duplicate")
            duplicate_action.triggered.connect(
                lambda _checked=False, p=path: self.duplicate_parameter_requested.emit(p)
            )
        if not menu.isEmpty():
            menu.addSeparator()

        index = self._real_parameter_index(path)
        last_index = len(self._node.parameters) - 1 if self._node is not None else -1
        move_up = menu.addAction("Move up")
        move_up.setEnabled(index is not None and index > 0)
        move_up.triggered.connect(
            lambda _checked=False, p=path: self.move_parameter_requested.emit(p, "up")
        )
        move_down = menu.addAction("Move down")
        move_down.setEnabled(index is not None and index < last_index)
        move_down.triggered.connect(
            lambda _checked=False, p=path: self.move_parameter_requested.emit(p, "down")
        )

        menu.addSeparator()
        menu.addAction(self._remove_action)
        return menu

    def _real_parameter_index(self, path: tuple[str, ...]) -> int | None:
        """*path*'s position among ``self._node.parameters`` (real rows only,
        in the same order the list renders them), or ``None`` if not found."""
        if self._node is None:
            return None
        for index, parameter in enumerate(self._node.parameters):
            if parameter.path == path:
                return index
        return None

    def _remove_current_parameter(self) -> None:
        """Request removal of whichever row is current.

        The context menu action and the Delete-key accelerator both land
        here; a no-op when nothing is current (e.g. Delete pressed with an
        empty list) or the current row is a synthetic "fields to add" row
        (role 256 is ``None`` there -- it names no existing parameter to
        remove).
        """
        if self._read_only:
            return
        item = self._list.currentItem()
        if item is None:
            return
        path = item.data(256)
        if path is None:
            return
        self.remove_parameter_requested.emit(path)

    def _open_add_popup(self) -> None:
        if self._node is None:
            return
        existing = {parameter.label for parameter in self._node.parameters}
        self._popup.open_for_section(
            self._add_button,
            self._node.label,
            existing,
            self._node.path,
            self._model,
            self._node.value,
        )

    def _on_custom_parameter_requested(self, key: str, seed: object) -> None:
        if self._node is None:
            return
        self.add_parameter_requested.emit(self._node.path, key, seed)
