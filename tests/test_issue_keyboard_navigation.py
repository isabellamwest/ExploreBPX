"""Keyboard navigation of validation issues (roadmap 2.3).

Both issue lists (the document-wide ``DiagnosticsPanel`` and the
parameter-scoped ``IssuesView``) must let Enter/Return activate the selected
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
from ui_qt.issues_view import IssuesView
from ui_qt.diagnostics_panel import DiagnosticsPanel


@pytest.fixture
def invalid_document(invalid_bpx_path) -> BPXDocument:
    return BPXDocument.from_bytes(invalid_bpx_path.read_bytes(), invalid_bpx_path.name)


def _issue_rows(panel: DiagnosticsPanel):
    """Issue rows in the stream -- the page's one renderer, so it always
    contains every issue and is the right default surface here."""
    lst = panel._stream._list
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
def issues_view(qtbot) -> IssuesView:
    # The Issues view is parameter-scoped, so drive it with a parameter that has
    # an issue directly (mirroring test_ui_qt_tree_model). This is independent
    # of whether any example file happens to produce a parameter-level issue.
    path = ("Parameterisation", "Cell", "Voltage")
    parameter = ParameterItem(
        label="Voltage",
        path=path,
        kind=ParameterKind.SCALAR,
        issues=[PydanticErrorDiagnostic(raw_error={"loc": path, "msg": "Invalid"})],
    )
    view = IssuesView()
    qtbot.addWidget(view)
    view.show_issues(parameter.issues, parameter.path)
    assert view._list.count() >= 1
    return view


def _press_return(qtbot, list_widget):
    qtbot.keyClick(list_widget, Qt.Key_Return)


def test_validation_panel_enter_activates_selected_row(qtbot, validation_panel):
    received = []
    validation_panel.issue_activated.connect(received.append)

    first_issue = _issue_rows(validation_panel)[0]
    validation_panel._stream._list.setCurrentItem(first_issue)
    expected_path = first_issue.data(256)
    _press_return(qtbot, validation_panel._stream._list)

    assert received == [expected_path]


def test_validation_panel_selection_change_alone_does_not_activate(qtbot, validation_panel):
    received = []
    validation_panel.issue_activated.connect(received.append)

    validation_panel._stream._list.setCurrentItem(_issue_rows(validation_panel)[0])

    assert received == []


def test_issues_view_enter_activates_selected_row(qtbot, issues_view):
    received = []
    issues_view.issue_activated.connect(received.append)

    issues_view._list.setCurrentRow(0)
    expected_path = issues_view._list.item(0).data(256)
    _press_return(qtbot, issues_view._list)

    assert received == [expected_path]


def test_issues_view_selection_change_alone_does_not_activate(qtbot, issues_view):
    received = []
    issues_view.issue_activated.connect(received.append)

    issues_view._list.setCurrentRow(0)

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


def test_issues_view_row_tooltip_is_severity_derived_not_message_derived(issues_view):
    """The fixture's fake diagnostic carries the message "Invalid" -- if the
    tooltip were message-derived it would show something unrelated to the
    pinned, generic sentence. It must show the fixed Severity.ERROR text
    regardless."""
    from core.validation import Severity
    from ui_qt import style

    item = issues_view._list.item(0)
    assert item.toolTip() == style.severity_tooltip(Severity.ERROR)


# ----------------------------------------------------------------------
# The activation key itself. Both lists above get Return from
# ``ActivatingList`` rather than from ``QAbstractItemView``, because Qt takes
# its activation key from the platform's binding scheme and macOS's reserves
# Return for rename, mapping activation to Cmd+O. These pin the override so
# the portable behaviour cannot quietly regress back to the platform's.
# ----------------------------------------------------------------------


@pytest.fixture
def activating_list(qtbot):
    from PySide6.QtWidgets import QListWidgetItem

    from ui_qt.activating_list import ActivatingList

    widget = ActivatingList()
    qtbot.addWidget(widget)
    for text in ("first", "second"):
        widget.addItem(QListWidgetItem(text))
    return widget


def test_return_activates_the_current_row(qtbot, activating_list):
    fired = []
    activating_list.itemActivated.connect(lambda item: fired.append(item.text()))
    activating_list.setCurrentRow(1)

    qtbot.keyClick(activating_list, Qt.Key_Return)

    assert fired == ["second"]


def test_keypad_enter_activates_too(qtbot, activating_list):
    fired = []
    activating_list.itemActivated.connect(lambda item: fired.append(item.text()))
    activating_list.setCurrentRow(0)

    qtbot.keyClick(activating_list, Qt.Key_Enter, Qt.KeypadModifier)

    assert fired == ["first"]


def test_return_activates_exactly_once(qtbot, activating_list):
    """The override consumes Return rather than passing it on, so Qt's own
    activation cannot also fire on a platform whose scheme maps it."""
    fired = []
    activating_list.itemActivated.connect(fired.append)
    activating_list.setCurrentRow(0)

    qtbot.keyClick(activating_list, Qt.Key_Return)

    assert len(fired) == 1


def test_a_modified_return_is_handed_to_the_base_class(qtbot, activating_list):
    """Only the bare chord is claimed by the override. What a *modified* Return
    then does is Qt's own business and varies by platform (Windows activates on
    Shift+Return, macOS does not), so the portable thing to pin is simply that
    the override passes it down instead of swallowing it."""
    from PySide6.QtWidgets import QListWidgetItem

    from ui_qt.activating_list import ActivatingList

    reached = []

    class _Probe(ActivatingList):
        def keyPressEvent(self, event):  # noqa: N802
            ActivatingList.keyPressEvent(self, event)
            reached.append(event.key())

    widget = _Probe()
    qtbot.addWidget(widget)
    widget.addItem(QListWidgetItem("only"))
    widget.setCurrentRow(0)

    qtbot.keyClick(widget, Qt.Key_Return, Qt.ShiftModifier)

    assert Qt.Key_Return in reached


def test_return_on_an_empty_list_does_nothing(qtbot):
    from ui_qt.activating_list import ActivatingList

    widget = ActivatingList()
    qtbot.addWidget(widget)
    fired = []
    widget.itemActivated.connect(fired.append)

    qtbot.keyClick(widget, Qt.Key_Return)

    assert fired == []
