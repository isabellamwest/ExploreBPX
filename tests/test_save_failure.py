"""A failed Save As must not poison the session's backing file.

MainWindow._save adopts the chosen path before writing. If the write then
fails (disk full, permissions, vanished drive), the adopted path must be
rolled back: keeping it would make every later Save retry the same broken
path without ever re-opening the file dialog -- there is no separate
Save As action, so the document would become un-savable through the UI.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def test_failed_save_as_rolls_back_backing_file_and_reprompts(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    session = window._state.active
    session.backing_file = None  # a never-saved document: Save runs Save As

    dialog_calls = []

    def fake_get_save_file_name(*args, **kwargs):
        dialog_calls.append(1)
        return (str(tmp_path / "target.json"), "")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", fake_get_save_file_name
    )
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", lambda *a, **k: None
    )

    def failing_save():
        raise OSError("disk full")

    monkeypatch.setattr(session, "save", failing_save)

    assert window._save() is False
    assert session.backing_file is None
    assert session.dirty is True

    # The next Save must re-open the dialog, not silently retry a dead path.
    assert window._save() is False
    assert len(dialog_calls) == 2


def test_failed_save_to_existing_backing_file_keeps_it(
    app_driver, spm_workfile, monkeypatch
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    session = window._state.active
    assert session.backing_file is not None

    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", lambda *a, **k: None
    )

    def failing_save():
        raise OSError("permission denied")

    monkeypatch.setattr(session, "save", failing_save)

    assert window._save() is False
    # The path was valid before this attempt; a transient failure must not
    # detach the document from its own file.
    assert session.backing_file == spm_workfile
