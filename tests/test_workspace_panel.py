"""Workspace page: activity-bar entry, default landing, info panel and New chooser.

Covers Step 7 (the Workspace page shell) and Step 8 (the inline New
model-chooser) of the top-bar/workspace redesign. Drag-and-drop (Step 9) is
out of scope.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtWidgets import QLabel, QPushButton

import ui_qt.main_window as main_window_module
import ui_qt.workspace_panel as workspace_panel_module
from core.document_factory import SUPPORTED_MODELS

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


def test_new_chooser_offers_exactly_the_supported_models(app_driver):
    assert sorted(app_driver.workspace_new_model_options()) == sorted(SUPPORTED_MODELS)


def test_new_chooser_renders_name_only_for_a_model_with_no_descriptor(qtbot, monkeypatch):
    """A model absent from ``_MODEL_DESCRIPTORS`` must still render (name-only),
    never crash -- the documented graceful-degradation fallback."""
    monkeypatch.setattr(workspace_panel_module, "SUPPORTED_MODELS", ("Mystery",))

    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    button = panel.findChild(QPushButton, "NewButton_Mystery")
    assert button is not None
    assert button.text() == "Mystery"

    descriptor = button.parentWidget().findChild(QLabel, "NewChooserDescriptor")
    assert descriptor is not None
    assert descriptor.text() == "Mystery"


@pytest.mark.parametrize("model", SUPPORTED_MODELS)
def test_choosing_new_model_creates_document_and_switches_to_editor(app_driver, model):
    d = app_driver
    assert d.current_view_index() == 2

    d.click_workspace_new(model)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert f"· {model} ·" in d.identity_text()
    assert "State: Modified" in d.workspace_info_text()
    assert "File: untitled.json" in d.workspace_info_text()


def test_new_from_workspace_page_goes_through_discard_guard_and_cancel_aborts(
    app_driver, spm_workfile, monkeypatch
):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    original_identity = d.identity_text()
    original_status = d.status_text()
    assert "Modified" in original_status

    d.show_view("Workspace")  # starting off the Editor page so a wrongful
    # switch-to-Editor on the abort path would actually move the index

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Cancel
    )

    d.click_workspace_new("DFN")

    assert d.current_view_index() == 2
    assert d.activity_bar_selected_label() == "Workspace"
    assert d.identity_text() == original_identity
    assert d.status_text() == original_status  # dirty state retained, nothing created


def test_new_from_workspace_page_discard_guard_proceeds_on_discard(
    app_driver, spm_workfile, monkeypatch
):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Discard
    )

    d.click_workspace_new("DFN")

    assert "· DFN ·" in d.identity_text()
    assert d.current_view_index() == 0
