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
from PySide6.QtGui import QDropEvent, QTextDocument
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


def _strip_chevron(text: str) -> str:
    """Drop a Diagnostics stream fold/clear-line row's leading "▸ "/"▾ "
    (the delegate paints straight from the same plain-text item) so
    assertions on header/clear-line content read clean without it."""
    return text[2:] if text[:1] in ("▸", "▾") else text


class AppDriver:
    """Drives a live :class:`MainWindow` the way a user would."""

    def __init__(self, window, qtbot) -> None:
        self._w = window
        self._qtbot = qtbot

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    def open(self, path: Path | str) -> "AppDriver":
        """Open a document by path (equivalent to File > Open).

        A detectably legacy v0.x *path* raises the real (blocking) D3
        prompt -- a legacy test must use :meth:`open_as_is` or stub
        ``_ask_legacy_intent`` itself."""
        self._w.open_document(Path(path))
        return self

    def open_as_is(self, path: Path | str) -> "AppDriver":
        """Open a legacy v0.x file as the main document, answering the D3
        prompt with "Open as-is, read-only" -- the state Phase 4's legacy
        record/stream facts describe. The prompt seam is stubbed for this
        one call (the ``_ask_open_intent`` monkeypatch convention)."""
        from ui_qt.main_window import LegacyIntent

        self._w._ask_legacy_intent = lambda *args: LegacyIntent.AS_IS_READ_ONLY
        try:
            self._w.open_document(Path(path))
        finally:
            del self._w._ask_legacy_intent
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

    def toggle_documentation_section(self) -> "AppDriver":
        """Click the Documentation section's title row (disclosure toggle)."""
        header = self._w._inspector._docs_section.header
        self._qtbot.mouseClick(header, Qt.LeftButton)
        return self

    # -- Diagnostics page: strip + one scrolling stream ---------------------
    #
    # The default surface for driver reads is the stream (``_stream``) --
    # the page's only renderer now (the old rail + single-section/"All
    # sections" pair is gone, PLAN-diagnostics-stream.md). It always
    # contains every issue/task row that survives the current chip filter,
    # so ``_validation_rows``/``validation_issue_texts``/``outstanding_
    # tasks``/etc. below all read it directly. Stream-specific state (fold
    # headers, the clear line, the all-clear row, collapse-all) gets its
    # own ``diagnostics_*``-prefixed methods further down.

    def activate_first_validation_issue(self) -> "AppDriver":
        """Activate the first issue row in the stream.

        Emits ``itemActivated`` -- the signal the panel actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the panel does
        not listen to.
        """
        items = self._validation_rows("issue")
        assert items, "No issue row in the Diagnostics list."
        self._w._diagnostics._stream._list.itemActivated.emit(items[0])
        return self

    def activate_validation_row(self, item) -> "AppDriver":
        """Emit ``itemActivated`` for one already-located ``QListWidgetItem``
        from the stream (e.g. from :meth:`_validation_rows`) -- the
        low-level primitive :meth:`activate_first_validation_issue`/
        :meth:`activate_outstanding_task` build on."""
        self._w._diagnostics._stream._list.itemActivated.emit(item)
        return self

    def activate_outstanding_task(self, task) -> "AppDriver":
        """Activate the Outstanding row for *task* (a ``CompletionTask``, as
        returned by :meth:`outstanding_tasks`) in the stream."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("task"):
            if item.data(dp._TASK_ROLE) == task:
                self._w._diagnostics._stream._list.itemActivated.emit(item)
                return self
        raise AssertionError(f"No Outstanding row for {task!r}")

    def outstanding_tasks(self) -> list:
        """Every ``CompletionTask`` currently rendered as a task row in the
        stream, in on-screen order."""
        from ui_qt import diagnostics_panel as dp

        return [item.data(dp._TASK_ROLE) for item in self._validation_rows("task")]

    def outstanding_task_row_text(self, task) -> str:
        """Plain text of the task row for *task* -- includes any absorbed
        validator messages appended as secondary text."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("task"):
            if item.data(dp._TASK_ROLE) == task:
                return item.text()
        raise AssertionError(f"No Outstanding row for {task!r}")

    def validation_group_headers(self) -> list[str]:
        """Text of every stream sub-head row, in order -- today only ever
        "OPTIONAL . K UNFILLED" (the required group's own former ratio
        sub-head is gone: that ratio now lives in the section's own fold
        header, D5). See :meth:`diagnostics_stream_subhead_texts` for the
        same read under its new name."""
        return [item.text() for item in self._validation_rows("subhead")]

    def validation_task_row_count_under_header(self, header_text: str) -> int:
        """Number of "task" rows directly beneath the sub-head/fold-header
        row whose text is *header_text* (chevron already stripped from a
        fold-header row, matching :meth:`diagnostics_stream_headers`'s own
        contract), up to (not including) the next such row (a required
        group's stated N must equal this count exactly, never an optional
        row sitting in between)."""
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._stream._list
        start = None
        for i in range(lst.count()):
            item = lst.item(i)
            kind = item.data(dp._KIND_ROLE)
            if kind in ("subhead", "fold_header") and _strip_chevron(item.text()) == header_text:
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
        """Text of every issue row in the stream, in order."""
        return [item.text() for item in self._validation_rows("issue")]

    def activate_validation_group_header(self, index: int = 0) -> "AppDriver":
        """Activate a sub-head row directly -- proves it is a structural
        no-op; only issue/task rows act."""
        return self.activate_validation_row(self._validation_rows("subhead")[index])

    def activate_fold_header(self, index: int = 0) -> "AppDriver":
        """Activate (Enter/double-click) a stream fold-header row directly
        -- proves it is a structural no-op; folding is single-click only
        (:meth:`diagnostics_fold_section`)."""
        return self.activate_validation_row(self._validation_rows("fold_header")[index])

    def all_sections_fold_headers(self) -> list[tuple[str, bool]]:
        """``(section_label, collapsed)`` for every rendered SECTION bucket's
        fold header, in display order -- the file-facts group (S1) is not a
        section and is excluded, matching this method's own name."""
        from ui_qt import diagnostics_panel as dp

        return [
            (item.data(dp._FOLD_BUCKET_ROLE).label, bool(item.data(dp._FOLD_COLLAPSED_ROLE)))
            for item in self._validation_rows("fold_header")
            if item.data(dp._FOLD_BUCKET_ROLE).path != dp._FILE_FACTS_PATH
        ]

    def diagnostics_fold_section(self, label: str) -> "AppDriver":
        """Fold/unfold the named bucket in the stream, as a single click on
        its header does."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("fold_header"):
            if item.data(dp._FOLD_BUCKET_ROLE).label == label:
                self._w._diagnostics._stream._on_clicked(item)
                return self
        raise AssertionError(f"No stream fold header for {label!r}.")

    def validation_task_texts(self) -> list[str]:
        """Text of every Outstanding task row in the stream, in order."""
        return [item.text() for item in self._validation_rows("task")]

    def validation_issue_html(self) -> list[str]:
        """The painted HTML of every issue row in the stream, in order --
        lets a test assert the two-line location/message split without
        pixel-reading."""
        from ui_qt import parameter_row

        return [
            item.data(parameter_row.HTML_ROLE) for item in self._validation_rows("issue")
        ]

    def _validation_rows(self, kind: str) -> list:
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._stream._list
        return [
            lst.item(i)
            for i in range(lst.count())
            if lst.item(i).data(dp._KIND_ROLE) == kind
        ]

    def activate_validation_issue(self, path: tuple[str, ...]) -> "AppDriver":
        """Emit the Diagnostics panel's own activation signal for *path*.

        Drives through the panel's public ``issue_activated`` signal
        directly (the same entry point a real double-click or Enter/Return
        uses internally, forwarded unmodified), bypassing ``QListWidget``'s
        ``itemDoubleClicked`` -- which is a distinct Qt signal from
        ``itemActivated`` and, unlike a genuine mouse event, does not
        trigger it when emitted manually.
        """
        self._w._diagnostics.issue_activated.emit(tuple(path))
        return self

    # -- Diagnostics stream: headers, clear line, all-clear, collapse-all --

    def diagnostics_strip_counts(self) -> tuple[int, int, int]:
        """``(errors, warnings, outstanding)`` -- the summary strip's own
        totals, straight from the ``PageBuckets`` the stream also renders
        from, so these can never disagree."""
        buckets = self._w._diagnostics._buckets
        if buckets is None:
            return (0, 0, 0)
        return (buckets.error_count, buckets.warning_count, buckets.outstanding_count)

    def diagnostics_bucket(self, label: str):
        """The ``SectionBucket`` with this label, or ``None`` for an
        unknown one."""
        buckets = self._w._diagnostics._buckets
        if buckets is None or label == "All sections":
            return None
        return next((b for b in buckets.buckets if b.label == label), None)

    def diagnostics_stream_headers(self) -> list[str]:
        """Every rendered fold-header's text, chevron stripped, in display
        order -- a section bucket's own (label plus its D5 suffix, e.g.
        "State  1 error · 2 of 5 remaining") *and*, when it renders, the
        file-facts group's (S1) ahead of every one of them."""
        return [_strip_chevron(item.text()) for item in self._validation_rows("fold_header")]

    def diagnostics_stream_section_headers(self) -> list[str]:
        """Like :meth:`diagnostics_stream_headers`, but SECTION buckets
        only -- the file-facts group (S1) excluded -- for assertions about
        section-bucket rendering that predate S1 and are unaffected by
        whether a document also happens to carry a file fact."""
        from ui_qt import diagnostics_panel as dp

        return [
            _strip_chevron(item.text())
            for item in self._validation_rows("fold_header")
            if item.data(dp._FOLD_BUCKET_ROLE).path != dp._FILE_FACTS_PATH
        ]

    def diagnostics_stream_issue_texts(self) -> list[str]:
        return [item.text() for item in self._validation_rows("issue")]

    def diagnostics_stream_task_texts(self) -> list[str]:
        return [item.text() for item in self._validation_rows("task")]

    def diagnostics_stream_subhead_texts(self) -> list[str]:
        return [item.text() for item in self._validation_rows("subhead")]

    def diagnostics_file_facts_header(self) -> str | None:
        """The file-facts group's own fold-header text (S1), chevron
        stripped, e.g. "nmc_pouch_cell_BPX.json  1 note" -- or ``None``
        while the group isn't rendered at all (no fact for the open
        document)."""
        from ui_qt import diagnostics_panel as dp

        for item in self._validation_rows("fold_header"):
            if item.data(dp._FOLD_BUCKET_ROLE).path == dp._FILE_FACTS_PATH:
                return _strip_chevron(item.text())
        return None

    def diagnostics_file_fact_texts(self) -> list[str]:
        """Plain text ("headline\\nsub") of every rendered file-facts row,
        in order -- empty while the group is folded or absent."""
        return [item.text() for item in self._validation_rows("file_fact")]

    def diagnostics_clear_line_text(self) -> str | None:
        """The clear line's own text, chevron stripped (e.g. "7 sections
        clear"), or ``None`` while it isn't rendered at all (no clear
        bucket exists)."""
        item = self._diagnostics_clear_summary_item()
        return _strip_chevron(item.text()) if item is not None else None

    def diagnostics_clear_line_tooltip(self) -> str:
        """The clear line's hover: why its "not checked" half reads that way.
        Empty when nothing on the line is unchecked."""
        item = self._diagnostics_clear_summary_item()
        return item.toolTip() if item is not None else ""

    def diagnostics_toggle_clear_line(self) -> "AppDriver":
        """Click the clear line, as a single click on it does."""
        item = self._diagnostics_clear_summary_item()
        if item is None:
            raise AssertionError("No clear line is currently shown.")
        self._w._diagnostics._stream._on_clicked(item)
        return self

    def _diagnostics_clear_summary_item(self):
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._stream._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(dp._KIND_ROLE) == "clear_summary":
                return item
        return None

    def diagnostics_clear_section_texts(self) -> list[str]:
        """Text of every expanded clear-line row, in order -- empty unless
        the clear line is currently expanded."""
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._stream._list
        return [lst.item(i).text() for i in range(lst.count()) if lst.item(i).data(dp._KIND_ROLE) == "clear_row"]

    def diagnostics_all_clear_text(self) -> str | None:
        """The D9 pinned all-clear row's plain text (both lines, "\\n"
        joined), or ``None`` while it isn't rendered."""
        from ui_qt import diagnostics_panel as dp

        lst = self._w._diagnostics._stream._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(dp._KIND_ROLE) == "all_clear":
                return item.text()
        return None

    def diagnostics_collapse_all_text(self) -> str | None:
        """The strip's D15 affordance label ("Collapse all"/"Expand all"),
        or ``None`` while it is hidden."""
        label = self._w._diagnostics._strip._collapse_all
        return None if label.isHidden() else label.text()

    def diagnostics_toggle_collapse_all(self) -> "AppDriver":
        """Click the strip's Collapse all/Expand all affordance."""
        self._qtbot.mouseClick(self._w._diagnostics._strip._collapse_all, Qt.LeftButton)
        return self

    # -- Diagnostics filters ------------------------------------------------

    def diagnostics_chip_is_on(self, name: str) -> bool:
        """*name* is "errors"/"warnings"/"outstanding"."""
        return self._diagnostics_chip(name).is_on()

    def diagnostics_toggle_chip(self, name: str) -> "AppDriver":
        """Click the named strip chip, as a real mouse click would."""
        self._qtbot.mouseClick(self._diagnostics_chip(name), Qt.LeftButton)
        return self

    def diagnostics_chip_is_enabled(self, name: str) -> bool:
        """False for a zero-count chip (D13) -- disabled, so a click does
        nothing (Qt withholds the mouse event entirely)."""
        return self._diagnostics_chip(name).isEnabled()

    def _diagnostics_chip(self, name: str):
        strip = self._w._diagnostics._strip
        return {"errors": strip._errors, "warnings": strip._warnings, "outstanding": strip._outstanding}[name]

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

    def activate_first_parameter_issue(self) -> "AppDriver":
        """Activate the first issue in the Inspector's Issues section.

        Emits ``itemActivated`` -- the signal the view actually connects
        (fired by a real double-click or Enter/Return) -- rather than
        ``itemDoubleClicked``, which is a distinct Qt signal the view does
        not listen to.
        """
        lst = self._w._inspector._issues_view._list
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

    # -- Source page --------------------------------------------------------

    def source_rail_enabled(self) -> bool:
        """Whether the Source rail entry is currently clickable (gated on an
        open document)."""
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

    def source_pull_paths(self) -> list[tuple[tuple, bool]]:
        """(path, is_section) of every ← gutter chip the Source view
        currently shows, top to bottom."""
        return [
            (path, is_section)
            for _, path, is_section in self._w._source._view.pull_lines()
        ]

    def source_pull(self, path: tuple[str, ...]) -> "AppDriver":
        """Click the ← gutter chip on *path*'s line. Raises if that line
        shows no chip -- pulling an equal/main-only row is impossible in
        the UI and stays impossible here."""
        view = self._w._source._view
        for _, pull_path, is_section in view.pull_lines():
            if pull_path == tuple(path):
                view.pull_requested.emit(pull_path, is_section)
                return self
        raise AssertionError(f"no ← pull chip on {path!r}")

    def source_chipped_texts(self) -> list[tuple[int, str, str]]:
        """Every value-chip highlight as (line index, "main"/"ref", text);
        empty with no reference docked (chips are a two-pane signal)."""
        return self._w._source._view.chipped_texts()

    def source_pane_headers(self) -> tuple[str, str] | None:
        """The two pane-header labels ("Main · …", "Reference · …"), or
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

    def source_file_label(self) -> str | None:
        """The single-pane toolbar's "filename · model" label text, or
        ``None`` while it is hidden (two-pane mode, or no document)."""
        label = self._w._source._file_label
        return None if label.isHidden() else label.text()

    def source_selected_path(self) -> tuple | None:
        """The Source view's selected row path (last clicked/revealed row),
        or ``None``."""
        return self._w._source._view.selected_path()

    def source_fold_button_text(self) -> str:
        """The toolbar's fold-all button label ("▾ Collapse Parameters" /
        "▸ Expand Parameters"), tracking the fold state of every
        multi-line (dict/list) parameter value; sections don't count."""
        return self._w._source._fold_button.text()

    def source_toggle_fold_all(self) -> "AppDriver":
        """Click the Source toolbar's fold-all toggle."""
        self._w._source._fold_button.click()
        return self

    def source_stale_band_visible(self) -> bool:
        """Whether the "<name> changed on disk" band is shown."""
        return not self._w._source._stale_band.isHidden()

    def source_stale_band_text(self) -> str:
        """The stale band's sentence -- it names the pinned references whose
        files changed, since any pin can go stale, not just the one shown."""
        return self._w._source._stale_text.text()

    def source_reference_header_text(self) -> str:
        """The reference pane's header ("Reference 1 of 3  ·  chen.json  ·
        SPM")."""
        return self._w._source._ref_head.text()

    def source_reference_badge_letters(self) -> str | None:
        """The letters of the reference pane's *selected* badge, or ``None``
        with no reference shown."""
        for button in self._w._source._ref_badge_buttons:
            if button.isChecked():
                return button.text()
        return None

    def source_reference_badges(self) -> list[str]:
        """Every badge in the reference pane's selector, in pin order."""
        return [button.text() for button in self._w._source._ref_badge_buttons]

    def click_source_reference_badge(self, index: int) -> "AppDriver":
        """Click the reference pane selector's badge at *index*, switching
        which reference the page compares against."""
        buttons = self._w._source._ref_badge_buttons
        assert index < len(buttons), f"No Source reference badge at {index}"
        buttons[index].click()
        return self

    def source_selected_reference_index(self) -> int:
        return self._w._source.selected_reference_index()

    def source_reload(self) -> "AppDriver":
        """Click the stale band's Reload link."""
        self._w._source._reload_button.click()
        return self

    def source_press_key(self, key: str) -> "AppDriver":
        """Send a navigation key to the Source view ("up"/"down"/"enter" --
        Enter pulls the selected row, the ← chip's keyboard counterpart)."""
        from PySide6.QtTest import QTest

        qt_key = {"up": Qt.Key_Up, "down": Qt.Key_Down, "enter": Qt.Key_Return}[key]
        QTest.keyClick(self._w._source._view, qt_key)
        return self

    def source_flash_path(self) -> tuple[str, ...] | None:
        """The row currently showing the transient "Used" gutter tag,
        or ``None`` once it has faded (or before any pull)."""
        return self._w._source._view.flash_path()

    def source_double_click(self, path: tuple[str, ...]) -> "AppDriver":
        """Double-click *path*'s key line in the main pane, exactly as a
        user does (press then double-click at the line's position).
        Raises if the row is not currently rendered."""
        from PySide6.QtCore import QPoint
        from PySide6.QtTest import QTest

        view = self._w._source._view
        for index, line in enumerate(view._lines):
            if line.row_path == tuple(path):
                y = view.line_top(index) + 2
                point = QPoint(30, y - view.verticalScrollBar().value())
                QTest.mouseDClick(view.viewport(), Qt.LeftButton, pos=point)
                return self
        raise AssertionError(f"no rendered row at {path!r}")

    def notice_window_activation(self) -> "AppDriver":
        """Run the window-activation stale-notice check directly (the
        headless suite has no real activation events to deliver)."""
        self._w._check_reference_stale()
        return self

    def click_workspace_open(self) -> "AppDriver":
        """Click the Open File button on the Workspace page."""
        self._qtbot.mouseClick(self._w._workspace._open_button, Qt.LeftButton)
        return self

    def _trigger_add_route(self, text: str) -> "AppDriver":
        """Pick one route from an empty slot's ＋ menu.

        The menu is built and its action triggered rather than shown: a
        modal ``exec`` cannot be driven headlessly, and the route's own flow
        (which is what these tests are about) starts at the action."""
        menu = self._w._workspace.build_add_menu()
        for action in menu.actions():
            if action.text() == text:
                action.trigger()
                menu.deleteLater()
                return self
        menu.deleteLater()
        raise AssertionError(f"No {text!r} route in the ＋ menu")

    def click_workspace_open_reference(self) -> "AppDriver":
        """Take the ＋ menu's "Open a BPX file…" route (the old dock button;
        same flow, so this seam is stable)."""
        return self._trigger_add_route("Open a BPX file…")

    def click_reference_from_library(self) -> "AppDriver":
        """Take the ＋ menu's reference-library route (opens the modal
        ReferenceLibraryDialog -- tests stub its ``exec``)."""
        return self._trigger_add_route("From the reference library…")

    def add_menu_routes(self) -> list[str]:
        """Every route the ＋ menu currently offers, submenus included by
        title."""
        menu = self._w._workspace.build_add_menu()
        routes = [action.text() for action in menu.actions() if action.text()]
        menu.deleteLater()
        return routes

    def add_menu_recent_files(self) -> list[str]:
        """File names on the ＋ menu's Recent files submenu."""
        menu = self._w._workspace.build_add_menu()
        names: list[str] = []
        for action in menu.actions():
            if action.menu() is not None:
                names = [entry.text() for entry in action.menu().actions()]
        menu.deleteLater()
        return names

    def pin_recent_file(self, name: str) -> "AppDriver":
        """Pick *name* from the ＋ menu's Recent files submenu."""
        menu = self._w._workspace.build_add_menu()
        for action in menu.actions():
            if action.menu() is None:
                continue
            for entry in action.menu().actions():
                if entry.text() == name:
                    entry.trigger()
                    menu.deleteLater()
                    return self
        menu.deleteLater()
        raise AssertionError(f"No recent file {name!r} in the ＋ menu")

    def dock_library_reference(self, set_id: str) -> "AppDriver":
        """Dock bundled reference set *set_id* ("pybamm/chen2020"), driving
        the same post-dialog path the dialog's accept takes -- the seam for
        testing the dock flow without the blocking modal ``exec``."""
        self._w._dock_reference_set(set_id)
        return self

    # --- the board's reference slots (multi-reference) --------------------

    def _reference_rows(self) -> list:
        """The filled reference slots, in pin order."""
        return [
            slot for slot in self._w._workspace._slots if slot.snapshot is not None
        ]

    def _reference_row(self, index: int = 0):
        rows = self._reference_rows()
        if index >= len(rows):
            raise AssertionError(f"No pinned reference at slot {index} (have {len(rows)})")
        return rows[index]

    def click_reference_remove(self, index: int = 0) -> "AppDriver":
        """Click the ✕ on the reference slot at *index*."""
        self._qtbot.mouseClick(self._reference_row(index)._remove, Qt.LeftButton)
        return self

    def empty_slot_count(self) -> int:
        """How many reference slots are still free. The slots are the drawn
        cap, so this replaced the old "n of 4 pinned" counter."""
        return sum(
            1 for slot in self._w._workspace._slots if slot.snapshot is None
        )

    def can_add_reference(self) -> bool:
        """Whether the board still offers a ＋ to click."""
        return self.empty_slot_count() > 0

    def click_reference_diff(self, index: int = 0) -> "AppDriver":
        """Click the differ-count route on the reference slot at *index*."""
        self._qtbot.mouseClick(self._reference_row(index)._diff_route, Qt.LeftButton)
        return self

    def reference_diff_text(self, index: int = 0) -> str:
        """The slot's differ-count route text ("3 values differ ▸")."""
        return self._reference_row(index)._diff_route.text()

    # --- the Workspace rail: named Workspaces above untitled Recent -------

    def _workspace_rows(self) -> list:
        return self._w._workspace._workspace_rows

    def _workspace_row_named(self, label: str, object_name: str | None = None):
        from PySide6.QtWidgets import QLabel

        for row in self._workspace_rows():
            if object_name is not None and row.objectName() != object_name:
                continue
            name = row.findChild(QLabel, "HistoryRowName")
            if name is not None and name.text() == label:
                return row
        raise AssertionError(f"No workspace row labelled {label!r}")

    def _row_labels(self, object_name: str | None = None) -> list[str]:
        from PySide6.QtWidgets import QLabel

        return [
            row.findChild(QLabel, "HistoryRowName").text()
            for row in self._workspace_rows()
            if object_name is None or row.objectName() == object_name
        ]

    def workspace_row_labels(self) -> list[str]:
        """Every rail row's label in display order: named workspaces first,
        then the untitled Recent ones."""
        return self._row_labels()

    def named_workspace_labels(self) -> list[str]:
        """Labels in the Workspaces group (named, never decaying)."""
        return self._row_labels("WorkspaceNamedRow")

    def recent_workspace_labels(self) -> list[str]:
        """Labels in the Recent group (untitled, capped)."""
        return self._row_labels("RecentRow")

    def current_workspace_row_label(self) -> str | None:
        """The label of the row wearing the "open now" pill, if any."""
        from PySide6.QtWidgets import QLabel

        for row in self._workspace_rows():
            if row.findChild(QLabel, "HistoryRowPill") is not None:
                return row.findChild(QLabel, "HistoryRowName").text()
        return None

    def click_workspace_row(self, label: str) -> "AppDriver":
        """Click a rail row, opening that workspace whole."""
        self._qtbot.mouseClick(self._workspace_row_named(label), Qt.LeftButton)
        return self

    def workspace_row_is_missing(self, label: str) -> bool:
        """Whether the row carries the "Not found" chip (its main is gone)."""
        from PySide6.QtWidgets import QLabel

        return (
            self._workspace_row_named(label).findChild(QLabel, "HistoryRowChip")
            is not None
        )

    def workspace_row_reference_count(self, label: str) -> int:
        """How many reference dots the row's glyph draws."""
        from PySide6.QtWidgets import QLabel

        glyph = self._workspace_row_named(label).findChild(QLabel, "WorkspaceGlyph")
        return glyph.text().count("·")

    def workspace_row_actions(self, label: str) -> list[str]:
        """The hover-revealed actions on a rail row, in order."""
        from PySide6.QtWidgets import QPushButton

        row = self._workspace_row_named(label)
        row.set_hovered(True)
        return [button.text() for button in row.findChildren(QPushButton)]

    def click_workspace_row_button(self, label: str, text: str) -> "AppDriver":
        """Hover a rail row (revealing its actions) and click one."""
        from PySide6.QtWidgets import QPushButton

        row = self._workspace_row_named(label)
        row.set_hovered(True)
        for button in row.findChildren(QPushButton):
            if button.text() == text:
                self._qtbot.mouseClick(button, Qt.LeftButton)
                return self
        raise AssertionError(f"No {text!r} action on workspace row {label!r}")

    def click_new_workspace(self) -> "AppDriver":
        """Click "New workspace" -- a separate line of work, empty board."""
        self._qtbot.mouseClick(
            self._w._workspace._new_workspace_button, Qt.LeftButton
        )
        return self

    def rail_empty_state_texts(self) -> list[str]:
        """The one-line empty states currently shown by the two rail groups
        (both groups are always visible, empty or not)."""
        ws = self._w._workspace
        return [
            label.text()
            for label in (ws._workspaces_empty, ws._recent_empty)
            if not label.isHidden()
        ]

    # --- the board's header and banner ------------------------------------

    def workspace_name_text(self) -> str:
        """What the board header shows: the workspace's name, the ghosted
        invitation when it has none, or "" when there is no workspace on the
        board and the header is not offered at all."""
        field = self._w._workspace._name_field
        return "" if field.isHidden() else field._display.text()

    def rename_workspace(self, name: str) -> "AppDriver":
        """Type a new name into the board header and commit it."""
        field = self._w._workspace._name_field
        field.begin_edit()
        field._editor.setText(name)
        self._qtbot.keyClick(field._editor, Qt.Key_Return)
        return self

    def workspace_name_error(self) -> str:
        """The inline refusal under the header ("That name is in use")."""
        return self._w._workspace._name_field.error_text()

    def missing_file_messages(self) -> list[str]:
        """What the missing-file banner is naming, one line per file."""
        return self._w._workspace._missing_banner.missing_labels()

    def click_missing_file_button(self, label: str, text: str) -> "AppDriver":
        """Click Locate…/Remove on the banner row naming *label*."""
        from PySide6.QtWidgets import QLabel, QPushButton

        banner = self._w._workspace._missing_banner
        for row in banner._rows:
            message = row.findChild(QLabel, "WorkspaceMissingText")
            if message is None or label not in message.text():
                continue
            for button in row.findChildren(QPushButton):
                if button.text() == text:
                    self._qtbot.mouseClick(button, Qt.LeftButton)
                    return self
        raise AssertionError(f"No {text!r} button for missing file {label!r}")

    # --- the board's routes out -------------------------------------------

    def workspace_validity_text(self) -> str:
        """The main card's validity mark ("Valid", "3 errors, 1 warning",
        "Not checked · 2 incomplete"), or "" when nothing is open."""
        card = self._w._workspace._main_card
        return "" if card._badge.isHidden() else card.validity_text()

    def workspace_main_name(self) -> str:
        """What the board's main card is naming."""
        return self._w._workspace._main_card.name_text()

    def workspace_record_visible(self) -> bool:
        """Whether the main document's fact plaque is showing (it is not,
        with nothing open)."""
        return not self._w._workspace._fact_band.isHidden()

    def click_edit_route(self) -> "AppDriver":
        """Click the main card's "Edit its parameters ▸"."""
        self._qtbot.mouseClick(
            self._w._workspace._main_card._edit_route, Qt.LeftButton
        )
        return self

    def click_issue_route(self) -> "AppDriver":
        """Click the main card's "N errors · why? ▸"."""
        self._qtbot.mouseClick(
            self._w._workspace._main_card._issue_route, Qt.LeftButton
        )
        return self

    def issue_route_text(self) -> str:
        """The main card's error route text, or "" when it is not offered."""
        route = self._w._workspace._main_card._issue_route
        return "" if route.isHidden() else route.text()

    def click_reference_row(self, index: int = 0) -> "AppDriver":
        """Click the reference slot at *index*, toggling its record."""
        self._qtbot.mouseClick(self._reference_row(index), Qt.LeftButton)
        return self

    def reference_row_expanded(self, index: int = 0) -> bool:
        """Whether the record beneath the board is showing this slot's
        reference."""
        record = self._w._workspace._reference_record
        return (
            not record.isHidden()
            and record.snapshot is self._reference_row(index).snapshot
        )

    def reference_row_badges(self) -> list[str]:
        """Badge letters of the reference slots, in pin order."""
        from ui_qt.reference_identity import badge_letters

        return badge_letters(self.pinned_reference_names())

    def reference_row_detail_text(self, index: int = 0) -> str:
        """The open record's key/value lines, one per line. The record is a
        single panel beneath the board, so the slot at *index* must be the
        one currently showing."""
        from PySide6.QtWidgets import QFormLayout, QLabel

        if not self.reference_row_expanded(index):
            raise AssertionError(f"Reference slot {index} is not showing its record")
        form = self._w._workspace._reference_record._form
        lines = []
        for position in range(form.rowCount()):
            label = form.itemAt(position, QFormLayout.LabelRole).widget()
            field = form.itemAt(position, QFormLayout.FieldRole).widget()
            if isinstance(field, QLabel):
                text = field.text()
            else:
                text = " ".join(
                    child.text()
                    for child in field.findChildren(QLabel)
                    if child.objectName() != "ValidityDot"
                )
            lines.append(f"{label.text()} {text}".strip())
        return "\n".join(lines)

    def unpin_all_references(self) -> "AppDriver":
        """Unpin every pinned reference, through the same handler the
        Workspace's Remove goes through.

        Pinning appends, so a test that means "this reference *instead of*
        that one" has to say so explicitly -- this is that step."""
        while self._w._state.references:
            self._w._on_remove_reference_requested(self._w._state.references[0])
        return self

    def pinned_reference_names(self) -> list[str]:
        """Display names of the pinned references, in pin order."""
        return [reference.filename for reference in self._w._state.references]

    def reference_tile_visible(self) -> bool:
        """Whether the board is holding at least one reference."""
        return bool(self._reference_rows())

    def reference_empty_state_visible(self) -> bool:
        """Whether the board is holding no references at all -- every slot
        an empty ＋, which is the board's own empty state."""
        return not self._reference_rows()

    def reference_tile_text(self, index: int = 0) -> str:
        """Text of the reference at slot *index*, flattened -- the slot's own
        name and model plus its record's lines (mirrors
        :meth:`workspace_info_text`).

        Opens the record to read it, which is what a person does: the slot
        stays compact and the record is one click beneath the board.
        """
        slot = self._reference_row(index)
        if not self.reference_row_expanded(index):
            self.click_reference_row(index)
        record = self._w._workspace._reference_record
        lines = [
            record._read_only_tag.text(),
            slot.snapshot.filename,
            f"Model: {slot.snapshot.model or '-'}",
        ]
        lines.extend(self.reference_row_detail_text(index).splitlines())
        return "\n".join(lines)

    def toast_text(self) -> str | None:
        """The toast's current message (action-link markup excluded), or
        None while it is hidden."""
        toast = self._w._toast
        return toast.message() if not toast.isHidden() else None

    def toast_action_text(self) -> str | None:
        """The visible toast's action-link label, or None (hidden toast,
        or a plain message with no action)."""
        toast = self._w._toast
        return toast.action_text() if not toast.isHidden() else None

    def toast_click_action(self) -> "AppDriver":
        """Click the visible toast's action link. Raises if no toast is
        showing or the message carries no action."""
        toast = self._w._toast
        assert not toast.isHidden(), "no toast is showing"
        assert toast.action_text() is not None, "toast has no action"
        toast._on_link_activated("action")
        return self

    def blocked_write_chip_text(self) -> str | None:
        """The status bar's blocked-write refusal chip, as plain text --
        or None while no refusal is standing."""
        chip = self._w._blocked_chip
        if chip.isHidden():
            return None
        doc = QTextDocument()
        doc.setHtml(chip.text())
        return doc.toPlainText()

    def blocked_write_chip_click(self) -> "AppDriver":
        """Follow the visible refusal chip's link back to the Editor."""
        chip = self._w._blocked_chip
        assert not chip.isHidden(), "no blocked-write chip is showing"
        chip.linkActivated.emit("editor")
        return self

    # ------------------------------------------------------------------
    # Comparison: strip, row decoration, ghost rows, tree marks, reference
    # block, ghost card.
    # ------------------------------------------------------------------

    def comparison_strip_visible(self) -> bool:
        return not self._w._params._strip.isHidden()

    def comparison_strip_chip_names(self) -> list[str]:
        """The strip's chip names, in pin order."""
        return [chip._name.text() for chip in self._w._params._strip._chips]

    def comparison_strip_chip_tooltips(self) -> list[str]:
        """The strip's chip tooltips -- where the per-reference counts live,
        since the chips themselves stay quiet."""
        return [chip.toolTip() for chip in self._w._params._strip._chips]

    def parameter_row_ref_bar(self, label: str) -> str | None:
        """The real parameter row starting with *label*'s own
        :data:`~ui_qt.parameter_row.REF_BAR_ROLE` variant ("differs" /
        "equal" / "ref_only"), or ``None`` if it carries none. This is the
        data the delegate actually paints from (see
        ``ParameterRowDelegate._paint_ref_bar``) -- ``QListWidgetItem``'s
        own ``background()``/``setBackground`` is a dead read once a
        stylesheet styles ``::item`` (a real Qt/QSS gotcha; see
        ``test_parameter_row.py``'s pixel-level regression pin)."""
        from ui_qt import parameter_row

        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                return item.data(parameter_row.REF_BAR_ROLE)
        raise AssertionError(f"No real parameter row starting with {label!r}.")

    def parameter_row_tooltip(self, label: str) -> str:
        """The real parameter row starting with *label*'s tooltip -- the main
        value line, then one line per distinct reference value naming the
        references that hold it."""
        lst = self._w._params._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(256) is not None and item.text().startswith(label):
                return item.toolTip()
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

    def ghost_row_ref_bar(self, key: str) -> str | None:
        from ui_qt import parameter_row

        panel = self._w._params
        lst = panel._list
        for i in range(lst.count()):
            item = lst.item(i)
            if item.data(panel._GROUP_ROW_KIND_ROLE) == "ghost" and item.data(panel._GHOST_KEY_ROLE) == key:
                return item.data(parameter_row.REF_BAR_ROLE)
        raise AssertionError(f"No ghost row for {key!r}.")

    def parameter_list_row_painted_colour(self, item_index: int, dx: int = 6, dy: int = 6) -> str:
        """The actual rendered pixel colour near the top-left of the row at
        *item_index* in the parameter list, real widths/window shown first.

        Proves the delegate genuinely painted a colour, not merely that an
        item carries data a headless read could misreport (see
        ``parameter_row_ref_bar``/``ghost_row_ref_bar`` and
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
        """The tree's own painted DisplayRole text for the node at *path*."""
        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        assert index.isValid(), f"No tree node at {path!r}"
        return model.data(index, Qt.DisplayRole)

    def tree_node_ref_bar(self, path: tuple[str, ...]) -> str | None:
        """The tree node at *path*'s :data:`~ui_qt.parameter_row.
        REF_BAR_ROLE` variant ("differs"/"equal") or ``None`` -- the data
        the tree delegate's gutter rail actually paints from."""
        from ui_qt.parameter_row import REF_BAR_ROLE

        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        assert index.isValid(), f"No tree node at {path!r}"
        return model.data(index, REF_BAR_ROLE)

    def tree_row_painted_colour(self, path: tuple[str, ...], dx: int = 1, dy: int = 12) -> str:
        """The actual rendered pixel colour at *dx* from the tree
        **viewport's** left edge (x=0) on the row at *path*, real
        widths/window shown first -- the tree's own version of
        ``parameter_list_row_painted_colour``, proving the gutter bar
        genuinely painted rather than merely carrying ``REF_BAR_ROLE`` data
        a headless read could misreport.

        *dx* is measured from the viewport edge, not ``rect.left()``: the
        bar paints flush against x=0 regardless of the row's own
        (indentation-shifted) rect (see ``_TreeItemDelegate._paint_ref_bar``)."""
        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        assert index.isValid(), f"No tree node at {path!r}"
        self._w.show()
        self._qtbot.waitExposed(view)
        rect = view.visualRect(index)
        image = view.viewport().grab().toImage()
        return image.pixelColor(dx, rect.top() + dy).name()

    def tree_row_right_band_shows_reference_colour(self, path: tuple[str, ...]) -> bool:
        """True if some pixel in the row's right-hand band (where the
        differ count paints) is tinted toward reference purple.

        A small font's anti-aliased strokes rarely include a pixel of the
        exact pinned colour the way a filled dot does (see
        ``parameter_list_row_painted_colour``'s exact-colour pin) -- a
        channel-distance tolerance against the plain white row background
        is the robust offscreen proxy for "the count actually painted"."""
        from PySide6.QtGui import QColor

        from ui_qt import style

        view = self._w._tree._view
        model = view.model()
        index = model.index_for_path(tuple(path))
        assert index.isValid(), f"No tree node at {path!r}"
        self._w.show()
        self._qtbot.waitExposed(view)
        rect = view.visualRect(index)
        image = view.viewport().grab().toImage()
        target = QColor(style.REFERENCE)
        band_left = max(rect.right() - 40, rect.left())
        for x in range(band_left, rect.right() + 1):
            pixel = image.pixelColor(x, rect.center().y())
            if (
                abs(pixel.red() - target.red()) < 40
                and abs(pixel.green() - target.green()) < 40
                and abs(pixel.blue() - target.blue()) < 40
            ):
                return True
        return False

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

    # --- Card ledger (multi-reference) -----------------------------------

    def _ledger(self):
        """The current card's ledger -- ``ParameterCard`` and
        ``GhostParameterCard`` share the attribute name deliberately."""
        card = self._w._inspector._card
        return getattr(card, "_ledger", None) if card is not None else None

    def _ledger_row(self, index: int = 0):
        ledger = self._ledger()
        assert ledger is not None, "The current card has no ledger"
        assert index < len(ledger._rows), (
            f"No ledger row at index {index} (have {len(ledger._rows)})"
        )
        return ledger._rows[index]

    def reference_block_visible(self) -> bool:
        """Whether the current card's reference ledger is currently shown --
        works for both ``ParameterCard`` and ``GhostParameterCard``."""
        ledger = self._ledger()
        return ledger is not None and not ledger.isHidden()

    def ledger_row_count(self) -> int:
        """How many distinct reference values the current card shows."""
        ledger = self._ledger()
        return len(ledger._rows) if ledger is not None else 0

    def ledger_row_badges(self, index: int = 0) -> list[str]:
        """The badge letters clustered on the ledger row at *index*."""
        from PySide6.QtWidgets import QLabel, QWidget

        row = self._ledger_row(index)
        cluster = row.findChild(QWidget, "LedgerBadgeCluster")
        return [child.text() for child in cluster.findChildren(QLabel)]

    def main_file_heading_visible(self) -> bool:
        """Whether the current ``ParameterCard``'s "Main" role label is
        shown -- only ever true while something is pinned and its section
        is not collapsed by an expanded grid."""
        card = self._w._inspector._card
        heading = getattr(card, "_main_file_heading", None) if card is not None else None
        return heading is not None and not heading.isHidden()

    def main_file_heading_text(self) -> str:
        return self._w._inspector._card._main_file_heading.text()

    def reference_value_text(self, index: int = 0) -> str:
        return self._ledger_row(index)._value.text()

    def reference_block_is_same(self, index: int = 0) -> bool:
        return bool(self._ledger_row(index)._value.property("same"))

    def pull_visible(self, index: int = 0) -> bool:
        """Whether the ledger row at *index* offers a Pull button. A row that
        equals main says "same" and offers none -- Pull's presence is the
        differs signal."""
        from PySide6.QtWidgets import QPushButton

        return self._ledger_row(index).findChild(QPushButton, "PullButton") is not None

    def pull_enabled(self, index: int = 0) -> bool:
        from PySide6.QtWidgets import QPushButton

        button = self._ledger_row(index).findChild(QPushButton, "PullButton")
        return button is not None and button.isEnabled()

    def click_pull(self, index: int = 0) -> "AppDriver":
        """Click the ledger row at *index*'s Pull button -- works for both
        ``ParameterCard`` and ``GhostParameterCard``."""
        from PySide6.QtWidgets import QPushButton

        button = self._ledger_row(index).findChild(QPushButton, "PullButton")
        assert button is not None, f"Ledger row {index} offers no Pull"
        button.click()
        return self

    def reference_grid_visible(self) -> bool:
        """Whether the ledger's read-only x/y grid is showing."""
        ledger = self._ledger()
        return ledger is not None and not ledger._table_grid.isHidden()

    def reference_grid_badges(self) -> list[str]:
        """The grid selector's badges, in pin order -- only the references
        whose table differs from main appear."""
        ledger = self._ledger()
        return [] if ledger is None else [b.text() for b in ledger._grid_buttons]

    def reference_grid_selected(self) -> str | None:
        """The letters of the grid selector's filled badge."""
        ledger = self._ledger()
        if ledger is None:
            return None
        for button in ledger._grid_buttons:
            if button.isChecked():
                return button.text()
        return None

    def click_reference_grid_badge(self, index: int) -> "AppDriver":
        """Click the grid selector's badge at *index*, switching which
        reference's numbers the grid shows."""
        buttons = self._ledger()._grid_buttons
        assert index < len(buttons), f"No reference grid badge at {index}"
        buttons[index].click()
        return self

    def reference_grid_row_count(self) -> int:
        return self._ledger()._table_grid._table.rowCount()

    # --- spread scale ----------------------------------------------------

    def _spread(self):
        ledger = self._ledger()
        return None if ledger is None else ledger._spread

    def spread_visible(self) -> bool:
        """Whether the current card shows the 1-D spread scale."""
        spread = self._spread()
        return spread is not None and spread.is_active

    def spread_axis_kind(self) -> str:
        """"linear" or "log" -- the axis the scale chose and names."""
        spread = self._spread()
        return "" if spread is None else spread.axis_kind()

    def spread_tick_values(self) -> list[float]:
        """The stated reference values on the axis, low to high."""
        spread = self._spread()
        if spread is None or spread._scale is None:
            return []
        return [tick.value for tick in spread._scale.ticks]

    def spread_tick_badges(self, index: int = 0) -> list[str]:
        """The badge letters stacked on the tick at *index*, in pin order."""
        spread = self._spread()
        tick = spread._scale.ticks[index]
        return [spread._pins[pin].letters for pin in tick.indices]

    def spread_tick_levels(self) -> list[int]:
        """The stack level each tick's lowest dot sits on -- 0 unless dots
        would have collided at the axis's painted width."""
        spread = self._spread()
        return [base for _tick, _x, base in spread._placements()]

    def spread_has_main_marker(self) -> bool:
        spread = self._spread()
        return spread is not None and spread._scale is not None and (
            spread._scale.main_position is not None
        )

    def spread_tooltip_at_tick(self, index: int = 0) -> str:
        """The hover text over the tick at *index* -- names plus exact
        value, read at the tick's own painted x."""
        spread = self._spread()
        tick = spread._scale.ticks[index]
        return spread.tooltip_at(spread._x_for(tick.position))

    def spread_tooltip_at_main(self) -> str:
        spread = self._spread()
        return spread.tooltip_at(spread._x_for(spread._scale.main_position))

    # --- chart overlay ---------------------------------------------------

    def _preview(self):
        """The current card's live chart preview, if its editor has one."""
        card = self._w._inspector._card
        editor = getattr(card, "_editor", None) if card is not None else None
        body = getattr(editor, "_table_body", None) if editor is not None else None
        return getattr(body, "_preview", None) if body is not None else None

    def charts_available(self) -> bool:
        """Whether QtCharts could be imported in this build -- every chart
        read below is meaningless without it."""
        from ui_qt.cards.table_preview import charts_available

        return charts_available()

    def chart_legend_badges(self) -> list[str]:
        """The chart legend's badges, one per overlaid reference curve."""
        return [button.text() for button in self._preview()._legend._buttons]

    def chart_legend_tooltips(self) -> list[str]:
        """Each legend badge's tooltip -- the reference's name, the curve's
        own domain and its point count."""
        return [button.toolTip() for button in self._preview()._legend._buttons]

    def click_chart_legend_badge(self, index: int) -> "AppDriver":
        """Click the legend badge at *index*, toggling its curve."""
        self._preview()._legend._buttons[index].click()
        return self

    def chart_curve_points(self, index: int) -> list[tuple[float, float]]:
        """The plotted points of the overlaid curve at *index*."""
        return self._preview()._curve_points[index]

    def chart_curve_shown(self, index: int) -> bool:
        """Whether the overlaid curve at *index* is currently drawn."""
        return self._preview()._ref_series[index].isVisible()

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
        """Click the Parameter list's section-header "+ Add" action."""
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
        or the "Create custom parameter" footer, which instead switches the
        popup to its Custom tab (see :meth:`submit_custom_parameter_form`)."""
        self._w._params._popup._activate()
        return self

    def add_parameter_custom_form_visible(self) -> bool:
        """True once the popup has switched to its Custom tab."""
        from ui_qt.add_parameter_popup import _TAB_LABELS

        return self._w._params._popup._active_tab == _TAB_LABELS[1]

    def select_add_parameter_tab(self, label: str) -> "AppDriver":
        """Click one of the popup's own "Standard"/"Custom" tab buttons."""
        from ui_qt.add_parameter_popup import _TAB_LABELS

        popup = self._w._params._popup
        button = popup._tab_strip._buttons[_TAB_LABELS.index(label)]
        self._qtbot.mouseClick(button, Qt.LeftButton)
        return self

    def type_custom_parameter_name(self, text: str) -> "AppDriver":
        """Replace the Custom tab's Name field."""
        popup = self._w._params._popup
        popup._form_name.clear()
        self._qtbot.keyClicks(popup._form_name, text)
        return self

    def type_custom_parameter_unit(self, text: str) -> "AppDriver":
        """Replace the Custom tab's (optional) Unit field."""
        popup = self._w._params._popup
        popup._form_unit.clear()
        self._qtbot.keyClicks(popup._form_unit, text)
        return self

    def select_custom_parameter_type(self, label: str) -> "AppDriver":
        """Click one of the Custom tab's five type buttons (e.g. "Scalar",
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
        """Click "Add" on the Custom tab's form, committing the composed key
        and the selected type's seed value."""
        self._qtbot.mouseClick(self._w._params._popup._form_add, Qt.LeftButton)
        return self

    def cancel_custom_parameter_form(self) -> "AppDriver":
        """Click "Cancel" on the Custom tab's form, switching back to
        Standard without creating anything."""
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
        (no missing fields, or the model doesn't qualify)."""
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

    # -- Card-header inline rename editor ------------------------------------

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
        :meth:`diagnostics_collapse_all_text`)."""
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

    def click_workspace_new_from_file(self) -> "AppDriver":
        """Click the New chooser's "From existing file…" row on the Workspace page."""
        self._qtbot.mouseClick(self._w._workspace._new_from_file_button, Qt.LeftButton)
        return self

    def workspace_new_from_file_texts(self) -> tuple[str, str]:
        """The (label, descriptor) texts of the New chooser's
        from-existing-file row."""
        ws = self._w._workspace
        return ws._new_from_file_button.text(), ws._new_from_file_descriptor.text()

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

    def save(self) -> "AppDriver":
        """Click the toolbar's Save button: writes to the backing file, or
        opens Save As first for a never-saved document (tests stub the
        dialog)."""
        self._w._save_action.trigger()
        return self

    def save_enabled(self) -> bool:
        return self._w._save_action.isEnabled()

    def save_shortcut(self) -> str:
        """Save's key, read off the action rather than a QShortcut -- that is
        where it lives, so that it inherits the action's enabled state."""
        return self._w._save_action.shortcut().toString()

    def open_shortcut(self) -> str:
        return self._w._open_shortcut.key().toString()

    def press_open_shortcut(self) -> "AppDriver":
        """Fire Ctrl+O without a synthesised key press, so the test does not
        depend on the offscreen window holding real Qt focus."""
        self._w._open_shortcut.activated.emit()
        return self

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
        """The Inspector validity badge: '', 'Valid', 'Warning', 'Invalid'
        or 'Not checked' (bpx aborted before judging this parameter)."""
        return self._w._inspector._card._badge.text()

    def validity_tooltip(self) -> str:
        """The Inspector validity badge's hover: why "Not checked" reads that
        way. Empty for every verdict whose own word says it."""
        return self._w._inspector._card._badge.toolTip()

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
        colours its *name* span (the first, bold one) with the muted colour
        rather than the normal one -- a committed-null value renders
        grey/muted. Checking only the leading span matters: the unit
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
        severity dot (page-visible issues only, not validator-verbatim). The
        row's own ``text()`` carries only the label now (the marker is a
        painted ``<img>`` in :data:`~ui_qt.parameter_row.HTML_ROLE`), so this
        checks the HTML for either severity colour's dot rather than a
        plain-text glyph."""
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

    def issues_section_visible(self) -> bool:
        """Whether the Inspector's Issues section is meant to be showing.

        Reads ``isVisibleTo`` against the Inspector so the answer is
        layout-truth even in a headless run where nothing is on screen.
        """
        panel = self._w._inspector
        return panel._issues_section.isVisibleTo(panel)

    def issues_header_count(self) -> int:
        """The Issues section's title-row count NUMBER ('' -> 0).

        Deliberately distinct from :meth:`issues_list_count` (which reads
        the section's own row *list*) -- the two are set by different code
        paths (``InspectorPanel._show_issue_rows``'s label vs
        ``IssuesView.show_issues``'s row-building) and must always agree.
        Two Inspector call-sites once pushed the *unmerged* diagnostic count
        into the old tab badge while the list stayed merged, so this reader
        exists specifically to catch that class of bug -- a test using only
        ``issues_list_count()`` cannot see it.
        """
        text = self._w._inspector._issues_count.text()
        return int(text) if text else 0

    def issues_list_count(self) -> int:
        return self._w._inspector._issues_view._list.count()

    def issues_list_texts(self) -> list[str]:
        """Text of every row currently listed in the Issues section (a
        null/bad FloatInt value's float_type+int_type pair displays merged
        to one row here)."""
        lst = self._w._inspector._issues_view._list
        return [lst.item(i).text() for i in range(lst.count())]

    def documentation_section_visible(self) -> bool:
        """Whether the Inspector's Documentation section is meant to be
        showing (see :meth:`issues_section_visible` for the idiom)."""
        panel = self._w._inspector
        return panel._docs_section.isVisibleTo(panel)

    def documentation_collapsed(self) -> bool:
        return self._w._inspector._docs_section.is_collapsed

    def validation_issue_count(self) -> int:
        """Count of issue rows in the stream only (task/header/clear-line/
        message rows excluded)."""
        return len(self._validation_rows("issue"))

    def validation_outstanding_count(self) -> int:
        """Count of task rows in the stream only."""
        return len(self._validation_rows("task"))

    def validation_message(self) -> str | None:
        """Visible full-page placeholder text ("No document open"), or None
        once a document is open -- the page then always shows the stream
        (a clean or Partial document gets its own pinned row inside it
        instead, see :meth:`diagnostics_all_clear_text`)."""
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
        if not ws._info_empty.isHidden():
            return ws._info_empty.text()
        lines = [f"Title: {ws._info_title.text()}"]
        if ws._main_card.validity_text():
            lines.append(f"Validity: {ws._main_card.validity_text()}")
        lines.append(f"Description: {ws._info_description.text()}")
        lines.append(f"Citation: {ws._info_citation.text()}")
        lines.append(f"Model: {ws._fact_model.text()}")
        lines.append(f"Read as: {ws._fact_read_as.value_text()}")
        lines.append(f"Checked: {ws._fact_checked.value_text()}")
        lines.append(f"Contents: {ws._fact_contents.text()}")
        if not ws._fact_from.isHidden():
            # The full path (the label itself elides), plus the disk facts.
            lines.append(
                f"From: {ws._fact_from_path.toolTip()} {ws._fact_from_meta.text()}".rstrip()
            )
        lines.append(f"Status: {ws._fact_status.text()}")
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
        """Whether the import-first dropzone is currently visible.

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
    # ValidationEmptyState (zero-run Validation container)
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
