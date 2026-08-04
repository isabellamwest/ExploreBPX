"""Discard-guard: prompts before replacing a dirty document.

Covers Step 5 of the top-bar/workspace redesign: MainWindow._open must not
silently discard unsaved changes. This exercises the reusable guard,
_confirm_discard_if_dirty, through _open -- Steps 8 (New) and 9 (drag-and-
drop) will reuse the same guard method.

M1 (multi-file track) changed _open's ordering: with a document already
active (dirty or not), Open now shows the open-intent choice dialog
(_ask_open_intent) BEFORE the discard guard -- "Replace main" falls through
into this same discard-guarded path, but "Add as reference"/"Cancel" never
reach it at all. Every test below that has a document already active
therefore stubs ``_ask_open_intent`` to return ``REPLACE_MAIN``, simulating
that choice, so the guard itself is exercised in isolation exactly as
before. See tests/test_reference_open_flow.py for the choice dialog itself.
"""

from __future__ import annotations

import json

import pytest
from PySide6.QtWidgets import QMessageBox

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _make_dirty(app_driver, spm_workfile) -> None:
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    assert app_driver.status_text() == f"{spm_workfile.name}  |  Modified"


def _fail_if_called(*args, **kwargs):
    raise AssertionError("This dialog should not have been shown")


def _stub_replace_main(app_driver, monkeypatch) -> None:
    """Simulate the open-intent choice dialog always answering "Replace
    main" -- a document is already active in every test below, so real
    ``_open()``/drop now shows that dialog before the discard guard."""
    monkeypatch.setattr(
        app_driver._w,
        "_ask_open_intent",
        lambda filename: main_window_module.OpenIntent.REPLACE_MAIN,
    )


def test_open_with_clean_document_does_not_prompt(
    app_driver, valid_spm_path, spm_workfile, monkeypatch
):
    app_driver.open(valid_spm_path)
    _stub_replace_main(app_driver, monkeypatch)

    monkeypatch.setattr(main_window_module.QMessageBox, "question", _fail_if_called)
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(spm_workfile), ""),
    )

    app_driver._w._open()

    assert app_driver.status_text() == f"{spm_workfile.name}  |  Saved"


def test_open_dirty_cancel_aborts(app_driver, spm_workfile, valid_spm_path, monkeypatch):
    _make_dirty(app_driver, spm_workfile)
    _stub_replace_main(app_driver, monkeypatch)
    original_status = app_driver.status_text()

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver._w._open()

    assert app_driver.status_text() == original_status
    assert app_driver._w._state.active.dirty is True


def test_open_dirty_dont_save_proceeds(app_driver, spm_workfile, valid_spm_path, monkeypatch):
    _make_dirty(app_driver, spm_workfile)
    _stub_replace_main(app_driver, monkeypatch)

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Discard
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver._w._open()

    assert app_driver.status_text() == f"{valid_spm_path.name}  |  Saved"


def test_open_dirty_save_succeeds_then_proceeds(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    _make_dirty(app_driver, spm_workfile)
    _stub_replace_main(app_driver, monkeypatch)

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Save
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver._w._open()

    assert app_driver.status_text() == f"{valid_spm_path.name}  |  Saved"
    saved = json.loads(spm_workfile.read_text("utf-8"))
    assert saved["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 6.0


def test_close_clean_window_does_not_prompt(app_driver, valid_spm_path, monkeypatch):
    app_driver.open(valid_spm_path)
    monkeypatch.setattr(main_window_module.QMessageBox, "question", _fail_if_called)

    assert app_driver._w.close() is True


def test_close_dirty_cancel_keeps_window_open(app_driver, spm_workfile, monkeypatch):
    _make_dirty(app_driver, spm_workfile)
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Cancel
    )

    assert app_driver._w.close() is False
    assert app_driver._w._state.active.dirty is True


def test_close_dirty_discard_closes(app_driver, spm_workfile, monkeypatch):
    _make_dirty(app_driver, spm_workfile)
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Discard
    )

    assert app_driver._w.close() is True


def test_close_dirty_save_writes_then_closes(app_driver, spm_workfile, monkeypatch):
    _make_dirty(app_driver, spm_workfile)
    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Save
    )

    assert app_driver._w.close() is True
    saved = json.loads(spm_workfile.read_text("utf-8"))
    assert saved["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 6.0


def test_open_dirty_save_cancelled_save_as_aborts(
    app_driver, spm_workfile, valid_spm_path, monkeypatch
):
    _make_dirty(app_driver, spm_workfile)
    _stub_replace_main(app_driver, monkeypatch)
    app_driver._w._state.active.backing_file = None  # force the Save As path
    original_status = app_driver.status_text()

    monkeypatch.setattr(
        main_window_module.QMessageBox, "question", lambda *a, **k: QMessageBox.Save
    )
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", "")
    )
    # The file picker now always runs before the discard guard (it must know
    # the target filename to show the open-intent choice dialog), so this can
    # no longer stub _fail_if_called the way it did pre-M1.
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getOpenFileName",
        lambda *a, **k: (str(valid_spm_path), ""),
    )

    app_driver._w._open()

    assert app_driver.status_text() == original_status
    assert app_driver._w._state.active.dirty is True
