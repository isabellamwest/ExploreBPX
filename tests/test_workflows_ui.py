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
_DIFFUSIVITY = ("Parameterisation", "Negative electrode", "Diffusivity [m2.s-1]")


# ---------------------------------------------------------------------------
# Mode strip: a union-typed field's representations, driven through the UI
# ---------------------------------------------------------------------------

def test_mode_strip_switch_alone_commits_nothing(app_driver, spm_workfile):
    """Switching mode is not an edit: it must not dirty the card, must not
    flash the badge, and a bare Enter after it must write nothing."""
    d = app_driver
    d.open(spm_workfile).go_to(_DIFFUSIVITY)
    assert d.mode_labels() == ("FloatInt", "Function", "InterpolatedTable")
    assert d.current_mode() == "FloatInt"
    assert d.validity() == "Valid"

    d.select_mode("Function")           # a real click on the strip button
    d.wait_for_live_validation()

    assert d.current_mode() == "Function"
    assert d.validity() == "Valid"      # no preview kicked at the empty body
    d.commit()
    assert d.undo_enabled() is False    # nothing entered the undo stack


def test_mode_strip_converts_a_number_into_an_interpolated_table(
    app_driver, spm_workfile, main_window
):
    d = app_driver
    d.open(spm_workfile).go_to(_DIFFUSIVITY)

    d.select_mode("InterpolatedTable")
    d.add_grid_row().set_grid_cell(0, 0, "0.1").set_grid_cell(0, 1, "5e-14")
    d.commit_grid()

    stored = main_window._state.active.document.raw["Parameterisation"][
        "Negative electrode"
    ]["Diffusivity [m2.s-1]"]
    assert stored == {"x": [0.1], "y": [5e-14]}
    assert d.current_mode() == "InterpolatedTable"


def test_an_invalid_expression_still_commits_for_repair(app_driver, spm_workfile):
    """A card never judges *legality*: an unparseable expression commits, and
    the validator -- not the card -- reports it."""
    d = app_driver
    d.open(spm_workfile).go_to(_DIFFUSIVITY).select_mode("Function")

    d.edit_field("not a function!!")
    d.wait_for_live_validation()
    assert d.validity() == "Invalid"

    d.commit()
    assert d.field_value() == "not a function!!"
    assert d.validation_issue_count() >= 1


def test_unrepresentable_value_opens_raw_and_blocks_a_broken_commit(
    app_driver, spm_with_ragged_table_path, main_window
):
    """The one card that gates on *syntax*. Unparseable JSON has no value to
    commit; writing its text as a string would destroy the stored table."""
    d = app_driver
    d.open(spm_with_ragged_table_path).go_to(_DIFFUSIVITY)

    assert d.current_mode() == "Raw"
    assert d.mode_labels()[-1] == "Raw"   # Raw appended only when unrepresentable
    assert d.commit_blocked_reason() is None

    stored = lambda: main_window._state.active.document.raw["Parameterisation"][
        "Negative electrode"
    ]["Diffusivity [m2.s-1]"]
    assert stored() == {"x": [0, 1], "y": [1]}

    d.set_raw_json('{"x": [0,1], "y": [1]')      # broken
    reason = d.commit_blocked_reason()
    assert reason is not None and "Not valid JSON" in reason

    d.commit()

    assert stored() == {"x": [0, 1], "y": [1]}   # untouched, not a broken string
    assert d.undo_enabled() is False

    d.set_raw_json('{"x": [0,1], "y": [1,2]}')   # repaired
    assert d.commit_blocked_reason() is None
    d.commit()

    assert stored() == {"x": [0, 1], "y": [1, 2]}
    assert d.current_mode() == "InterpolatedTable"
    assert "Raw" not in d.mode_labels()          # representable now


def test_a_blocked_draft_holds_the_badge_rather_than_previewing_a_stale_value(
    app_driver, spm_with_ragged_table_path
):
    """While the Raw text is unparseable there is no value to validate, so the
    badge must not report the last representable one as "Valid"."""
    d = app_driver
    d.open(spm_with_ragged_table_path).go_to(_DIFFUSIVITY)
    before = d.validity()

    d.set_raw_json("{definitely not json")
    d.wait_for_live_validation()

    assert d.validity() == before


# ---------------------------------------------------------------------------
# Series grid: edit a cell -> validation reacts -> undo restores, end to end
#
# These scenarios used to run against ``SeriesCard`` via ``_TIME_SERIES``
# (any array of a Validation run). Since the ExperimentCard phase, navigating
# there opens the unified ``ExperimentCard`` instead -- ``SeriesCard`` is kept
# (still directly constructible/testable, see ``test_series_card.py``) but is
# no longer reachable through this navigation path, so the same guarantees
# (edit+undo, add/remove, escape-revert, the cell-editor-vs-grid keyboard
# layering) now live in ``tests/test_experiment_card.py`` instead.
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Flagship 1: open -> select -> edit -> validation updates -> issues update
# ---------------------------------------------------------------------------

def test_flagship_edit_updates_validation_and_issues(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    d.go_to(_CAPACITY)
    assert d.inspector_title() == "Nominal cell capacity [A.h]"
    assert d.validity() == "Valid"

    # Commit an invalid value: the validity mark flips and the Issues
    # section appears with the issue counted in its title row.
    d.edit_field("not-a-number").commit()
    assert d.validity() == "Invalid"
    assert d.issues_section_visible()
    assert d.issues_list_count() >= 1
    assert d.issues_header_count() == d.issues_list_count()

    # Repair it: validity clears and the Issues section disappears.
    d.edit_field("5.0").commit()
    assert d.validity() == "Valid"
    assert not d.issues_section_visible()
    assert d.issues_list_count() == 0


# ---------------------------------------------------------------------------
# Flagship 2: navigate from a validation issue, fix it, validation clears
# ---------------------------------------------------------------------------

def test_flagship_navigate_from_issue_and_fix(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    # Introduce a known error, then look at the document-wide Validation view.
    d.go_to(_CAPACITY).edit_field("not-a-number").commit()
    d.show_view("Diagnostics")
    assert d.validation_issue_count() >= 1

    # Move the Inspector away from the offending parameter first, so the
    # assertion below can only pass if activation itself navigates there --
    # not because the Inspector already happened to be sitting on it.
    d.go_to(_MODEL)
    assert d.inspector_title() == "Model"
    d.show_view("Diagnostics")

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
# Issues section: navigation + conditional presence
# ---------------------------------------------------------------------------

def test_issues_section_navigation_and_presence(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)

    # A valid parameter has no Issues section at all.
    d.go_to(_CAPACITY)
    assert not d.issues_section_visible()
    assert d.issues_list_count() == 0

    # An invalid parameter lists its issues; activating one navigates.
    d.edit_field("not-a-number").commit()
    assert d.issues_section_visible()
    assert d.issues_list_count() >= 1
    # The Issues section is parameter-scoped: its list only ever contains
    # issues for the currently-displayed parameter, so activation always
    # navigates to that same parameter. Unlike the flagship Validation test,
    # the navigate-away-then-activate displacement pattern is structurally
    # inapplicable here -- this assertion instead verifies that the real
    # activation signal chain fires (catching a broken/removed connection),
    # not that activation navigates across parameters.
    d.activate_first_parameter_issue()
    assert d.inspector_title() == "Nominal cell capacity [A.h]"


# ---------------------------------------------------------------------------
# Documentation section state is workspace state, not parameter state
# ---------------------------------------------------------------------------

def test_documentation_section_state_persists_and_resets(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_MODEL)

    # The resident Documentation section starts collapsed; its title row
    # toggles it open...
    assert d.documentation_section_visible()
    assert d.documentation_collapsed() is True
    d.toggle_documentation_section()
    assert d.documentation_collapsed() is False

    # ...and it stays open across parameter changes.
    d.go_to(_CAPACITY)
    assert d.documentation_collapsed() is False

    # Clicking the title row again collapses it.
    d.toggle_documentation_section()
    assert d.documentation_collapsed() is True

    # Opening a new document resets it to the collapsed default.
    d.toggle_documentation_section()
    assert d.documentation_collapsed() is False
    d.open(spm_workfile)
    assert d.documentation_collapsed() is True


_VOLTAGE_LIMIT = ("Parameterisation", "Cell", "Upper voltage cut-off [V]")
_CELL_OBJECT = ("Parameterisation", "Cell")


def test_sections_hide_without_a_parameter(app_driver, spm_workfile):
    """The sections are parameter-scoped, so they must not linger showing
    stale/empty content when the Inspector falls back to its placeholder --
    but the Documentation section's open/collapsed choice must survive the
    trip."""
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_CAPACITY)

    # Open the Documentation section...
    d.toggle_documentation_section()
    assert d.documentation_collapsed() is False

    # ...selecting an object (no parameter) hides both sections...
    d.select_object(_CELL_OBJECT)
    assert d.showing_placeholder() is True
    assert not d.documentation_section_visible()
    assert not d.issues_section_visible()

    # ...and selecting a parameter again restores it, still open.
    d.go_to(_CAPACITY)
    assert d.documentation_section_visible()
    assert d.documentation_collapsed() is False

    # Collapsing while a parameter is shown, then switching parameters,
    # must not re-open it.
    d.toggle_documentation_section()
    assert d.documentation_collapsed() is True
    d.go_to(_VOLTAGE_LIMIT)
    assert d.documentation_collapsed() is True


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


# ---------------------------------------------------------------------------
# Staged-abort masking: unjudged parameters must not badge "Valid"
# ---------------------------------------------------------------------------

_TEMPERATURE = ("State", "Initial conditions", "Initial temperature [K]")


def test_masked_section_badges_not_validated_instead_of_valid(
    app_driver, spm_workfile
):
    """bpx validates in stages, and a Parameterisation error aborts the run
    before State is ever judged (see test_gateway.py's staged-abort tests).
    A parameter bpx never judged must badge neutral "Not checked" -- a
    green "Valid" there would be a false clean bill of health."""
    d = app_driver
    d.open(spm_workfile).go_to(_TEMPERATURE)
    assert d.validity() == "Valid"

    # Break a Cell parameter: bpx now aborts before reaching State.
    d.go_to(_CAPACITY).edit_field("nonsense").commit()
    assert d.validity() == "Invalid"

    d.go_to(_TEMPERATURE)
    assert d.validity() == "Not checked"

    # The live preview of a draft is equally unjudged while the abort holds.
    d.edit_field("300")
    d.wait_for_live_validation()
    assert d.validity() == "Not checked"
    d.escape()

    # Repair the Cell parameter: State is judged again and the badge returns.
    d.go_to(_CAPACITY).edit_field("5").commit()
    assert d.validity() == "Valid"
    d.go_to(_TEMPERATURE)
    assert d.validity() == "Valid"
