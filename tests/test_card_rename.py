"""Tests for the card-header inline rename editor (Concept A): the pencil
button beside a renamable parameter's title, its Name/Unit/Apply row, and
the schema-fixed unit tooltip on a non-renamable parameter's card.

This is the single rename surface for a User-defined parameter -- also
reachable (opened/focused, not reimplemented) via the parameter-list row's
"Rename..." context-menu action; see test_parameter_row_actions.py for the
menu side and this file for the card side plus their integration.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from ui_qt import style

_CELL = ("Parameterisation", "Cell")
_USER_DEFINED = ("Parameterisation", "User-defined")


@pytest.fixture
def user_defined_window(app_driver, spm_workfile):
    """A live window with two User-defined parameters (one with a unit)."""
    d = app_driver
    d.open(spm_workfile)
    window = d._w
    window._on_add_section_requested(("Parameterisation",), "User-defined")
    window._on_add_parameter_requested(_USER_DEFINED, "Foo [V]", 0.0)
    window._on_add_parameter_requested(_USER_DEFINED, "Bar", 0.0)
    return d


# ---------------------------------------------------------------------------
# Pencil presence: renamable (User-defined) vs schema-fixed
# ---------------------------------------------------------------------------


def test_pencil_present_for_user_defined_parameter(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    assert d.card_rename_pencil_present() is True


def test_pencil_absent_for_schema_parameter(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_CELL + ("Reference temperature [K]",))
    assert d.card_rename_pencil_present() is False


def test_schema_parameter_unit_carries_fixed_tooltip(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile)
    d.go_to(_CELL + ("Reference temperature [K]",))
    assert d.card_unit_tooltip() == style.FIXED_UNIT_TOOLTIP


def test_user_defined_parameter_unit_carries_no_tooltip(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    assert d.card_unit_tooltip() in (None, "")


# ---------------------------------------------------------------------------
# Expanding the row: prefilled from the current label
# ---------------------------------------------------------------------------


def test_pencil_click_expands_row_prefilled_with_name_and_unit(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    assert d.card_rename_row_visible() is False

    d.click_card_rename_pencil()

    assert d.card_rename_row_visible() is True
    assert d.card_rename_name_text() == "Foo"
    assert d.card_rename_unit_text() == "V"


def test_pencil_click_expands_row_prefilled_with_no_unit(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Bar",))

    d.click_card_rename_pencil()

    assert d.card_rename_name_text() == "Bar"
    assert d.card_rename_unit_text() == ""


# ---------------------------------------------------------------------------
# Apply: renames the key, the card updates
# ---------------------------------------------------------------------------


def test_apply_with_unit_renames_key_and_card_updates(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    d.click_card_rename_pencil()
    d.type_card_rename_name("Voltage offset")
    d.type_card_rename_unit("mV")

    d.click_card_rename_apply()

    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Voltage offset [mV]" in bucket
    assert "Foo [V]" not in bucket
    assert d.inspector_title() == "Voltage offset [mV]"
    # A freshly built card starts with its rename row collapsed again.
    assert d.card_rename_row_visible() is False


def test_apply_without_unit_renames_key_with_no_bracket(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Bar",))
    d.click_card_rename_pencil()
    d.type_card_rename_name("Baz")
    d.click_card_rename_apply()

    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Baz" in bucket
    assert "Bar" not in bucket
    assert d.inspector_title() == "Baz"


def test_rename_is_undoable_end_to_end(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    d.click_card_rename_pencil()
    d.type_card_rename_name("Renamed")  # unit "V" stays prefilled -> "Renamed [V]"
    d.click_card_rename_apply()
    assert "Renamed [V]" in d._w._state.active.document.raw["Parameterisation"]["User-defined"]

    d.undo()

    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Foo [V]" in bucket
    assert "Renamed [V]" not in bucket


# ---------------------------------------------------------------------------
# Refusals: surfaced inline, row stays open, nothing changes
# ---------------------------------------------------------------------------


def test_unchanged_name_shows_inline_error_and_keeps_row_open(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    d.click_card_rename_pencil()

    d.click_card_rename_apply()  # nothing edited: same name, same unit

    assert d.card_rename_error_text() == "Name is unchanged."
    assert d.card_rename_row_visible() is True
    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Foo [V]" in bucket


def test_renaming_to_a_taken_sibling_name_shows_inline_error(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    d.click_card_rename_pencil()
    d.type_card_rename_name("Bar")
    d.type_card_rename_unit("")

    d.click_card_rename_apply()

    assert d.card_rename_error_text() == "“Bar” already exists here."
    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Foo [V]" in bucket
    assert list(bucket).count("Bar") == 1


# ---------------------------------------------------------------------------
# Cancel: collapses without changing anything
# ---------------------------------------------------------------------------


def test_cancel_hides_row_without_changing_the_document(user_defined_window):
    d = user_defined_window
    d.go_to(_USER_DEFINED + ("Foo [V]",))
    d.click_card_rename_pencil()
    d.type_card_rename_name("Should not stick")

    d.click_card_rename_cancel()

    assert d.card_rename_row_visible() is False
    bucket = d._w._state.active.document.raw["Parameterisation"]["User-defined"]
    assert "Foo [V]" in bucket


# ---------------------------------------------------------------------------
# Integration: the row menu's "Rename..." opens this very editor
# ---------------------------------------------------------------------------


def test_row_menu_rename_action_opens_the_same_card_editor(user_defined_window):
    d = user_defined_window
    d.select_object(_USER_DEFINED)
    labels = d.parameter_labels()
    index = next(i for i, label in enumerate(labels) if label.startswith("Foo"))

    d.trigger_parameter_row_menu_action(index, "Rename…")

    assert d.shown_parameter_path() == _USER_DEFINED + ("Foo [V]",)
    assert d.card_rename_row_visible() is True
    assert d.card_rename_name_text() == "Foo"
    assert d.card_rename_unit_text() == "V"
