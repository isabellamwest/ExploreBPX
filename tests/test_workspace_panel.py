"""Workspace page: activity-bar entry, default landing, info panel, New chooser
and drag-and-drop file opening.

Covers Step 7 (the Workspace page shell), Step 8 (the inline New
model-chooser) and Step 9 (drag-and-drop) of the top-bar/workspace redesign.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import QMimeData, QPointF, QUrl, Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QLabel, QPushButton

import ui_qt.main_window as main_window_module
import ui_qt.workspace_panel as workspace_panel_module
from core.document_factory import SUPPORTED_MODELS

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _mime_data_for(*paths) -> QMimeData:
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(p)) for p in paths])
    return mime


def _drag_enter_event(*paths) -> QDragEnterEvent:
    mime = _mime_data_for(*paths)
    event = QDragEnterEvent(QPointF(0, 0).toPoint(), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    event._mime_keepalive = mime  # PySide6 does not keep the QMimeData arg alive on its own
    return event


def _drop_event(*paths) -> QDropEvent:
    mime = _mime_data_for(*paths)
    event = QDropEvent(QPointF(0, 0), Qt.CopyAction, mime, Qt.LeftButton, Qt.NoModifier)
    event._mime_keepalive = mime  # PySide6 does not keep the QMimeData arg alive on its own
    return event


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
    assert d.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert d._w._state.active.document.identity.model == "SPM"


def test_opening_from_workspace_page_goes_through_discard_guard(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    """Open from the Workspace page reuses ``_confirm_discard_if_dirty``,
    the same guard exercised by the toolbar Open in the discard-guard tests.

    A document is already open, so ``_open()`` now shows the open-intent
    choice dialog first (M1) -- stubbed here to "Replace main" so the
    discard guard is exercised in isolation, same as before.
    """
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    assert d.status_text() == f"{spm_workfile.name}  |  Modified"
    original_status = d.status_text()

    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Cancel
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    d.click_workspace_open()

    assert d.status_text() == original_status


def test_document_card_shows_validity_and_contents(app_driver, valid_spm_path):
    app_driver.open(valid_spm_path)
    ws = app_driver._w._workspace
    assert ws._info_badge.text() == "Valid"
    assert not ws._info_badge.isHidden()
    # section/parameter counts come straight from the document, not invented.
    doc = app_driver._w._state.active.document
    assert ws._info_fields["Contents"].text() == (
        f"{doc.section_count} sections · {doc.parameter_count} parameters"
    )


def test_document_card_badge_reports_errors(app_driver, invalid_bpx_path):
    app_driver.open(invalid_bpx_path)
    ws = app_driver._w._workspace
    doc = app_driver._w._state.active.document
    assert not doc.is_valid
    assert ws._info_badge.text() == "1 error"


def test_document_card_badge_matches_partitioned_count_not_raw_diagnostics(
    warning_only_bpx_path, tmp_path, app_driver
):
    """The pill must report the same counts as the Diagnostics rail badge.

    ``warning_legacy_bpx_float.json`` with its Electrolyte conductivity
    corrupted to a string carries 4 raw diagnostics on that one field (one
    per failed union branch: float, int, function-expression, table) plus
    the fixture's pre-existing Header warning, but ``partition_issues``
    merges the field's float/int union pair into a single displayed error
    (decision Q), so the rest of the app shows 3 errors, 1 warning. The pill
    must match, not the raw ``document.error_count``/``warning_count`` (4/1).
    """
    import json

    raw = json.loads(warning_only_bpx_path.read_text("utf-8"))
    raw["Parameterisation"]["Electrolyte"]["Conductivity [S.m-1]"] = "not-a-number"
    workfile = tmp_path / "union_pair.json"
    workfile.write_text(json.dumps(raw), encoding="utf-8")

    app_driver.open(workfile)
    ws = app_driver._w._workspace
    doc = app_driver._w._state.active.document
    assert (doc.error_count, doc.warning_count) == (4, 1), "premise: raw counts are 4/1"
    assert ws._info_badge.text() == "3 errors, 1 warning"


def test_document_card_is_blank_with_no_document(app_driver):
    ws = app_driver._w._workspace
    assert ws._info_title.text() == "No document open"
    assert ws._info_badge.isHidden()


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
    assert d._w._state.active.document.identity.model == model
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

    assert d._w._state.active.document.identity.model == "DFN"
    assert d.current_view_index() == 0


# --- panel-level drag/drop filtering ------------------------------------
#
# These construct real QDragEnterEvent/QDropEvent instances and dispatch
# them straight to a bare WorkspacePanel, exercising the extension filter
# and single-file behaviour independent of MainWindow.


def test_drag_enter_accepts_a_supported_extension(qtbot, valid_spm_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    event = _drag_enter_event(valid_spm_path)
    panel.dragEnterEvent(event)

    assert event.isAccepted()


def test_drag_enter_ignores_an_unsupported_extension(qtbot, tmp_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    unsupported = tmp_path / "notes.txt"

    event = _drag_enter_event(unsupported)
    panel.dragEnterEvent(event)

    assert not event.isAccepted()


def test_drop_emits_file_dropped_for_the_first_supported_file_only(
    qtbot, valid_spm_path, tmp_path
):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    other = tmp_path / "other.json"
    other.write_text("{}", encoding="utf-8")
    received: list[str] = []
    panel.file_dropped.connect(received.append)

    event = _drop_event(valid_spm_path, other)
    panel.dropEvent(event)

    assert received == [str(valid_spm_path)]
    assert event.isAccepted()


def test_drop_skips_a_leading_unsupported_file_to_reach_a_later_supported_one(
    qtbot, valid_spm_path, tmp_path
):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    unsupported = tmp_path / "notes.txt"
    received: list[str] = []
    panel.file_dropped.connect(received.append)

    event = _drop_event(unsupported, valid_spm_path)
    panel.dropEvent(event)

    assert received == [str(valid_spm_path)]
    assert event.isAccepted()


def test_drag_enter_accepts_an_uppercase_supported_extension(qtbot, tmp_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    uppercase = tmp_path / "SOMETHING.JSON"
    uppercase.write_text("{}", encoding="utf-8")

    event = _drag_enter_event(uppercase)
    panel.dragEnterEvent(event)

    assert event.isAccepted()


def test_drop_ignores_an_unsupported_extension_without_emitting(qtbot, tmp_path):
    panel = workspace_panel_module.WorkspacePanel()
    qtbot.addWidget(panel)

    unsupported = tmp_path / "notes.txt"
    received: list[str] = []
    panel.file_dropped.connect(received.append)

    event = _drop_event(unsupported)
    panel.dropEvent(event)

    assert received == []
    assert not event.isAccepted()


# --- MainWindow wiring: drop goes through the same guard/open/error path
# as the toolbar/Workspace Open button ------------------------------------


def test_dropping_a_valid_file_opens_it_and_switches_to_editor(app_driver, valid_spm_path):
    d = app_driver
    assert d.current_view_index() == 2

    d.drop_file_on_workspace(valid_spm_path)

    assert d.current_view_index() == 0
    assert d.activity_bar_selected_label() == "Editor"
    assert d.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert d._w._state.active.document.identity.model == "SPM"


def test_dropping_a_file_goes_through_discard_guard_and_cancel_aborts(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    """A document is already open, so the drop now shows the open-intent
    choice dialog first (M1) -- stubbed here to "Replace main" so the
    discard guard is exercised in isolation, same as before."""
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    original_identity = d.identity_text()
    original_status = d.status_text()
    assert "Modified" in original_status

    d.show_view("Workspace")  # starting off the Editor page so a wrongful
    # switch-to-Editor on the abort path would actually move the index

    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Cancel
    )

    d.drop_file_on_workspace(valid_spm_path)

    assert d.current_view_index() == 2
    assert d.activity_bar_selected_label() == "Workspace"
    assert d.identity_text() == original_identity
    assert d.status_text() == original_status  # dirty state retained, nothing opened


def test_dropping_a_file_discard_guard_proceeds_on_discard(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    d = app_driver
    d.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()

    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: main_window_module.QMessageBox.Discard
    )

    d.drop_file_on_workspace(valid_spm_path)

    assert d.identity_text() == "Minimal valid SPM example · BPX v1.0.0"
    assert d._w._state.active.document.identity.model == "SPM"
    assert d.current_view_index() == 0


def test_dropping_an_unsupported_extension_is_a_no_op(app_driver, tmp_path):
    d = app_driver
    unsupported = tmp_path / "notes.txt"
    unsupported.write_text("hello", encoding="utf-8")

    d.drop_file_on_workspace(unsupported)

    assert d.current_view_index() == 2
    assert d.workspace_info_text() == "No document open"


def test_dropping_an_unparseable_file_shows_the_load_error_dialog(
    app_driver, tmp_path, monkeypatch
):
    d = app_driver
    broken = tmp_path / "broken.json"
    broken.write_text("{not valid json", encoding="utf-8")

    calls = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", lambda *a, **k: calls.append(a)
    )

    d.drop_file_on_workspace(broken)

    assert len(calls) == 1
    assert d.current_view_index() == 2  # stayed on Workspace, nothing opened
    assert d.workspace_info_text() == "No document open"
