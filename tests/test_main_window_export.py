"""Export must propose a copy path and never touch Save's own state.

Regression coverage for the bug where Export pre-filled its dialog with the
backing file's own path, so accepting the default silently overwrote the
file Save writes -- while leaving ``dirty``/``backing_file`` referring to
that same, now export-overwritten, file.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QApplication

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _capture_and_close_open_popup(captured: dict) -> None:
    """Grab the Export button's open menu actions, then close it -- the same
    zero-delay-timer idiom used for the row context menu in
    test_remove_parameter.py, needed because ``QMenu.exec()`` (which
    ``QToolButton.InstantPopup`` runs internally) blocks in a real native
    event loop that a Python monkeypatch cannot intercept.
    """
    popup = QApplication.instance().activePopupWidget()
    if popup is not None:
        captured["actions"] = popup.actions()
        popup.close()


def _make_dirty(app_driver, spm_workfile) -> None:
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()


def test_export_default_proposes_copy_name_not_backing_file(
    app_driver, spm_workfile, monkeypatch
):
    app_driver.open(spm_workfile)
    captured = {}

    def fake_get_save_file_name(parent, title, default, filter):
        captured["default"] = default
        return ("", "")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", fake_get_save_file_name
    )

    app_driver._w._export_as("json")

    expected = spm_workfile.with_name(f"{spm_workfile.stem} (copy){spm_workfile.suffix}")
    assert captured["default"] == str(expected)
    assert captured["default"] != str(spm_workfile)


def test_export_as_yaml_proposes_yaml_extension_even_for_a_json_backing_file(
    app_driver, spm_workfile, monkeypatch
):
    app_driver.open(spm_workfile)
    captured = {}

    def fake_get_save_file_name(parent, title, default, filter):
        captured["default"] = default
        captured["filter"] = filter
        return ("", "")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", fake_get_save_file_name
    )

    app_driver._w._export_as("yaml")

    expected = spm_workfile.with_name(f"{spm_workfile.stem} (copy).yaml")
    assert captured["default"] == str(expected)
    assert "yaml" in captured["filter"].lower()


def test_export_leaves_dirty_and_backing_file_unchanged(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
    _make_dirty(app_driver, spm_workfile)
    session = app_driver._w._state.active
    assert session.dirty is True

    export_path = tmp_path / "exported.json"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(export_path), ""),
    )

    app_driver._w._export_as("json")

    assert session.dirty is True
    assert session.backing_file == spm_workfile
    assert export_path.exists()


def test_export_writes_same_bytes_save_would_write(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
    _make_dirty(app_driver, spm_workfile)
    export_path = tmp_path / "exported.json"

    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(export_path), ""),
    )
    app_driver._w._export_as("json")
    app_driver._w._save()

    assert export_path.read_bytes() == spm_workfile.read_bytes()


def test_export_never_saved_document_falls_back_to_document_filename(
    app_driver, monkeypatch
):
    app_driver._w._new("SPM")
    session = app_driver._w._state.active
    assert session.backing_file is None
    captured = {}

    def fake_get_save_file_name(parent, title, default, filter):
        captured["default"] = default
        return ("", "")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", fake_get_save_file_name
    )

    app_driver._w._export_as("json")

    assert captured["default"] == session.document.filename


def test_export_button_offers_json_and_yaml_format_choices(app_driver, spm_workfile):
    app_driver.open(spm_workfile)
    captured: dict = {}
    QTimer.singleShot(0, lambda: _capture_and_close_open_popup(captured))

    app_driver._qtbot.mouseClick(app_driver._w._export_action, Qt.LeftButton)

    actions = captured.get("actions")
    assert actions is not None, "Export button opened no menu"
    assert [a.text() for a in actions] == ["Export as JSON…", "Export as YAML…"]
