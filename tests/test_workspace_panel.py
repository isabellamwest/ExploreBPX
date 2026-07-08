"""Workspace page: activity-bar entry, default landing, and info panel.

Covers Step 7 of the top-bar/workspace redesign: the Workspace page shell.
The New model-chooser (Step 8) and drag-and-drop (Step 9) are out of scope.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _fail_if_called(*args, **kwargs):
    raise AssertionError("This dialog should not have been shown")


def test_workspace_entry_exists_and_selecting_it_shows_workspace_page(app_driver):
    d = app_driver
    d.show_view("Editor")
    assert d.current_view_index() == 0

    d.show_view("Workspace")

    assert d.current_view_index() == 2
    assert d.activity_bar_selected_label() == "Workspace"


def test_app_launches_on_workspace_page_with_no_document(app_driver):
    assert app_driver.current_view_index() == 2
    assert app_driver.activity_bar_selected_label() == "Workspace"


def test_workspace_info_shows_empty_state_with_no_document(app_driver):
    assert app_driver.workspace_info_text() == "No document open"


def test_workspace_info_shows_identity_and_file_state_once_opened(
    app_driver, valid_spm_path
):
    app_driver.open(valid_spm_path)

    text = app_driver.workspace_info_text()
    assert "Title: Minimal valid SPM example" in text
    assert "Model: SPM" in text
    assert "BPX version: 1.0.0" in text
    assert f"File: {valid_spm_path.name}" in text
    assert "State: Saved" in text


def test_workspace_info_reflects_dirty_state(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()

    assert "State: Modified" in app_driver.workspace_info_text()


def test_workspace_info_returns_to_saved_after_save(app_driver, spm_workfile):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    assert "State: Modified" in d.workspace_info_text()

    d._w._save()

    assert "State: Saved" in d.workspace_info_text()


def test_workspace_info_filename_updates_after_save_as(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    d._w._state.active.backing_file = None  # force the Save As path

    new_path = tmp_path / "renamed.json"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(new_path), ""),
    )

    d._w._save()

    assert f"File: {new_path.name}" in d.workspace_info_text()
    assert "State: Saved" in d.workspace_info_text()


def test_opening_from_workspace_page_switches_to_editor_page(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    assert d.current_view_index() == 2

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    d.click_workspace_open()

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.identity_text() == "Minimal valid SPM example · SPM · BPX v1.0.0"


def test_opening_from_workspace_page_goes_through_discard_guard(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    """Open from the Workspace page reuses ``_confirm_discard_if_dirty``,
    the same guard exercised by the toolbar Open in the discard-guard tests."""
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    assert d.status_text() == f"{spm_workfile.name}  |  Modified"
    original_status = d.status_text()

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Cancel
    )
    monkeypatch.setattr(main_window_module.QFileDialog, "getOpenFileName", _fail_if_called)

    d.click_workspace_open()

    assert d.status_text() == original_status
