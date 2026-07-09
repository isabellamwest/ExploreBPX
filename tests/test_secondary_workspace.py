"""Unit tests for `SecondaryWorkspace`'s expanded/suspended state machine.

`SecondaryWorkspace` separates the user's *intent* (want-open, set only by
`open`/`collapse`/a tab click) from its rendered *visibility*, which is also
overridden by `suspend`/`resume` while there is no parameter to scope the
content to. These tests exercise every transition directly against the
widget; `test_workflows_ui.py` covers the same behaviour end-to-end through
the Inspector.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel

from ui_qt.secondary_workspace import SecondaryWorkspace


@pytest.fixture
def workspace(qtbot) -> SecondaryWorkspace:
    ws = SecondaryWorkspace()
    qtbot.addWidget(ws)
    ws.add_tab("issues", "Issues", QLabel("issues content"))
    ws.add_tab("other", "Other", QLabel("other content"))
    return ws


def _checked(ws: SecondaryWorkspace, tab_id: str) -> bool:
    return ws._buttons[tab_id].isChecked()


def test_initial_state_is_collapsed_with_no_active_tab(workspace):
    assert workspace.is_expanded is False
    assert workspace.active_id is None
    assert _checked(workspace, "issues") is False


def test_open_expands_and_activates(workspace):
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.open("issues")

    assert workspace.is_expanded is True
    assert workspace.active_id == "issues"
    assert _checked(workspace, "issues") is True
    assert received == [True]


def test_tab_click_on_active_tab_while_expanded_collapses(workspace):
    workspace.open("issues")
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace._buttons["issues"].click()

    assert workspace.is_expanded is False
    assert workspace.active_id == "issues"  # active tab remembered, just collapsed
    assert _checked(workspace, "issues") is False
    assert received == [False]


def test_collapse_collapses(workspace):
    workspace.open("issues")
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.collapse()

    assert workspace.is_expanded is False
    assert received == [False]


def test_suspend_force_collapses_without_touching_intent_or_active_tab(workspace):
    workspace.open("issues")
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.suspend()

    assert workspace.is_expanded is False
    assert workspace.active_id == "issues"
    assert _checked(workspace, "issues") is False
    assert received == [False]


def test_suspend_while_already_collapsed_emits_nothing(workspace):
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.suspend()

    assert workspace.is_expanded is False
    assert received == []


def test_resume_restores_an_expanded_intent(workspace):
    workspace.open("issues")
    workspace.suspend()
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.resume()

    assert workspace.is_expanded is True
    assert workspace.active_id == "issues"
    assert _checked(workspace, "issues") is True
    assert received == [True]


def test_resume_restores_a_collapsed_intent(workspace):
    workspace.open("issues")
    workspace.collapse()  # intent: collapsed, tab stays remembered as active
    workspace.suspend()
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.resume()

    assert workspace.is_expanded is False
    assert received == []  # already invisible before and after resume


def test_resume_is_idempotent_when_not_suspended(workspace):
    """A direct parameter-to-parameter reveal, with no intervening
    placeholder, must never touch visibility or emit."""
    workspace.open("issues")
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.resume()

    assert workspace.is_expanded is True
    assert received == []


def test_reset_returns_to_collapsed_default(workspace):
    workspace.open("issues")
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.reset()

    assert workspace.is_expanded is False
    assert workspace.active_id is None
    assert _checked(workspace, "issues") is False
    assert received == [False]


def test_reset_also_clears_suspension(workspace):
    workspace.open("issues")
    workspace.suspend()

    workspace.reset()
    workspace.resume()  # must be a no-op: reset already cleared suspension

    assert workspace.is_expanded is False


def test_open_while_suspended_records_intent_without_visibly_expanding(workspace):
    """Reachable in the live app: the tab strip stays visible and clickable
    even while the Inspector shows its placeholder (no parameter selected),
    so a user can click a tab before ever selecting a parameter. The click
    must be remembered, not lost, but must not visibly expand the drawer
    over placeholder content that belongs to no parameter."""
    workspace.suspend()
    received = []
    workspace.expanded_changed.connect(received.append)

    workspace.open("issues")

    assert workspace.is_expanded is False
    assert workspace.active_id == "issues"
    assert _checked(workspace, "issues") is False
    assert received == []

    workspace.resume()
    assert workspace.is_expanded is True
    assert _checked(workspace, "issues") is True
