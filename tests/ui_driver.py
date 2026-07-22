"""Test-side UI driver: the single home for "how to drive the app" knowledge.

The workflow tests describe *what the user does and sees* in domain terms
(open a file, go to a parameter, edit the field, commit, read the validity
badge). This driver translates those intentions into concrete widget
interactions.

Design rules:
  - Tests never touch widgets directly; they only call driver methods.
  - The driver drives through the outermost surface available: the public
    ``MainWindow`` operations (``open_document``, ``navigate_to``), the panels'
    public signals, and real Qt events via ``qtbot``. Where it must reach a
    concrete widget (to type into the active card or read a visible label),
    that knowledge is confined to this file.
  - Readers return *user-visible* state (badge text, tab labels, list counts,
    window title) so assertions survive internal refactors.

If a UI refactor moves a widget or renames an attribute, only this driver
changes -- the workflow tests keep expressing the same behaviour.
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QSpinBox


def _find_tree_node(root, path: tuple[str, ...]):
    """Walk *root* (a ``TreeNode``) down to the child at *path*, or None."""
    if root is None:
        return None
    node = root
    for depth in range(1, len(path) + 1):
        target = path[:depth]
        node = next((child for child in node.children if child.path == target), None)
        if node is None:
            return None
    return node


class AppDriver:
    """Drives a live :class:`MainWindow` the way a user would."""

    def __init__(self, window, qtbot) -> None:
        self._w = window
        self._qtbot = qtbot

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def open(self, path: Path | str) -> "AppDriver":
        """Open a document by path (equivalent to File > Open)."""
        self._w.open_document(Path(path))
        return self

    def select_object(self, path: tuple[str, ...]) -> "AppDriver":
        """Click an object node in the structure tree."""
        self._w._tree.node_selected.emit(tuple(path))
        return self

    def select_parameter(self, path: tuple[str, ...]) -> "AppDriver":
        """Click a parameter in the parameter list."""
        self._w._params.parameter_selected.emit(tuple(path))
        return self

    def go_to(self, path: tuple[str, ...]) -> "AppDriver":
        """Navigate straight to a parameter (owning object + parameter)."""
        self._w.navigate_to(tuple(path))
        return self

    def edit_field(self, value) -> "AppDriver":
        """Type/set *value* into the active card's editor."""
        widget = self._editor_widget()
        if isinstance(widget, QLineEdit):
            widget.clear()
            self._qtbot.keyClicks(widget, str(value))
        elif isinstance(widget, QSpinBox):
            widget.setValue(int(value))
        elif isinstance(widget, QComboBox):
            index = widget.findText(str(value))
            if index >= 0:
                widget.setCurrentIndex(index)
            else:
                widget.setEditText(str(value))
        else:  # pragma: no cover - defensive
            raise AssertionError(f"No editable widget for the active card: {widget!r}")
        return self

    def commit(self) -> "AppDriver":
        """Press Enter to commit the current draft to the document."""
        self._qtbot.keyClick(self._editor_widget(), Qt.Key_Return)
        return self

    def escape(self) -> "AppDriver":
        """Press Escape to discard the current draft."""
        self._qtbot.keyClick(self._editor_widget(), Qt.Key_Escape)
        return self

    def wait_for_live_validation(self) -> "AppDriver":
        """Wait for the Inspector's debounce so live validation can settle."""
        self._qtbot.wait(260)  # slightly longer than the 200ms debounce
        return self

    def click_issues_tab(self) -> "AppDriver":
        """Click the Issues tab button in the secondary workspace."""
        button = self._w._inspector._secondary._buttons["issues"]
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    # -- Diagnostics page (rail redesign: strip + rail + detail pane) ---
    #
    # The default surface for driver reads that don't care which rail entry
    # is selected is the "All sections" view (``_all_view``) -- it is both
    # the default selection on a freshly opened document (matching most
    # existing call sites, which never touch the rail first) and the F3
    # backup view that always contains every issue/task row, so scanning it
    # preserves the old single-list driver semantics almost exactly.
    # ``_validation_rows``/``validation_issue_texts``/``outstanding_tasks``/
    # etc. below all read it. Rail- and section-pane-specific behaviour gets
    # its own ``diagnostics_*``-prefixed methods further down.

    def activate_first_validation_issue(self) -> "AppDriver":
        """Activate the first issue row in the All-sections view.

        Emits ``itemActivated`` -- the signal the panel actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the panel does
        not listen to.
        """
        items = self._validation_rows("issue")
        assert items, "No issue row in the Diagnostics list."
        self._w._diagnostics._all_view._list.itemActivated.emit(items[0])
        return self

    def activate_validation_row(self, item) -> "AppDriver":
        """Emit ``itemActivated`` for one already-located ``QListWidgetItem``
        from the All-sections view (e.g. from :meth:`_validation_rows`) --
        the low-level primitive :meth:`activate_first_validation_issue`/
        :meth:`activate_outstanding_task` build on."""
        self._w._diagnostics._all_view._list.itemActivated.emit(item)
        return self

    def activate_outstanding_task(self, task) -> "AppDriver":
        """Activate the Outstanding row for *task* (a ``CompletionTask``, as
        returned by :meth:`outstanding_tasks`) in the All-sections view."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("task"):
            if item.data(dp._TASK_ROLE) == task:
                self._w._diagnostics._all_view._list.itemActivated.emit(item)
                return self
        raise AssertionError(f"No Outstanding row for {task!r}")

    def outstanding_tasks(self) -> list:
        """Every ``CompletionTask`` currently rendered as an Outstanding row
        in the All-sections view, in on-screen order."""
        from ui_qt import diagnostics_panel as dp

        return [item.data(dp._TASK_ROLE) for item in self._validation_rows("task")]

    def outstanding_task_row_text(self, task) -> str:
        """Plain text of the Outstanding row for *task* -- includes any
        absorbed validator messages appended as secondary text (decision O)."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("task"):
            if item.data(dp._TASK_ROLE) == task:
                return item.text()
        raise AssertionError(f"No Outstanding row for {task!r}")

    def validation_group_headers(self) -> list[str]:
        """Text of every All-sections sub-head row, in order (e.g.
        "Cell - 2 of 5 remaining", "Separator - section absent",
        "Cell · optional - 1 unfilled") -- the pinned copy from S3."""
        return [item.text() for item in self._validation_rows("subhead")]

    def validation_task_row_count_under_header(self, header_text: str) -> int:
        """Number of "task" rows directly beneath the sub-head/fold-header
        row whose text is *header_text*, up to (not including) the next such
        row (decision R's ratio-integrity check: a required group's stated N
        must equal this count exactly, never an optional row sitting in
        between)."""
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._all_view._list
        start = None
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(dp._KIND_ROLE) in ("subhead", "fold_header") and item.text() == header_text:
                start = i
                break
        assert start is not None, f"No header row with text {header_text!r}."
        count = 0
        for i in range(start + 1, lst.count()):
            item = lst.item(i)
            kind = item.data(dp._KIND_ROLE)
            if kind in ("subhead", "fold_header"):
                break
            if kind == "task":
                count += 1
        return count

    def validation_issue_texts(self) -> list[str]:
        """Text of every issue row in the All-sections view, in order."""
        return [item.text() for item in self._validation_rows("issue")]

    def activate_validation_group_header(self, index: int = 0) -> "AppDriver":
        """Activate a sub-head row directly -- proves it is a structural
        no-op (decision L: only issue/task rows act)."""
        return self.activate_validation_row(self._validation_rows("subhead")[index])

    def activate_fold_header(self, index: int = 0) -> "AppDriver":
        """Activate (Enter/double-click) an All-sections fold-header row
        directly -- proves it is a structural no-op; folding is single-click
        only (:meth:`toggle_all_sections_fold`)."""
        return self.activate_validation_row(self._validation_rows("fold_header")[index])

    def all_sections_fold_headers(self) -> list[tuple[str, bool]]:
        """``(section_label, collapsed)`` for every All-sections fold
        header, in display order."""
        from ui_qt import diagnostics_panel as dp

        return [
            (item.data(dp._FOLD_BUCKET_ROLE).label, bool(item.data(dp._FOLD_COLLAPSED_ROLE)))
            for item in self._validation_rows("fold_header")
        ]

    def toggle_all_sections_fold(self, section_label: str) -> "AppDriver":
        """Fold/unfold the named bucket in the All-sections view, as a
        single click on its header does."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("fold_header"):
            if item.data(dp._FOLD_BUCKET_ROLE).label == section_label:
                self._w._diagnostics._all_view._on_clicked(item)
                return self
        raise AssertionError(f"No All-sections fold header for {section_label!r}.")

    def validation_task_texts(self) -> list[str]:
        """Text of every Outstanding task row in the All-sections view, in order."""
        return [item.text() for item in self._validation_rows("task")]

    def validation_issue_html(self) -> list[str]:
        """The painted HTML of every issue row in the All-sections view, in
        order -- lets a test assert the two-line location/message split
        without pixel-reading."""
        from ui_qt import parameter_row

        return [
            item.data(parameter_row.HTML_ROLE) for item in self._validation_rows("issue")
        ]

    def _validation_rows(self, kind: str) -> list:
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._all_view._list
        return [
            lst.item(i)
            for i in range(lst.count())
            if lst.item(i).data(dp._KIND_ROLE) == kind
        ]

    def activate_validation_issue(self, path: tuple[str, ...]) -> "AppDriver":
        """Emit the Diagnostics panel's own activation signal for *path*.

        Drives through the panel's public ``issue_activated`` signal directly
        (the same entry point a real double-click or Enter/Return uses
        internally, from either detail-pane view -- the panel forwards both
        unmodified), bypassing ``QListWidget``'s ``itemDoubleClicked`` --
        which is a distinct Qt signal from ``itemActivated`` and, unlike a
        genuine mouse event, does not trigger it when emitted manually.
        """
        self._w._diagnostics.issue_activated.emit(tuple(path))
        return self

    # -- Diagnostics rail --------------------------------------------------

    def diagnostics_strip_counts(self) -> tuple[int, int, int]:
        """``(errors, warnings, outstanding)`` -- the summary strip's own
        totals, straight from the ``PageBuckets`` the rail/pane also render
        from (F3's reconciliation invariant: these can never disagree)."""
        buckets = self._w._diagnostics._buckets
        if buckets is None:
            return (0, 0, 0)
        return (buckets.error_count, buckets.warning_count, buckets.outstanding_count)

    def diagnostics_rail_labels(self) -> list[str]:
        """Every rail entry's label, in display order ("All sections" first,
        then a separator -- omitted here -- then one per bucket)."""
        from ui_qt import diagnostics_panel as dp

        rail = self._w._diagnostics._rail
        return [
            rail.item(i).text()
            for i in range(rail.count())
            if rail.item(i).data(dp._RAIL_KIND_ROLE) in ("all", "section")
        ]

    def diagnostics_rail_absent(self, label: str) -> bool:
        """True when rail entry *label* renders italic (an absent section)."""
        from ui_qt import diagnostics_panel as dp

        return bool(self._diagnostics_rail_item(label).data(dp._RAIL_ABSENT_ROLE))

    def diagnostics_rail_has_badge(self, label: str) -> bool:
        """True when rail entry *label* carries at least one painted count
        badge (F4: a clean bucket carries none at all)."""
        from ui_qt import diagnostics_panel as dp

        return bool(self._diagnostics_rail_item(label).data(dp._RAIL_BADGE_ROLE))

    def diagnostics_bucket(self, label: str):
        """The ``SectionBucket`` currently backing rail entry *label* --
        ``None`` for "All sections" (which has no single bucket) or an
        unknown label."""
        buckets = self._w._diagnostics._buckets
        if buckets is None or label == "All sections":
            return None
        return next((b for b in buckets.buckets if b.label == label), None)

    def diagnostics_select_rail(self, label: str) -> "AppDriver":
        """Select rail entry *label*, as a click would -- switches the pane
        immediately via the rail's own ``selection_changed`` signal."""
        self._w._diagnostics._rail.setCurrentItem(self._diagnostics_rail_item(label))
        return self

    def diagnostics_selected_rail_label(self) -> str | None:
        item = self._w._diagnostics._rail.currentItem()
        return item.text() if item is not None else None

    def diagnostics_rail_press_down(self) -> "AppDriver":
        """Give the rail keyboard focus and press Down -- proves arrow keys
        move rail selection (and so switch the pane) without a click."""
        rail = self._w._diagnostics._rail
        rail.setFocus()
        self._qtbot.keyClick(rail, Qt.Key_Down)
        return self

    def _diagnostics_rail_item(self, label: str):
        rail = self._w._diagnostics._rail
        for i in range(rail.count()):
            item = rail.item(i)
            if item.text() == label:
                return item
        raise AssertionError(f"No rail entry named {label!r}.")

    # -- Diagnostics detail pane ------------------------------------------

    def diagnostics_pane_mode(self) -> str:
        """"section" or "all" -- which detail-pane view is currently showing."""
        panel = self._w._diagnostics
        return "section" if panel._pane_stack.currentWidget() is panel._section_view else "all"

    def diagnostics_section_header_text(self) -> str:
        """The selected section pane's own header label (rich text; callers
        match on substrings)."""
        return self._w._diagnostics._section_view._header.text()

    def diagnostics_section_issue_texts(self) -> list[str]:
        return [
            item.text()
            for item in self._diagnostics_kind_rows(
                self._w._diagnostics._section_view._issues_box.list, "issue"
            )
        ]

    def diagnostics_section_issues_badge_texts(self) -> list[str]:
        """Text of every badge currently shown in the selected section's
        Issues box header, left to right (0, 1 or 2: red error / amber
        warning -- :func:`ui_qt.diagnostics_panel._issue_badge_specs`)."""
        layout = self._w._diagnostics._section_view._issues_box._badge_layout
        return [layout.itemAt(i).widget().text() for i in range(layout.count())]

    def diagnostics_section_outstanding_title(self) -> str:
        return self._w._diagnostics._section_view._outstanding_box._title_label.text()

    def diagnostics_section_task_texts(self) -> list[str]:
        return [
            item.text()
            for item in self._diagnostics_kind_rows(
                self._w._diagnostics._section_view._outstanding_box.list, "task"
            )
        ]

    def diagnostics_section_optional_subhead_texts(self) -> list[str]:
        return [
            item.text()
            for item in self._diagnostics_kind_rows(
                self._w._diagnostics._section_view._outstanding_box.list, "subhead"
            )
        ]

    def diagnostics_section_issues_empty_text(self) -> str | None:
        """Pinned empty-state text of the selected section's Issues box
        (e.g. "✓ No issues"), or None if it holds real rows."""
        return self._first_message_text(self._w._diagnostics._section_view._issues_box.list)

    def diagnostics_section_outstanding_empty_text(self) -> str | None:
        """Pinned empty-state text of the selected section's Outstanding box
        (e.g. "✓ Nothing outstanding"), or None if it holds real rows."""
        return self._first_message_text(self._w._diagnostics._section_view._outstanding_box.list)

    # -- Diagnostics filters (F8) ------------------------------------------

    def diagnostics_chip_is_on(self, name: str) -> bool:
        """*name* is "errors"/"warnings"/"outstanding"."""
        return self._diagnostics_chip(name).is_on()

    def diagnostics_toggle_chip(self, name: str) -> "AppDriver":
        """Click the named strip chip, as a real mouse click would (F8)."""
        self._qtbot.mouseClick(self._diagnostics_chip(name), Qt.LeftButton)
        return self

    def _diagnostics_chip(self, name: str):
        strip = self._w._diagnostics._strip
        return {"errors": strip._errors, "warnings": strip._warnings, "outstanding": strip._outstanding}[name]

    def diagnostics_section_hidden_line_text(self) -> str | None:
        """The selected section pane's own "N hidden by filters" line, or
        None if nothing is hidden there. Reads ``isHidden()`` rather than
        ``isVisible()`` -- the latter also depends on the top-level window
        actually being shown (which headless tests never do), while
        ``isHidden()`` reflects only this label's own ``setVisible`` call."""
        label = self._w._diagnostics._section_view._hidden_label
        return label.text() if not label.isHidden() else None

    def diagnostics_all_sections_hidden_line_text(self) -> str | None:
        """The All-sections view's own "N hidden by filters" line (its last
        row, when present), or None if nothing is hidden there."""
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._all_view._list
        if lst.count() == 0:
            return None
        last = lst.item(lst.count() - 1)
        if last.data(dp._KIND_ROLE) == "message" and "hidden by filters" in last.text():
            return last.text()
        return None

    def _first_message_text(self, list_widget) -> str | None:
        from ui_qt import diagnostics_panel as dp

        if list_widget.count() == 1 and list_widget.item(0).data(dp._KIND_ROLE) == "message":
            return list_widget.item(0).text()
        return None

    def _diagnostics_kind_rows(self, list_widget, kind: str) -> list:
        from ui_qt import diagnostics_panel as dp

        return [
            list_widget.item(i)
            for i in range(list_widget.count())
            if list_widget.item(i).data(dp._KIND_ROLE) == kind
        ]

    def fields_to_add_current_alias(self) -> str | None:
        """The alias of the parameter list's currently-selected "fields to
        add" suggestion row, or None if the current row isn't one (used to
        assert a MISSING_FIELD Outstanding activation landed on the right
        synthetic row via ``reveal_missing_alias``)."""
        panel = self._w._params
        item = panel._list.currentItem()
        if item is None or item.data(panel._GROUP_ROW_KIND_ROLE) != "suggestion":
            return None
        return item.data(panel._GROUP_ROW_ALIAS_ROLE)

    def validation_issues_empty_text(self) -> str | None:
        """Pinned empty-state text of the currently selected SECTION pane's
        Issues box (e.g. "✓ No issues"), or None if it holds real rows, or
        the All-sections view is showing -- that view is the quiet F3 backup
        (no pinned empty-state copy of its own; see
        :meth:`diagnostics_section_issues_empty_text` for the direct form of
        this same read)."""
        panel = self._w._diagnostics
        if panel._pane_stack.currentWidget() is not panel._section_view:
            return None
        return self.diagnostics_section_issues_empty_text()

    def validation_outstanding_empty_text(self) -> str | None:
        """Pinned empty-state text of the currently selected SECTION pane's
        Outstanding box (e.g. "✓ Nothing outstanding"), or None if it holds
        real rows or the All-sections view is showing."""
        panel = self._w._diagnostics
        if panel._pane_stack.currentWidget() is not panel._section_view:
            return None
        return self.diagnostics_section_outstanding_empty_text()

    def activate_first_parameter_issue(self) -> "AppDriver":
        """Activate the first issue in the Inspector's Issues tab.

        Emits ``itemActivated`` -- the signal the tab actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the tab does
        not listen to.
        """
        lst = self._w._inspector._issues_tab._list
        lst.itemActivated.emit(lst.item(0))
        return self

    def choose_search_result(self, path: tuple[str, ...]) -> "AppDriver":
        """Type a query, then pick the matching result from the SearchPopup."""
        from PySide6.QtCore import Qt

        search = self._w._search
        search.setFocus()
        search.clear()
        self._qtbot.keyClicks(search, path[-1])
        popup = search._popup
        for row in range(popup.count()):
            if popup.item(row).data(Qt.UserRole) == tuple(path):
                popup.setCurrentRow(row)
                popup.itemClicked.emit(popup.item(row))
                return self
        raise AssertionError(f"No search result for {path!r}")

    def show_view(self, name: str) -> "AppDriver":
        """Switch the workspace via the activity bar ("Workspace"/"Editor"/
        "Source"/"Diagnostics")."""
        index = {"Editor": 0, "Diagnostics": 1, "Workspace": 2, "Source": 3}[name]
        self._w._activity_bar.view_requested.emit(index)
        return self

    def current_view_name(self) -> str:
        """Label of the rail entry for whichever stack page is current."""
        return self._w._activity_bar.label_for(self._w._stack.currentIndex())

    # -- Source page (multi-file track M5) --------------------------------

    def source_rail_enabled(self) -> bool:
        """Whether the Source rail entry is currently clickable (gated on an
        open document, decision 13)."""
        return self._w._btn_source.isEnabled()

    def source_line_texts(self) -> list[str]:
        """Plain text of every line the Source view currently renders, top
        to bottom (folded-away content is genuinely absent)."""
        return self._w._source._view.line_texts()

    def source_toggle_fold(self, path: tuple[str, ...]) -> "AppDriver":
        """Fold/unfold the Source-view section or table at *path*, as a
        click on its caret line does."""
        self._w._source._view.toggle_fold(tuple(path))
        return self

    def source_ref_line_texts(self) -> list[str]:
        """Reference-pane counterpart of :meth:`source_line_texts`; empty
        while no reference is docked. Gap blocks read as empty strings, at
        the same indices as the main pane's lines."""
        return self._w._source._view.ref_line_texts()

    def source_chipped_texts(self) -> list[tuple[int, str, str]]:
        """Every value-chip highlight as (line index, "main"/"ref", text);
        empty with no reference docked (chips are a two-pane signal)."""
        return self._w._source._view.chipped_texts()

    def source_pane_headers(self) -> tuple[str, str] | None:
        """The two pane-header labels ("Main · …", "◇ Reference · …"), or
        ``None`` while the header row is hidden (no reference docked)."""
        page = self._w._source
        if page._pane_head.isHidden():
            return None
        return (page._main_head.text(), page._ref_head.text())

    def source_hint_visible(self) -> bool:
        """Whether the "Open a reference to compare…" toolbar hint is shown.
        ``isHidden()``, not ``isVisible()`` -- the window is never shown in
        the headless suite (known Qt pitfall)."""
        return not self._w._source._hint.isHidden()

    def source_has_input_widget(self) -> bool:
        """The Source page's no-edit invariant (coexistence rule 14): true
        if any input widget exists anywhere on the page."""
        from PySide6.QtWidgets import (
            QAbstractSpinBox,
            QComboBox,
            QPlainTextEdit,
            QTextEdit,
        )

        page = self._w._source
        return bool(
            page.findChildren(QLineEdit)
            or page.findChildren(QComboBox)
            or page.findChildren(QAbstractSpinBox)
            or page.findChildren(QTextEdit)
            or page.findChildren(QPlainTextEdit)
        )

    def click_workspace_open(self) -> "AppDriver":
        """Click the Open File button on the Workspace page."""
        self._qtbot.mouseClick(self._w._workspace._open_button, Qt.LeftButton)
        return self

    def click_workspace_open_reference(self) -> "AppDriver":
        """Click the "Open File as Reference…" button on the Workspace page."""
        self._qtbot.mouseClick(self._w._workspace._open_reference_button, Qt.LeftButton)
        return self

    def click_reference_remove(self) -> "AppDriver":
        """Click the docked reference tile's Remove button."""
        self._qtbot.mouseClick(self._w._workspace._reference_remove_button, Qt.LeftButton)
        return self

    def click_reference_make_main(self) -> "AppDriver":
        """Click the docked reference tile's "Make main" button (M4)."""
        self._qtbot.mouseClick(self._w._workspace._reference_make_main_button, Qt.LeftButton)
        return self

    def reference_make_main_button_visible(self) -> bool:
        """Whether the reference card's "Make main" button is reachable --
        true only while the card itself is shown (the button is never
        hidden individually; it lives entirely inside the card, so this
        first checks the card's own hidden flag, same as
        :meth:`reference_tile_visible`)."""
        return self.reference_tile_visible() and not self._w._workspace._reference_make_main_button.isHidden()

    def reference_heading_visible(self) -> bool:
        return not self._w._workspace._reference_heading.isHidden()

    def reference_tile_visible(self) -> bool:
        return not self._w._workspace._reference_tile.isHidden()

    def reference_tile_text(self) -> str:
        """Text of the reference card, flattened -- tag/filename/validity
        pill/key-value lines, one per line (mirrors :meth:`workspace_info_text`)."""
        ws = self._w._workspace
        lines = [
            ws._reference_tag.text(),
            ws._reference_filename.text(),
            f"Validity: {ws._reference_badge.text()}",
        ]
        lines.extend(f"{key}: {ws._reference_fields[key].text()}" for key in ws._reference_fields)
        return "\n".join(lines)

    def toast_text(self) -> str | None:
        """The toast's current message, or None while it is hidden."""
        toast = self._w._toast
        return toast.text() if not toast.isHidden() else None

    # ------------------------------------------------------------------
    # Comparison (multi-file track M2): strip, row decoration, ghost rows,
    # tree marks, reference block, ghost card.
    # ------------------------------------------------------------------

    def comparison_strip_visible(self) -> bool:
        return not self._w._params._strip.isHidden()

    def comparison_strip_identity_text(self) -> str:
        return self._w._params._strip._identity.text()

    def comparison_strip_counts_text(self) -> str:
        return self._w._params._strip._counts.text()

    def parameter_row_tint(self, label: str) -> str | None:
        """The real parameter row starting with *label*'s own
        :data:`~ui_qt.parameter_row.TINT_ROLE` hex colour, or ``None`` if it
        carries none. This is the data the delegate actually paints from
        (see ``ParameterRowDelegate._paint_tint``) -- ``QListWidgetItem``'s
        own ``background()``/``setBackground`` is a dead read once a
        stylesheet styles ``::item`` (a real Qt/QSS gotcha; see
        ``test_parameter_row.py``'s pixel-level regression pin)."""
        from ui_qt import parameter_row

        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                return item.data(parameter_row.TINT_ROLE)
        raise AssertionError(f"No real parameter row starting with {label!r}.")

    def ghost_row_keys(self) -> list[str]:
        """Every REF_ONLY ghost row's key, in list order."""
        panel = self._w._params
        lst = panel._list
        return [
            lst.item(i).data(panel._GHOST_KEY_ROLE)
            for i in range(lst.count())
            if lst.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "ghost"
        ]

    def ghost_row_tint(self, key: str) -> str | None:
        from ui_qt import parameter_row

        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "ghost" and item.data(panel._GHOST_KEY_ROLE) == key:
                return item.data(parameter_row.TINT_ROLE)
        raise AssertionError(f"No ghost row for {key!r}.")

    def parameter_list_row_painted_colour(self, item_index: int, dx: int = 6, dy: int = 6) -> str:
        """The actual rendered pixel colour near the top-left of the row at
        *item_index* in the parameter list, real widths/window shown first.

        Proves the delegate genuinely painted a colour, not merely that an
        item carries data a headless read could misreport (see
        ``parameter_row_tint``/``ghost_row_tint`` and
        ``test_parameter_row.py``'s pixel-level regression pin)."""
        lst = self._w._params._list
        self._w.show()
        self._qtbot.waitExposed(lst)
        rect = lst.visualItemRect(lst.item(item_index))
        image = lst.viewport().grab().toImage()
        return image.pixelColor(rect.left() + dx, rect.top() + dy).name()

    def select_ghost_row(self, key: str) -> "AppDriver":
        """Click the ghost row for *key* -- the same ``itemClicked`` path a
        real click uses, made current first (as a real click also does)."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "ghost" and item.data(panel._GHOST_KEY_ROLE) == key:
                lst.setCurrentItem(item)
                lst.itemClicked.emit(item)
                return self
        raise AssertionError(f"No ghost row for {key!r}.")

    def right_click_ghost_row(self, key: str) -> "AppDriver":
        """Right-click the ghost row for *key*: proves it opens no menu
        (read-only everywhere)."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "ghost" and item.data(panel._GHOST_KEY_ROLE) == key:
                lst.setCurrentItem(item)
                pos = lst.visualItemRect(item).center()
                panel._on_context_menu_requested(pos)
                return self
        raise AssertionError(f"No ghost row for {key!r}.")

    def tree_node_display_text(self, path: tuple[str, ...]) -> str:
        """The tree's own painted DisplayRole text for the node at *path*
        (e.g. carries the "≠ N" mark, multi-file track M2)."""
        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        assert index.isValid(), f"No tree node at {path!r}"
        return model.data(index, Qt.DisplayRole)

    def tree_error_marked_sections(self) -> list[tuple[str, ...]]:
        """Paths of tree rows currently answering the error-dot query
        (page-visible errors only), walking every node in document order --
        including collapsed rollup marks, which real expansion state
        determines exactly as on screen."""
        from PySide6.QtCore import QModelIndex

        from ui_qt.parameter_row import SEVERITY_ROLE

        model = self._w._tree._view.model()
        marked: list[tuple[str, ...]] = []

        def walk(parent: QModelIndex) -> None:
            for row in range(model.rowCount(parent)):
                index = model.index(row, 0, parent)
                if model.data(index, SEVERITY_ROLE) == "error":
                    marked.append(model.node_at(index).path)
                walk(index)

        walk(QModelIndex())
        return marked

    def reference_block_visible(self) -> bool:
        """Whether the current card's reference row is currently shown --
        works for both ``ParameterCard`` and ``GhostParameterCard``, which
        share the same ``_reference_block`` attribute (the shared
        ``ReferenceValueBlock`` widget)."""
        card = self._w._inspector._card
        block = getattr(card, "_reference_block", None) if card is not None else None
        return block is not None and not block.isHidden()

    def main_file_heading_visible(self) -> bool:
        """Whether the current ``ParameterCard``'s "Main file" heading is
        shown -- only ever true while a reference is docked and its section
        is not collapsed by an expanded grid."""
        card = self._w._inspector._card
        heading = getattr(card, "_main_file_heading", None) if card is not None else None
        return heading is not None and not heading.isHidden()

    def main_file_heading_text(self) -> str:
        return self._w._inspector._card._main_file_heading.text()

    def reference_file_heading_text(self) -> str:
        return self._w._inspector._card._reference_block._heading.text()

    def reference_value_text(self) -> str:
        return self._w._inspector._card._reference_block._value.text()

    def reference_unit_text(self) -> str | None:
        """The reference row's unit label text, or ``None`` when this kind
        shows no unit (mirroring whether the main editable row shows one).
        ``isHidden()``, not ``isVisible()`` -- the latter also requires every
        ancestor up to a shown top-level window (known Qt pitfall)."""
        label = self._w._inspector._card._reference_block._unit_label
        return label.text() if not label.isHidden() else None

    def reference_block_is_same(self) -> bool:
        return bool(self._w._inspector._card._reference_block._value.property("same"))

    def copy_up_visible(self) -> bool:
        return not self._w._inspector._card._reference_block._copy_up.isHidden()

    def copy_up_enabled(self) -> bool:
        return self._w._inspector._card._reference_block._copy_up.isEnabled()

    def click_copy_up(self) -> "AppDriver":
        """Click the current card's "Copy up" button -- works for both
        ``ParameterCard`` and ``GhostParameterCard``."""
        self._w._inspector._card._reference_block._copy_up.click()
        return self

    def ghost_card_shown(self) -> bool:
        from ui_qt.cards.ghost_card import GhostParameterCard

        return isinstance(self._w._inspector._card, GhostParameterCard)

    def ghost_card_heading_text(self) -> str:
        return self._w._inspector._card._heading.text()

    def ghost_card_title_text(self) -> str:
        return self._w._inspector._card._title.text()

    def ghost_card_has_input_widget(self) -> bool:
        from PySide6.QtWidgets import QAbstractSpinBox, QComboBox

        card = self._w._inspector._card
        return bool(
            card.findChildren(QLineEdit)
            or card.findChildren(QComboBox)
            or card.findChildren(QAbstractSpinBox)
        )

    def drop_file_on_workspace(self, path: Path | str) -> "AppDriver":
        """Simulate the user dropping *path* onto the Workspace page.

        Dispatches a real ``QDropEvent`` straight to the panel, exercising
        its own extension filtering as well as MainWindow's discard-guard
        and open/error-handling wiring -- the same as a genuine OS-level
        drop. If *path* is not a supported BPX file, the panel ignores the
        event and nothing happens.
        """
        panel = self._w._workspace
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        panel.dropEvent(event)
        return self

    def open_add_parameter_popup(self) -> "AppDriver":
        """Click the Parameter list's "+ Add parameter" header button."""
        self._qtbot.mouseClick(self._w._params._add_button, Qt.LeftButton)
        return self

    def type_new_parameter_alias(self, text: str) -> "AppDriver":
        """Type *text* into the add-parameter popup's input."""
        popup = self._w._params._popup
        popup._input.clear()
        self._qtbot.keyClicks(popup._input, text)
        return self

    def activate_selected_add_parameter_row(self) -> "AppDriver":
        """Activate whichever row is currently highlighted in the
        add-parameter popup -- a BPX-alias suggestion (creates immediately)
        or the "Create custom parameter" footer, which instead expands the
        inline custom-parameter form in place (see
        :meth:`submit_custom_parameter_form`)."""
        self._w._params._popup._activate()
        return self

    def add_parameter_custom_form_visible(self) -> bool:
        """True once the "Create custom parameter" footer has expanded into
        its inline Name/Unit/type form."""
        return self._w._params._popup._form_visible

    def type_custom_parameter_name(self, text: str) -> "AppDriver":
        """Replace the inline custom-parameter form's Name field."""
        popup = self._w._params._popup
        popup._form_name.clear()
        self._qtbot.keyClicks(popup._form_name, text)
        return self

    def type_custom_parameter_unit(self, text: str) -> "AppDriver":
        """Replace the inline custom-parameter form's (optional) Unit field."""
        popup = self._w._params._popup
        popup._form_unit.clear()
        self._qtbot.keyClicks(popup._form_unit, text)
        return self

    def select_custom_parameter_type(self, label: str) -> "AppDriver":
        """Click one of the inline form's five type buttons (e.g. "Scalar",
        "Table")."""
        from ui_qt.add_parameter_popup import _CUSTOM_TYPE_LABELS

        popup = self._w._params._popup
        button = popup._form_type_strip._buttons[_CUSTOM_TYPE_LABELS.index(label)]
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def custom_parameter_add_enabled(self) -> bool:
        return self._w._params._popup._form_add.isEnabled()

    def custom_parameter_scalar_warning_visible(self) -> bool:
        return self._w._params._popup._form_warning.isVisible()

    def submit_custom_parameter_form(self) -> "AppDriver":
        """Click "Add" on the inline custom-parameter form, committing the
        composed key and the selected type's seed value."""
        self._qtbot.mouseClick(self._w._params._popup._form_add, Qt.LeftButton)
        return self

    def cancel_custom_parameter_form(self) -> "AppDriver":
        """Click "Cancel" on the inline custom-parameter form, collapsing it
        back to the plain pinned footer without creating anything."""
        self._qtbot.mouseClick(self._w._params._popup._form_cancel, Qt.LeftButton)
        return self

    def right_click_parameter_row(self, index: int) -> "AppDriver":
        """Right-click the parameter row at *index*: select it and open its
        context menu.

        Emits the list's own ``customContextMenuRequested`` at the row's
        on-screen position -- the same entry point a real right-click
        delivers. ``QMenu.exec()`` is a genuinely blocking native call (a
        Python-level monkeypatch of it does not intercept the underlying
        C++ modal loop), so a zero-delay timer closes the menu the instant
        its event loop starts, letting ``exec()`` return immediately -- the
        standard Qt-test idiom for driving a blocking popup without a real
        user dismissing it.
        """
        from PySide6.QtCore import QTimer
        from PySide6.QtWidgets import QApplication

        def _close_open_popup() -> None:
            popup = QApplication.instance().activePopupWidget()
            if popup is not None:
                popup.close()

        panel = self._w._params
        item = panel._list.item(index)
        assert item is not None, f"No parameter row at index {index}"
        pos = panel._list.visualItemRect(item).center()
        QTimer.singleShot(0, _close_open_popup)
        panel._list.customContextMenuRequested.emit(pos)
        return self

    def fields_to_add_header_text(self) -> str | None:
        """Text of the parameter list's "fields to add" group header row
        (e.g. "▸ 2 fields to add"), or None if the group isn't shown at all
        (no missing fields, or the model doesn't qualify -- decision C)."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "header":
                return item.text()
        return None

    def toggle_fields_to_add_group(self) -> "AppDriver":
        """Click the "fields to add" group's header row."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "header":
                lst.itemClicked.emit(item)
                return self
        raise AssertionError("No fields-to-add group header is currently shown.")

    def fields_to_add_suggestion_aliases(self) -> list[str]:
        """The aliases currently listed under the (expanded) "fields to add"
        group, in list order."""
        panel = self._w._params
        lst = panel._list
        return [
            lst.item(i).data(panel._GROUP_ROW_ALIAS_ROLE)
            for i in range(lst.count())
            if lst.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
        ]

    def click_fields_to_add_suggestion(self, alias: str) -> "AppDriver":
        """Click one "fields to add" suggestion row -- the same
        ``add_parameter_requested`` path the add-parameter popup's own
        Suggested rows use."""
        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if (
                item.data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
                and item.data(panel._GROUP_ROW_ALIAS_ROLE) == alias
            ):
                lst.itemClicked.emit(item)
                return self
        raise AssertionError(f"No fields-to-add suggestion row for {alias!r}.")

    def activate_remove_parameter_action(self) -> "AppDriver":
        """Activate the parameter list's "Remove parameter" context-menu
        action -- the equivalent of clicking it while the menu is showing."""
        self._w._params._remove_action.trigger()
        return self

    def press_delete_in_parameter_list(self) -> "AppDriver":
        """Press the Delete key with the parameter list focused -- the
        row-removal accelerator."""
        self._qtbot.keyClick(self._w._params._list, Qt.Key_Delete)
        return self

    # -- Parameter-list row menu: Rename…/Duplicate/Move up/down ---------
    #
    # Built directly via ``ParameterListPanel._build_row_menu`` rather than
    # a real right-click -- the same "inspect without exec'ing" convention
    # ``tests/test_tree_editing.py`` uses for the tree's own structure menu
    # (``TreePanel._build_menu``), avoiding ``QMenu.exec()``'s blocking
    # native modal loop entirely.

    def _parameter_row_path(self, index: int) -> tuple[str, ...]:
        panel = self._w._params
        item = panel._list.item(index)
        assert item is not None, f"No parameter row at index {index}"
        path = item.data(256)
        assert path is not None, f"Row {index} is not a real parameter row"
        return path

    def parameter_row_menu_actions(self, index: int) -> list:
        """The row's context-menu actions, in order (separators included)."""
        panel = self._w._params
        return panel._build_row_menu(self._parameter_row_path(index)).actions()

    def parameter_row_menu_labels(self, index: int) -> list[str]:
        """Visible action labels for the row's context menu, in order
        (separators excluded -- their own text is always empty)."""
        return [a.text() for a in self.parameter_row_menu_actions(index) if not a.isSeparator()]

    def parameter_row_menu_action_enabled(self, index: int, label: str) -> bool:
        for action in self.parameter_row_menu_actions(index):
            if action.text() == label:
                return action.isEnabled()
        raise AssertionError(f"No {label!r} action on row {index}'s context menu.")

    def trigger_parameter_row_menu_action(self, index: int, label: str) -> "AppDriver":
        """Trigger one named action from the row's freshly built context menu."""
        for action in self.parameter_row_menu_actions(index):
            if action.text() == label:
                action.trigger()
                return self
        raise AssertionError(f"No {label!r} action on row {index}'s context menu.")

    # -- Card-header inline rename editor (Concept A pencil) --------------

    def card_rename_pencil_present(self) -> bool:
        """True when the active card offers the "✎" rename button."""
        card = self._w._inspector._card
        return card is not None and getattr(card, "_rename_button", None) is not None

    def click_card_rename_pencil(self) -> "AppDriver":
        card = self._w._inspector._card
        assert card is not None and card._rename_button is not None, (
            "Active card has no rename pencil."
        )
        self._qtbot.mouseClick(card._rename_button, Qt.LeftButton)
        return self

    def card_rename_row_visible(self) -> bool:
        """True once the rename row has been shown.

        Reads ``isHidden()``, not ``isVisible()`` -- the window is never
        shown in this suite, so ``isVisible()`` would read False regardless
        of the row's own hidden flag (the same reasoning as
        ``diagnostics_section_hidden_line_text``)."""
        card = self._w._inspector._card
        row = getattr(card, "_rename_row", None) if card is not None else None
        return row is not None and not row.isHidden()

    def card_rename_name_text(self) -> str:
        return self._w._inspector._card._rename_name.text()

    def card_rename_unit_text(self) -> str:
        return self._w._inspector._card._rename_unit.text()

    def type_card_rename_name(self, text: str) -> "AppDriver":
        card = self._w._inspector._card
        card._rename_name.clear()
        self._qtbot.keyClicks(card._rename_name, text)
        return self

    def type_card_rename_unit(self, text: str) -> "AppDriver":
        card = self._w._inspector._card
        card._rename_unit.clear()
        self._qtbot.keyClicks(card._rename_unit, text)
        return self

    def click_card_rename_apply(self) -> "AppDriver":
        card = self._w._inspector._card
        self._qtbot.mouseClick(card._rename_apply, Qt.LeftButton)
        return self

    def click_card_rename_cancel(self) -> "AppDriver":
        card = self._w._inspector._card
        self._qtbot.mouseClick(card._rename_cancel, Qt.LeftButton)
        return self

    def card_rename_error_text(self) -> str | None:
        """Visible inline rename-error text, or None if none is shown.

        Reads ``isHidden()``, not ``isVisible()`` -- see
        :meth:`card_rename_row_visible`."""
        card = self._w._inspector._card
        if card is None or getattr(card, "_rename_row", None) is None:
            return None
        return card._rename_error.text() if not card._rename_error.isHidden() else None

    def card_unit_tooltip(self) -> str | None:
        """The active card's own unit label tooltip, or None (no unit shown,
        or no tooltip set -- a renamable/custom parameter's unit)."""
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        label = getattr(card._editor, "_unit_label", None)
        if label is None:
            # A ModalCard's unit label lives on its active mode body.
            body = getattr(card._editor, "_body", None)
            label = getattr(body, "_unit_label", None)
        return label.toolTip() if label is not None else None

    def undo(self) -> "AppDriver":
        """Click the toolbar's Undo button: a document command.

        ``QAction.trigger()`` is ignored by a disabled action exactly as a
        click on it would be, so this faithfully reproduces "Undo is currently
        unavailable" too. It does bypass one thing a real mouse click meets
        first: an open popup's ``OutsideDismissFilter`` swallows the click that
        dismisses it, so in the running app a click with the search popup open
        closes the popup and a second click reaches Undo. That is the app's
        dismissal convention (shared by Save and Export), tested in
        ``test_dismissal.py``, and orthogonal to what Undo does.
        """
        self._w._undo_action.trigger()
        return self

    def press_undo_shortcut(self) -> "AppDriver":
        """Press ``Ctrl+Z``: focus-aware undo (see ``MainWindow._undo``).

        Emits the real ``QShortcut``'s ``activated`` signal rather than a
        ``Ctrl+Z`` key event, because ``QTest`` delivers key events straight to
        the target widget and never consults the window's shortcut map -- so a
        synthesised key press would silently exercise nothing.
        """
        self._w._undo_shortcut.activated.emit()
        return self

    def redo(self) -> "AppDriver":
        """Click the toolbar's Redo button: a document command.

        Mirrors ``undo()`` -- see its docstring for why a disabled action and
        an open popup are handled the way they are.
        """
        self._w._redo_action.trigger()
        return self

    def press_redo_shortcut(self) -> "AppDriver":
        """Press ``Ctrl+Y``: focus-aware redo (see ``MainWindow._redo``).

        Emits the real ``QShortcut``'s ``activated`` signal -- see
        ``press_undo_shortcut`` for why a synthesised key press would not do.
        """
        self._w._redo_shortcut.activated.emit()
        return self

    def press_redo_shortcut_alt(self) -> "AppDriver":
        """Press ``Ctrl+Shift+Z``: the alternate focus-aware redo shortcut."""
        self._w._redo_shortcut_alt.activated.emit()
        return self

    def focus_search(self) -> "AppDriver":
        """Give the top-bar search box keyboard focus within the window."""
        self._focus(self._w._search)
        return self

    def type_in_search(self, text: str) -> "AppDriver":
        self._qtbot.keyClicks(self._w._search, str(text))
        return self

    def search_text(self) -> str:
        return self._w._search.text()

    def _focus(self, widget) -> None:
        """Give *widget* keyboard focus within the window.

        The window must be shown first: ``setFocus`` on a hidden widget only
        propagates as far as its first non-hidden ancestor, so a toolbar widget
        in an unshown window never becomes the window's focus widget. That is
        real Qt behaviour, not a test artefact -- a hidden widget cannot hold
        the keyboard.
        """
        self._w.show()
        widget.setFocus()
        assert self._w.focusWidget() is widget, f"{widget!r} did not take focus"

    def focus_field(self) -> "AppDriver":
        """Give the active card's editor keyboard focus within the window."""
        self._focus(self._editor_widget())
        return self

    def type_in_field(self, text: str) -> "AppDriver":
        """Type into the active card's editor without clearing it first, so the
        widget accumulates its own undo history."""
        self._qtbot.keyClicks(self._editor_widget(), str(text))
        return self

    def field_text(self) -> str:
        """The raw text currently shown in the active card's editor."""
        widget = self._editor_widget()
        assert isinstance(widget, QLineEdit), f"{type(widget).__name__} has no text()"
        return widget.text()

    def click_workspace_new(self, model: str) -> "AppDriver":
        """Click the New button for *model* on the Workspace page's inline chooser."""
        button = self._w._workspace.findChild(QPushButton, f"NewButton_{model}")
        assert button is not None, f"No New button for model {model!r}"
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def workspace_new_model_options(self) -> list[str]:
        """The model names currently offered as buttons by the inline New chooser."""
        prefix = "NewButton_"
        return [
            button.objectName()[len(prefix):]
            for button in self._w._workspace.findChildren(QPushButton)
            if button.objectName().startswith(prefix)
        ]

    # ------------------------------------------------------------------
    # Readers -- user-visible state only
    # ------------------------------------------------------------------

    def has_document(self) -> bool:
        return self._w.windowTitle() != "ExploreBPX"

    def window_title(self) -> str:
        return self._w.windowTitle()

    def status_text(self) -> str:
        return self._w._status_label.text()

    def identity_text(self) -> str:
        """Full (untruncated) top-bar identity string.

        Reads the label's tooltip rather than its rendered ``text()``: the
        label elides its visible text to the widget's current width, which is
        unreliable off-screen, but the tooltip always holds the full string.
        """
        return self._w._identity_label.toolTip()

    def save_enabled(self) -> bool:
        return self._w._save_action.isEnabled()

    def export_enabled(self) -> bool:
        return self._w._export_action.isEnabled()

    def undo_enabled(self) -> bool:
        return self._w._undo_action.isEnabled()

    def undo_shortcut(self) -> str:
        return self._w._undo_shortcut.key().toString()

    def redo_enabled(self) -> bool:
        return self._w._redo_action.isEnabled()

    def redo_shortcut(self) -> str:
        return self._w._redo_shortcut.key().toString()

    def inspector_title(self) -> str:
        return self._w._inspector._card._title.text()

    def validity(self) -> str:
        """The Inspector validity badge: '', 'Valid', 'Warning' or 'Invalid'."""
        return self._w._inspector._card._badge.text()

    def field_value(self):
        return self._w._inspector._card.value()

    def card_is_editable(self) -> bool:
        card = self._w._inspector._card
        return card is not None and card.is_editable

    def card_is_dirty(self) -> bool:
        """True when the active card holds an uncommitted draft."""
        card = self._w._inspector._card
        return card is not None and card.is_dirty

    def shown_parameter_path(self) -> tuple[str, ...] | None:
        """Path of the parameter the Inspector is currently showing."""
        card = self._w._inspector._card
        return tuple(card.parameter.path) if card is not None else None

    def showing_placeholder(self) -> bool:
        """True when the Inspector shows its 'select an object' placeholder."""
        return self._w._inspector._card is None

    def parameter_labels(self) -> list[str]:
        lst = self._w._params._list
        return [lst.item(i).text() for i in range(lst.count())]

    def parameter_row_is_grey(self, label: str) -> bool:
        """True when the real parameter row starting with *label*'s rich-text
        (decision P: a committed-null value renders grey/muted) colours its
        *name* span (the first, bold one) with the muted colour rather than
        the normal one. Checking only the leading span matters: the unit
        suffix is always muted regardless (``build_parameter_row_html``), so
        a naive "is MUTED anywhere in the html" check is always true for any
        row with a unit. Real rows only -- matched by role-256 path presence.
        """
        from ui_qt import parameter_row, style

        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                html = item.data(parameter_row.HTML_ROLE)
                assert html is not None, f"Row {label!r} carries no rich-text data."
                name_span_prefix = f'<span style="font-weight:600; color:{style.MUTED};">'
                return html.startswith(name_span_prefix)
        raise AssertionError(f"No real parameter row starting with {label!r}.")

    def parameter_row_has_warning_marker(self, label: str) -> bool:
        """True when the real parameter row starting with *label* shows its
        severity dot (decision P: page-visible issues only, not validator-
        verbatim). The row's own ``text()`` carries only the label now (the
        marker is a painted ``<img>`` in :data:`~ui_qt.parameter_row.HTML_ROLE`,
        unified symbol system Concept A), so this checks the HTML for either
        severity colour's dot rather than a plain-text glyph."""
        from ui_qt import icons, parameter_row, style

        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                html = item.data(parameter_row.HTML_ROLE) or ""
                error_dot = icons.html_img(icons.DOT, color=style.ERROR, size=parameter_row.MARK_BOX)
                warning_dot = icons.html_img(icons.DOT, color=style.WARNING, size=parameter_row.MARK_BOX)
                return error_dot in html or warning_dot in html
        raise AssertionError(f"No real parameter row starting with {label!r}.")

    def add_parameter_button_enabled(self) -> bool:
        return self._w._params._add_button.isEnabled()

    def add_parameter_row_count(self) -> int:
        """Number of rows currently shown in the add-parameter popup's list,
        including group headers. The custom-add fallback is a pinned footer,
        not a list row -- see :meth:`add_parameter_can_create_custom`."""
        return self._w._params._popup._list.count()

    def add_parameter_can_create_custom(self) -> bool:
        """True when the popup's pinned "Create custom parameter" footer is
        offered for the currently typed text."""
        return self._w._params._popup._footer_shown

    def add_parameter_alias_texts(self) -> list[str]:
        """The visible text of every real (non-header) parameter row currently
        listed in the add-parameter popup."""
        popup = self._w._params._popup
        lst = popup._list
        return [
            lst.item(i).text()
            for i in range(lst.count())
            if lst.item(i).data(popup._TIER_ROLE) != "header"
        ]

    def editor_kind(self) -> str:
        """Class name of the active card's per-kind editor (e.g.
        'ScalarCard', 'RawCard'), so tests can assert a known BPX alias opens
        its proper metadata-driven editor rather than the raw fallback."""
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        return type(card._editor).__name__

    def issues_tab_label(self) -> str:
        return self._w._inspector._secondary._buttons["issues"].text()

    def issues_tab_badge_count(self) -> int:
        """The secondary Issues tab's badge NUMBER, parsed from its button
        text (e.g. 'Issues (1)' -> 1; 'Issues' with no suffix -> 0).

        Deliberately distinct from :meth:`issues_tab_count` (which reads the
        tab's own row *list*) -- the two are set by different code paths
        (``SecondaryWorkspace.set_count`` vs ``IssuesTab.show_parameter``'s
        row-building) and must always agree. M1 (reviewed defect): two
        Inspector call-sites (``_validate_draft``, ``_on_reset``) used to push
        the *unmerged* diagnostic count into this badge while the list stayed
        merged, so this reader exists specifically to catch that class of bug
        -- a test using only ``issues_tab_count()`` cannot see it.
        """
        text = self._w._inspector._secondary._buttons["issues"].text()
        if "(" not in text:
            return 0
        return int(text.rsplit("(", 1)[1].rstrip(")"))

    def issues_tab_count(self) -> int:
        return self._w._inspector._issues_tab._list.count()

    def issues_tab_texts(self) -> list[str]:
        """Text of every row currently listed in the Issues tab (decision Q:
        a null/bad FloatInt value's float_type+int_type pair displays merged
        to one row here)."""
        lst = self._w._inspector._issues_tab._list
        return [lst.item(i).text() for i in range(lst.count())]

    def issues_tab_message(self) -> str | None:
        """Visible placeholder text when the Issues tab shows one, else None."""
        tab = self._w._inspector._issues_tab
        if tab._stack.currentWidget() is tab._placeholder:
            return tab._placeholder.text()
        return None

    def secondary_expanded(self) -> bool:
        return self._w._inspector._secondary.is_expanded

    def validation_issue_count(self) -> int:
        """Count of Issues-section rows only (the page also always renders
        two section headers plus the Outstanding section -- Phase 5)."""
        return len(self._validation_rows("issue"))

    def validation_outstanding_count(self) -> int:
        """Count of Outstanding-section task rows only."""
        return len(self._validation_rows("task"))

    def validation_message(self) -> str | None:
        """Visible full-page placeholder text ("No document open"), or None
        once a document is open -- the page then always shows its list (the
        two sections carry their own inline empty-state rows instead)."""
        panel = self._w._diagnostics
        if panel._stack.currentWidget() is panel._placeholder:
            return panel._placeholder.text()
        return None

    def editor_showing_empty_state(self) -> bool:
        """True when the Editor page shows its no-document hint rather than
        the tree/params/inspector splitter."""
        page = self._w._editor_page
        return page._stack.currentWidget() is page._placeholder

    def editor_empty_state_text(self) -> str:
        return self._w._editor_page._placeholder.text()

    def current_view_index(self) -> int:
        return self._w._stack.currentIndex()

    def validation_badge_count(self) -> int:
        """The Diagnostics activity-bar entry's badge count (0 = no badge)."""
        return self._w._btn_diagnostics.badge_count

    def validation_badge_severity(self) -> str | None:
        """The Diagnostics entry's badge severity: 'error', 'warning' or None."""
        return self._w._btn_diagnostics.badge_severity

    def validation_tooltip(self) -> str:
        """The Diagnostics activity-bar entry's tooltip text."""
        return self._w._btn_diagnostics.toolTip()

    def page_header_title(self) -> str:
        """The page header's current (raw, non-upper-cased) title."""
        return self._w._page_header.title()

    def activity_bar_selected_label(self) -> str | None:
        """Accessible name of whichever activity bar button is checked."""
        for btn in self._w._activity_bar._buttons:
            if btn.isChecked():
                return btn.accessibleName()
        return None

    def workspace_info_text(self) -> str:
        """Text of the Workspace page's current-document card, flattened.

        Composed from the card's title, validity badge and field rows into the
        ``Key: value`` lines the workspace assertions read, so a layout change
        (single label -> formatted card) does not ripple into every test.
        """
        ws = self._w._workspace
        title = ws._info_title.text()
        if title == "No document open":
            return title
        lines = [f"Title: {title}"]
        if ws._info_badge.text():
            lines.append(f"Validity: {ws._info_badge.text()}")
        for key in ("Model", "BPX version", "File", "State", "Contents"):
            lines.append(f"{key}: {ws._info_fields[key].text()}")
        return "\n".join(lines)

    def tree_selection_label(self) -> str | None:
        """Label of the node currently selected in the structure tree, if any."""
        index = self._w._tree._view.currentIndex()
        if not index.isValid():
            return None
        return index.internalPointer().label

    def tree_path_is_expanded(self, path: tuple[str, ...]) -> bool:
        """True when the tree node at *path* is expanded."""
        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        return index.isValid() and view.isExpanded(index)

    # ------------------------------------------------------------------
    # Grid cards (SeriesCard, and later interpolated tables)
    # ------------------------------------------------------------------

    def grid_values(self) -> list[list[object]]:
        """Every row of the active card's grid, as raw cell objects."""
        return self._grid().values()

    def set_grid_cell(self, row: int, column: int, text) -> "AppDriver":
        """Type *text* into one grid cell (what the cell delegate commits).

        Drives the model's ``setData`` -- the same entry point the cell editor
        uses on confirm -- so the lenient parse and no-coercion contract are
        exercised without opening a per-cell editor widget.
        """
        from PySide6.QtCore import Qt

        grid = self._grid()
        grid._model.setData(grid._model.index(row, column), str(text), Qt.EditRole)
        return self

    def add_grid_row(self) -> "AppDriver":
        self._grid().insert_row()
        return self

    def remove_grid_row(self, row: int | None = None) -> "AppDriver":
        grid = self._grid()
        if row is not None:
            grid._view.setCurrentIndex(grid._model.index(row, 0))
        grid.remove_row()
        return self

    def open_grid_cell_editor(self, row: int, column: int) -> "AppDriver":
        """Open the real per-cell editor widget for one grid cell.

        Types a digit into the cell -- the ``AnyKeyPressed`` trigger -- so the
        delegate opens its ``QLineEdit``, exactly as a user editing a cell does.
        The window is shown first: an item delegate opens and commits its editor
        against a live view, and in an unshown window it never leaves the edit
        state. Use with :meth:`press_in_cell_editor` to exercise the cell-level
        (vs grid-level) Enter/Escape layer.
        """
        from PySide6.QtCore import Qt

        grid = self._grid()
        view = grid.focus_widget()
        self._w.show()
        view.setFocus()
        view.setCurrentIndex(grid._model.index(row, column))
        self._qtbot.keyClick(view, Qt.Key_1)
        return self

    def grid_cell_editor_open(self) -> bool:
        from PySide6.QtWidgets import QAbstractItemView

        return self._grid().focus_widget().state() == QAbstractItemView.State.EditingState

    def press_in_cell_editor(self, key) -> "AppDriver":
        """Send a key to the open cell editor widget (not the grid).

        Waits for Qt to deliver the delegate's commit/close after the key, so
        the caller observes the settled state rather than a mid-transition one.
        """
        from PySide6.QtWidgets import QLineEdit

        editor = self._grid().focus_widget().findChild(QLineEdit)
        assert editor is not None, "No cell editor is open."
        self._qtbot.keyClick(editor, key)
        self._qtbot.wait(10)
        return self

    def commit_grid(self) -> "AppDriver":
        """Press Enter on the grid itself to commit the draft to the document."""
        from PySide6.QtCore import Qt

        self._qtbot.keyClick(self._grid().focus_widget(), Qt.Key_Return)
        return self

    def revert_grid(self) -> "AppDriver":
        """Press Escape on the grid itself to discard the draft."""
        from PySide6.QtCore import Qt

        self._qtbot.keyClick(self._grid().focus_widget(), Qt.Key_Escape)
        return self

    def _grid(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        grid = getattr(editor, "_grid", None)
        if grid is None:
            # A ModalCard's grid lives inside its active table body.
            body = getattr(editor, "_body", None)
            grid = getattr(body, "_grid", None)
        assert grid is not None, f"Card {type(editor).__name__} has no grid."
        return grid

    # ------------------------------------------------------------------
    # Modal cards (mode strip)
    # ------------------------------------------------------------------

    def mode_labels(self) -> tuple[str, ...]:
        """The strip's mode names, in verbatim bpx.schema vocabulary."""
        return self._modal().mode_labels

    def current_mode(self) -> str:
        return self._modal().current_mode

    def select_mode(self, label: str) -> "AppDriver":
        """Click a mode button on the strip."""
        modal = self._modal()
        index = list(modal.mode_labels).index(label)
        self._qtbot.mouseClick(modal._strip._buttons[index], Qt.LeftButton)
        return self

    def mode_strip_visible(self) -> bool:
        """False for a kind with a single representation (no strip is built)."""
        return self._modal()._strip is not None

    def commit_blocked_reason(self) -> str | None:
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        return card.commit_blocked_reason()

    def set_raw_json(self, text: str) -> "AppDriver":
        """Replace the Raw mode body's JSON text wholesale."""
        modal = self._modal()
        assert modal.current_mode == "Raw", f"Not in Raw mode ({modal.current_mode})."
        modal._body._edit.setPlainText(text)
        return self

    def _modal(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        assert hasattr(editor, "mode_labels"), (
            f"Card {type(editor).__name__} is not a ModalCard."
        )
        return editor

    # ------------------------------------------------------------------
    # ExperimentCard (a Validation run's unified multi-column editor)
    # ------------------------------------------------------------------

    def experiment_card(self):
        """The active :class:`~ui_qt.cards.experiment.ExperimentCard`.

        Asserts loudly (naming the actual card type) rather than returning
        ``None``, since every caller below assumes it exists.
        """
        from ui_qt.cards.experiment import ExperimentCard

        card = self._w._inspector._card
        assert isinstance(card, ExperimentCard), (
            "Inspector is not showing an ExperimentCard "
            f"({type(card).__name__ if card is not None else None})."
        )
        return card

    def experiment_columns(self) -> tuple[str, ...]:
        """The aliases of every column the card currently shows, in order."""
        return tuple(p.label for p in self.experiment_card()._columns)

    def experiment_focused_column(self) -> str | None:
        """The alias of the column holding the grid's current-cell ring, or
        ``None`` if nothing is focused (a bare run-node reveal)."""
        card = self.experiment_card()
        index = card._grid._view.currentIndex()
        if not index.isValid():
            return None
        return card._columns[index.column()].label

    def _experiment_column_index(self, alias: str) -> int:
        return [p.label for p in self.experiment_card()._columns].index(alias)

    def experiment_column_values(self, alias: str) -> list:
        card = self.experiment_card()
        return card._grid.column_values(self._experiment_column_index(alias))

    def set_experiment_cell(self, alias: str, row: int, text) -> "AppDriver":
        """Type *text* into one cell of column *alias* (the model's
        ``setData``, exactly like :meth:`set_grid_cell`)."""
        card = self.experiment_card()
        grid = card._grid
        column = self._experiment_column_index(alias)
        grid._model.setData(grid._model.index(row, column), str(text), Qt.EditRole)
        return self

    def experiment_cell_tooltip(self, alias: str, row: int) -> str | None:
        card = self.experiment_card()
        grid = card._grid
        column = self._experiment_column_index(alias)
        return grid._model.data(grid._model.index(row, column), Qt.ToolTipRole)

    def commit_experiment(self) -> "AppDriver":
        """Press Enter on the card's grid: commits every changed column as
        one ``SetValues``."""
        card = self.experiment_card()
        self._qtbot.keyClick(card._grid.focus_widget(), Qt.Key_Return)
        return self

    def revert_experiment(self) -> "AppDriver":
        """Press Escape on the card's grid: discards every column's draft."""
        card = self.experiment_card()
        self._qtbot.keyClick(card._grid.focus_widget(), Qt.Key_Escape)
        return self

    def experiment_card_is_dirty(self) -> bool:
        return self.experiment_card().is_dirty

    def experiment_title(self) -> str:
        return self.experiment_card()._title.text()

    def experiment_add_temperature_button(self):
        """The "+ Temperature [K]" button, or ``None`` when hidden (the
        column already exists, or the card is read-only)."""
        return self.experiment_card()._add_temperature_button

    def click_experiment_add_temperature(self) -> "AppDriver":
        button = self.experiment_add_temperature_button()
        assert button is not None, "No '+ Temperature [K]' button is currently shown."
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def experiment_chip_text(self) -> str | None:
        card = self.experiment_card()
        return card._chip.text() if card._chip is not None else None

    def experiment_import_csv(self, data, mapping) -> "AppDriver":
        """Apply a confirmed CSV mapping directly (the dialog itself is
        modal and tested separately; see ``test_csv_import.py``)."""
        self.experiment_card()._apply_csv_import(data, mapping)
        return self

    def experiment_dropzone_shown(self) -> bool:
        """Whether the import-first dropzone is currently visible (Phase 3).

        ``isHidden()``, not ``isVisible()``: the window is never shown in
        this suite, so ``isVisible()`` would read ``False`` regardless of
        the widget's own hidden flag (see ``test_modal_cards.py``)."""
        dropzone = self.experiment_card()._dropzone
        return dropzone is not None and not dropzone.isHidden()

    def experiment_sample_count_text(self) -> str:
        return self.experiment_card()._sample_count_chip.text()

    def click_experiment_dropzone_browse(self) -> "AppDriver":
        dropzone = self.experiment_card()._dropzone
        assert dropzone is not None, "No dropzone is currently shown."
        button = dropzone.findChild(QPushButton, "ExperimentDropzoneUpload")
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def click_experiment_database_examples(self) -> "AppDriver":
        button = self.experiment_card()._database_examples_button
        assert button is not None, "No 'Compare…' button is currently shown."
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def open_database_examples_dialog_from_toolbar(self):
        """Click the card header's "Compare…" button and return the live
        dialog it created -- the caller's own ``.exec()`` must already be
        neutralised (see ``test_database_examples_dialog.py``'s ``_no_exec``
        fixture), or this blocks forever on a real modal loop."""
        from ui_qt.cards.database_examples_dialog import DatabaseExamplesDialog

        card = self.experiment_card()
        self.click_experiment_database_examples()
        dialog = card.findChild(DatabaseExamplesDialog)
        assert dialog is not None, "Database examples dialog was not created."
        return dialog

    # ------------------------------------------------------------------
    # ValidationEmptyState (zero-run Validation container, Phase 4)
    # ------------------------------------------------------------------

    def validation_empty_state_shown(self) -> bool:
        from ui_qt.validation_empty_state import ValidationEmptyState

        return isinstance(self._w._inspector._card, ValidationEmptyState)

    def _validation_empty_state(self):
        from ui_qt.validation_empty_state import ValidationEmptyState

        card = self._w._inspector._card
        assert isinstance(card, ValidationEmptyState), (
            "Inspector is not showing the ValidationEmptyState "
            f"({type(card).__name__ if card is not None else None})."
        )
        return card

    def click_add_experiment(self) -> "AppDriver":
        widget = self._validation_empty_state()
        self._qtbot.mouseClick(widget._add_button, Qt.LeftButton)
        return self

    def click_import_csv_as_new_experiment(self) -> "AppDriver":
        widget = self._validation_empty_state()
        self._qtbot.mouseClick(widget._import_button, Qt.LeftButton)
        return self

    def confirm_validation_empty_state_name(self, name: str) -> "AppDriver":
        """Type *name* into the open name popup and confirm it -- same
        directness as ``test_tree_editing.py``'s own ``NamePopup`` driving."""
        widget = self._validation_empty_state()
        widget._popup._input.setText(name)
        widget._popup._input.confirm_requested.emit()
        return self

    def drop_file_on_experiment_dropzone(self, path: Path | str) -> "AppDriver":
        """Simulate dropping *path* onto the card's dropzone -- same real-
        ``QDropEvent`` idiom as :meth:`drop_file_on_workspace`."""
        dropzone = self.experiment_card()._dropzone
        assert dropzone is not None, "No dropzone is currently shown."
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(path))])
        event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
        dropzone.dropEvent(event)
        return self

    def open_experiment_cell_editor(self, alias: str, row: int) -> "AppDriver":
        """Open the real per-cell editor widget for one cell of column
        *alias* -- mirrors :meth:`open_grid_cell_editor` for the multi-column
        grid, to exercise the same cell-level-vs-grid-level keyboard layering."""
        card = self.experiment_card()
        grid = card._grid
        column = self._experiment_column_index(alias)
        view = grid.focus_widget()
        self._w.show()
        view.setFocus()
        view.setCurrentIndex(grid._model.index(row, column))
        self._qtbot.keyClick(view, Qt.Key_1)
        return self

    def experiment_cell_editor_open(self) -> bool:
        from PySide6.QtWidgets import QAbstractItemView

        return (
            self.experiment_card()._grid.focus_widget().state()
            == QAbstractItemView.State.EditingState
        )

    def press_in_experiment_cell_editor(self, key) -> "AppDriver":
        from PySide6.QtWidgets import QLineEdit

        editor = self.experiment_card()._grid.focus_widget().findChild(QLineEdit)
        assert editor is not None, "No cell editor is open."
        self._qtbot.keyClick(editor, key)
        self._qtbot.wait(10)
        return self

    def rename_node(self, path: tuple[str, ...], new_name: str) -> "AppDriver":
        """Rename the user-named key at *path*, as the tree's rename UI does."""
        self._w._tree.rename_requested.emit(tuple(path), new_name)
        return self

    def open_tree_rename_popup(self, path: tuple[str, ...]) -> "AppDriver":
        """Open the tree's rename popup for the node at *path*, as its own
        "Rename…" context-menu action would."""
        tree = self._w._tree
        node = _find_tree_node(tree._root, tuple(path))
        assert node is not None, f"No tree node at {path!r}"
        tree._open_rename(node)
        return self

    def tree_rename_popup_note_text(self) -> str | None:
        """The rename popup's small informational note line, or None when
        hidden (every target but a Particle material)."""
        note = self._w._tree._popup._note
        return note.text() if note.isVisible() else None

    # ------------------------------------------------------------------
    # Internals -- the one place that knows card widget structure
    # ------------------------------------------------------------------

    def _editor_widget(self):
        card = self._w._inspector._card
        assert card is not None, "No active card; navigate to a parameter first."
        editor = card._editor
        # A ModalCard has no single input widget: it delegates to whichever
        # mode body is showing.
        focus_widget = getattr(editor, "focus_widget", None)
        if callable(focus_widget):
            return focus_widget()
        for attr in ("_edit", "_fallback", "_spin", "_combo"):
            widget = getattr(editor, attr, None)
            if widget is not None:
                return widget
        raise AssertionError(f"Card {type(editor).__name__} exposes no editor widget.")
