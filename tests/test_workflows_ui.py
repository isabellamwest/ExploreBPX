"""UI workflow / wiring tests, driven entirely through :class:`AppDriver`.

These are a deliberately small set of end-to-end tests that protect
user-visible behaviour and the signal wiring that connects the UI to the core.
They assert only on what a user can observe (badge text, tab labels, list
counts, the window title) and drive the app through real interactions, so they
survive internal refactors: if a widget moves, only ``ui_driver.py`` changes.

The behavioural depth (validation rules, save formats, issue resolution) lives
in ``test_workflows_behaviour.py``; here we confirm the wiring delivers it.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

_MODEL = ("Header", "Model")
_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


# ---------------------------------------------------------------------------
# Flagship 1: open -> select -> edit -> validation updates -> issues update
# ---------------------------------------------------------------------------

def test_flagship_edit_updates_validation_and_issues(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    d.go_to(_CAPACITY)
    assert d.inspector_title() == "Nominal cell capacity [A.h]"
    assert d.validity() == "Valid"

    # Commit an invalid value: the badge flips and the Issues tab counts it.
    d.edit_field("not-a-number").commit()
    assert d.validity() == "Invalid"
    assert d.issues_tab_count() >= 1
    assert "Issues (" in d.issues_tab_label()

    # Repair it: validity clears and the Issues tab empties.
    d.edit_field("5.0").commit()
    assert d.validity() == "Valid"
    assert d.issues_tab_count() == 0


# ---------------------------------------------------------------------------
# Flagship 2: navigate from a validation issue, fix it, validation clears
# ---------------------------------------------------------------------------

def test_flagship_navigate_from_issue_and_fix(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    # Introduce a known error, then look at the document-wide Validation view.
    d.go_to(_CAPACITY).edit_field("not-a-number").commit()
    d.show_view("Validation")
    assert d.validation_issue_count() >= 1

    # Activating the issue navigates the Inspector to the offending parameter.
    d.activate_first_validation_issue()
    assert d.inspector_title() == "Nominal cell capacity [A.h]"
    assert d.validity() == "Invalid"

    # Fixing it clears both the badge and the Validation list.
    d.edit_field("5.0").commit()
    assert d.validity() == "Valid"
    assert d.validation_issue_count() == 0


# ---------------------------------------------------------------------------
# Live validation + Escape recovery (the one timing-dependent workflow)
# ---------------------------------------------------------------------------

def test_live_validation_updates_then_escape_restores(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_CAPACITY)
    assert d.validity() == "Valid"

    # Typing an invalid draft updates the badge live, without committing.
    d.edit_field("not-a-number").wait_for_live_validation()
    assert d.validity() == "Invalid"

    # Escape discards the draft and restores the committed (valid) state.
    d.escape()
    assert d.validity() == "Valid"
    assert d.field_value() == 5.0


def test_committed_invalid_value_stays_editable_and_recoverable(app_driver, spm_workfile):
    """A committed invalid value must reopen in an editable card (never trap the
    user), and Escape must restore the committed value."""
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_CAPACITY).edit_field("trapme").commit()

    assert d.validity() == "Invalid"
    assert d.card_is_editable()

    # Start a new draft, then Escape back to the committed invalid value.
    d.edit_field("5.0")
    d.escape()
    assert d.field_value() == "trapme"
    assert d.validity() == "Invalid"


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

def test_search_navigates_to_parameter(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.choose_search_result(_CAPACITY)
    assert d.inspector_title() == "Nominal cell capacity [A.h]"


def test_search_navigates_to_object(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.choose_search_result(("Parameterisation", "Cell"))
    assert d.tree_selection_label() == "Cell"
    # An object-level navigation shows the Inspector placeholder.
    assert d.showing_placeholder() is True


# ---------------------------------------------------------------------------
# Navigation reveals the target in the structure tree
# ---------------------------------------------------------------------------

def test_navigation_reveals_owning_object_in_tree(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_CAPACITY)
    # The owning object is selected and its ancestor is expanded.
    assert d.tree_selection_label() == "Cell"
    assert d.tree_path_is_expanded(("Parameterisation",)) is True


def test_focus_search_selects_existing_text(main_window, spm_workfile):
    main_window.open_document(spm_workfile)
    main_window._search.setText("abc")
    main_window._focus_search()
    # Focusing selects the existing text so it can be replaced immediately.
    assert main_window._search.selectedText() == "abc"


# ---------------------------------------------------------------------------
# Issues tab: navigation + placeholders
# ---------------------------------------------------------------------------

def test_issues_tab_navigation_and_placeholders(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    # A valid parameter shows the explanatory 'no issues' placeholder.
    d.go_to(_CAPACITY)
    assert d.issues_tab_count() == 0
    assert "No validation issues" in (d.issues_tab_message() or "")

    # An invalid parameter lists its issues; activating one navigates.
    d.edit_field("not-a-number").commit()
    assert d.issues_tab_count() >= 1
    d.activate_first_parameter_issue()
    assert d.inspector_title() == "Nominal cell capacity [A.h]"


# ---------------------------------------------------------------------------
# Secondary workspace is workspace state, not parameter state
# ---------------------------------------------------------------------------

def test_secondary_workspace_persists_and_resets(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_MODEL)

    # Opening the Issues tab expands the workspace...
    d.click_issues_tab()
    assert d.secondary_expanded() is True

    # ...and it stays open across parameter changes.
    d.go_to(_CAPACITY)
    assert d.secondary_expanded() is True

    # Clicking the active tab collapses it.
    d.click_issues_tab()
    assert d.secondary_expanded() is False

    # Opening a new document resets it to the collapsed default.
    d.click_issues_tab()
    assert d.secondary_expanded() is True
    d.open(spm_workfile)
    assert d.secondary_expanded() is False


# ---------------------------------------------------------------------------
# Placeholder / no-document states
# ---------------------------------------------------------------------------

def test_fresh_window_has_no_document(app_driver):
    assert app_driver.has_document() is False
    assert app_driver.window_title() == "ExploreBPX"


def test_selecting_object_without_parameter_shows_placeholder(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.select_object(("Parameterisation", "Cell"))
    assert d.showing_placeholder() is True
    assert d.parameter_labels()  # the object's parameter list is populated
