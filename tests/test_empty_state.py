"""No-document empty-state polish (Step 10 of the top-bar/workspace redesign).

Covers three surfaces:
  - the Validation activity-bar badge (no badge/count at zero issues)
  - the Validation page's own empty-state message
  - the Editor page's empty-state hint, shown only with no document
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


# --- Validation activity-bar badge --------------------------------------


def test_validation_badge_shows_no_count_with_no_document(app_driver):
    assert app_driver.validation_badge_count() == 0
    assert app_driver.validation_badge_severity() is None


def test_validation_badge_shows_no_count_for_a_clean_document(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)

    assert app_driver.validation_badge_count() == 0
    assert app_driver.validation_badge_severity() is None


def test_validation_badge_shows_count_once_an_issue_exists(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field("not-a-number").commit()

    assert d.validation_badge_count() > 0
    assert d.validation_badge_severity() == "error"


# --- Validation page empty state ----------------------------------------


def test_validation_page_shows_no_document_message(app_driver):
    assert app_driver.validation_message() == "No document open"
    assert app_driver.validation_issue_count() == 0


def test_validation_page_shows_no_issues_message_for_a_clean_document(
    app_driver, valid_spm_path
):
    app_driver.open(valid_spm_path)

    assert app_driver.validation_message() == "✓ No issues"


def test_validation_page_shows_the_list_once_an_issue_exists(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field("not-a-number").commit()

    assert d.validation_message() is None
    assert d.validation_issue_count() >= 1


# --- Editor page empty-state hint ----------------------------------------


def test_editor_page_shows_empty_state_hint_with_no_document(app_driver):
    d = app_driver
    d.show_view("Editor")

    assert d.editor_showing_empty_state() is True
    assert "Workspace" in d.editor_empty_state_text()


def test_editor_page_hides_hint_once_a_document_is_opened(app_driver, valid_spm_path):
    d = app_driver
    d.show_view("Editor")
    assert d.editor_showing_empty_state() is True

    d.open(valid_spm_path)

    assert d.editor_showing_empty_state() is False


def test_editor_page_hides_hint_for_a_newly_created_document(app_driver):
    d = app_driver

    d.click_workspace_new("SPM")

    assert d.editor_showing_empty_state() is False


def test_editor_page_shows_hint_again_after_returning_to_no_document_state(
    app_driver, valid_spm_path
):
    """Not a real user flow today (there is no "close document" action), but
    guards against the hint being wired as a one-shot rather than driven by
    live document state."""
    d = app_driver
    d.open(valid_spm_path)
    assert d.editor_showing_empty_state() is False

    d._w._state.close()
    d._w._refresh_all()

    assert d.editor_showing_empty_state() is True
