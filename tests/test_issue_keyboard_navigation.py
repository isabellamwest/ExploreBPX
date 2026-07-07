"""Keyboard navigation of validation issues (roadmap 2.3).

Both issue lists (the document-wide ``ValidationPanel`` and the
parameter-scoped ``IssuesTab``) must let Enter/Return activate the selected
row and emit ``issue_activated``, matching the existing double-click
behaviour. Arrow-key selection alone (i.e. simply moving the current row)
must not navigate.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from core.document import BPXDocument
from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem
from core.validation import PydanticErrorDiagnostic
from ui_qt.issues_tab import IssuesTab
from ui_qt.validation_panel import ValidationPanel


@pytest.fixture
def invalid_document(invalid_bpx_path) -> BPXDocument:
    return BPXDocument.from_bytes(invalid_bpx_path.read_bytes(), invalid_bpx_path.name)


@pytest.fixture
def validation_panel(qtbot, invalid_document) -> ValidationPanel:
    panel = ValidationPanel()
    qtbot.addWidget(panel)
    panel.refresh(invalid_document)
    assert panel._list.count() >= 1
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

    validation_panel._list.setCurrentRow(0)
    expected_path = validation_panel._list.item(0).data(256)
    _press_return(qtbot, validation_panel._list)

    assert received == [expected_path]


def test_validation_panel_selection_change_alone_does_not_activate(qtbot, validation_panel):
    received = []
    validation_panel.issue_activated.connect(received.append)

    validation_panel._list.setCurrentRow(0)

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
