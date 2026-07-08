"""Cross-tab navigation reveals must switch to the Editor page.

Covers Step 4 of the top-bar/workspace redesign: the tree, parameter list and
Inspector only live on the Editor page of the workspace stack. Since Search is
always live in the top bar, a navigation request while on the Validation page
(from Search, a validation issue, or the Issues tab) must first switch the
workspace back to Editor -- both the ``QStackedWidget`` page and the activity
bar's selected entry -- before revealing the target, otherwise the reveal
lands on hidden widgets and the user sees nothing happen.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
_MODEL = ("Header", "Model")


def test_navigate_to_switches_from_validation_to_editor_page(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    d.show_view("Validation")
    assert d.current_view_index() == 1
    assert d.activity_bar_selected_label() == "Validation"

    d.go_to(_CAPACITY)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.inspector_title() == "Nominal cell capacity [A.h]"
    assert d.editor_showing_empty_state() is False


def test_navigate_while_already_on_editor_stays_on_editor(app_driver, valid_spm_path):
    d = app_driver
    d.open(valid_spm_path)
    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"

    d.go_to(_CAPACITY)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.inspector_title() == "Nominal cell capacity [A.h]"
    assert d.editor_showing_empty_state() is False


def test_activating_validation_issue_switches_back_to_editor_page(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field("not-a-number").commit()

    # Move focus to a different parameter so a later match can only be
    # explained by the issue activation below, not a stale reveal.
    d.go_to(_MODEL)
    assert d.inspector_title() == "Model"
    d.show_view("Validation")
    assert d.current_view_index() == 1

    d.activate_validation_issue(_CAPACITY)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.inspector_title() == "Nominal cell capacity [A.h]"
    assert d.editor_showing_empty_state() is False
