"""Keyboard navigation of validation issues (roadmap 2.3).

Both issue lists (the document-wide ``DiagnosticsPanel`` and the
parameter-scoped ``IssuesTab``) must let Enter/Return activate the selected
row and emit ``issue_activated``, matching the existing double-click
behaviour. Arrow-key selection alone (i.e. simply moving the current row)
must not navigate.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from core import completion, page_buckets
from core.document import BPXDocument
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from core.validation import PydanticErrorDiagnostic
from ui_qt import diagnostics_panel as vp
from ui_qt.issues_tab import IssuesTab
from ui_qt.diagnostics_panel import DiagnosticsPanel


@pytest.fixture
def invalid_document(invalid_bpx_path) -> BPXDocument:
    return BPXDocument.from_bytes(invalid_bpx_path.read_bytes(), invalid_bpx_path.name)


def _issue_rows(panel: DiagnosticsPanel):
    """Issue rows in the All-sections view -- the backup view that always
    contains every issue, so it is the right default surface here."""
    lst = panel._all_view._list
    return [lst.item(i) for i in range(lst.count()) if lst.item(i).data(vp._KIND_ROLE) == "issue"]


@pytest.fixture
def validation_panel(qtbot, invalid_document) -> DiagnosticsPanel:
    panel = DiagnosticsPanel()
    qtbot.addWidget(panel)
    raw = invalid_document.raw
    model = None
    tasks = completion.document_completion(raw)
    partition = completion.partition_issues(invalid_document, tasks)
    buckets = page_buckets.bucket_page_content(raw, model, partition, tasks)
    panel.refresh(buckets, partition, model)
    assert _issue_rows(panel), "fixture premise: the invalid fixture must draw at least one Issue"
    return panel


@pytest.fixture
def issues_tab(qtbot) -> IssuesTab:
    # The Issues tab is parameter-scoped, so drive it with a parameter that has
    # an issue directly (mirroring test_ui_qt_tree_model). This is independent
    # of whether any example file happens to produce a parameter-level issue.
    path = ("Parameterisation", "Cell", "Voltage")
    parameter = ParameterItem(
        label="Voltage",
        path=path,
        kind=ParameterKind.SCALAR,
        issues=[PydanticErrorDiagnostic(raw_error={"loc": path, "msg": "Invalid"})],
    )
    tab = IssuesTab()
    qtbot.addWidget(tab)
    tab.show_parameter(parameter)
    assert tab._list.count() >= 1
    return tab


def _press_return(qtbot, list_widget):
    qtbot.keyClick(list_widget, Qt.Key_Return)


def test_validation_panel_enter_activates_selected_row(qtbot, validation_panel):
    received = []
    validation_panel.issue_activated.connect(received.append)

    first_issue = _issue_rows(validation_panel)[0]
    validation_panel._all_view._list.setCurrentItem(first_issue)
    expected_path = first_issue.data(256)
    _press_return(qtbot, validation_panel._all_view._list)

    assert received == [expected_path]


def test_validation_panel_selection_change_alone_does_not_activate(qtbot, validation_panel):
    received = []
    validation_panel.issue_activated.connect(received.append)

    validation_panel._all_view._list.setCurrentItem(_issue_rows(validation_panel)[0])

    assert received == []


def test_issues_tab_enter_activates_selected_row(qtbot, issues_tab):
    received = []
    issues_tab.issue_activated.connect(received.append)

    issues_tab._list.setCurrentRow(0)
    expected_path = issues_tab._list.item(0).data(256)
    _press_return(qtbot, issues_tab._list)

    assert received == [expected_path]


def test_issues_tab_selection_change_alone_does_not_activate(qtbot, issues_tab):
    received = []
    issues_tab.issue_activated.connect(received.append)

    issues_tab._list.setCurrentRow(0)

    assert received == []


# --- tooltip vocabulary (polish round): severity/task-kind derived, never --
# --- message-derived ---------------------------------------------------------


def test_validation_panel_issue_row_tooltips_match_their_severity_role(validation_panel):
    """Drift-safe by construction: the tooltip is looked up from the same
    severity ("error"/"warning") already stashed on the row for the dot
    icon, via ``style.severity_tooltip`` -- never from the row's own
    verbatim validator message."""
    from core.validation import Severity
    from ui_qt import parameter_row, style

    rows = _issue_rows(validation_panel)
    assert rows  # fixture premise
    for item in rows:
        severity = Severity.ERROR if item.data(parameter_row.SEVERITY_ROLE) == "error" else Severity.WARNING
        assert item.toolTip() == style.severity_tooltip(severity)


def test_issues_tab_row_tooltip_is_severity_derived_not_message_derived(issues_tab):
    """The fixture's fake diagnostic carries the message "Invalid" -- if the
    tooltip were message-derived it would show something unrelated to the
    pinned, generic sentence. It must show the fixed Severity.ERROR text
    regardless."""
    from core.validation import Severity
    from ui_qt import style

    item = issues_tab._list.item(0)
    assert item.toolTip() == style.severity_tooltip(Severity.ERROR)
