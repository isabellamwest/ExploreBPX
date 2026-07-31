"""Reference tile lifecycle, toast feedback, and the Open-dialog choice flow
(M1: reference in state + Workspace).

Study ``PLAN-multi-file.md`` decision 8 before extending this file: the
choice dialog only ever appears while a main document is already open (main
or reference, dirty or not) -- with no document open, Open/drop behave
exactly as before.
"""

from __future__ import annotations

import json
import shutil

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QMessageBox

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _fail_if_called(*args, **kwargs):
    raise AssertionError("This dialog should not have been shown")


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def test_reference_card_shows_the_empty_state_with_nothing_docked(app_driver):
    """Concept A (signed 2026-07-31): with nothing docked the card stays on
    screen as the reference library's front door, not a docked tile."""
    assert not app_driver.reference_tile_visible()
    assert app_driver.reference_empty_state_visible()


def test_clicking_open_as_reference_docks_and_shows_the_tile(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.reference_tile_visible()
    assert not d.reference_empty_state_visible()
    text = d.reference_tile_text()
    assert "Read-only" in text
    assert valid_spm_path.name in text
    assert "Model: SPM" in text
    assert "Contents: 11 sections · 44 parameters" in text
    assert "Validity: Valid" in text


def test_removing_the_reference_returns_the_card_to_its_empty_state(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()
    assert d.reference_tile_visible()

    d.click_reference_remove()

    assert not d.reference_tile_visible()
    assert d.reference_empty_state_visible()
    assert d._w._state.reference is None


def test_reference_tile_validity_line_for_an_invalid_reference(
    app_driver, valid_spm_path, tmp_path, monkeypatch
):
    """Breaking a copy of a real fixture surfaces the validator's own error
    count on the tile -- never an invented one."""
    raw = json.loads(valid_spm_path.read_text("utf-8"))
    del raw["Header"]["Model"]
    broken = tmp_path / "broken_reference.json"
    broken.write_text(json.dumps(raw), encoding="utf-8")

    d = app_driver
    _stub_open_dialog(monkeypatch, broken)

    d.click_workspace_open_reference()

    tile_text = d.reference_tile_text()
    assert "1 error" in tile_text
    # Zero counts are dropped, matching the document card's badge convention.
    assert "0 warnings" not in tile_text


def test_reference_tile_can_be_docked_with_no_main_document_open(
    app_driver, valid_spm_path, monkeypatch
):
    """A reference-only workspace is a legal state."""
    d = app_driver
    assert d._w._state.active is None
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.reference_tile_visible()
    assert d._w._state.active is None


def test_toast_shows_added_message_after_docking(app_driver, valid_spm_path, monkeypatch):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.toast_text() == f"Added {valid_spm_path.name} as reference"


def test_toast_shows_already_reference_on_the_same_path_again(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()

    d.click_workspace_open_reference()

    assert d.toast_text() == "Already open as reference"


def test_toast_shows_is_main_when_referencing_the_open_main_file(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    d.open(valid_spm_path)
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.toast_text() == "Already open as the main file"
    assert d._w._state.reference is None


def test_choice_replace_main_reaches_the_normal_open(
    app_driver, valid_spm_path, tmp_path, monkeypatch
):
    d = app_driver
    d.open(valid_spm_path)  # a document is already open (clean)

    other = tmp_path / "other.json"
    shutil.copy(valid_spm_path, other)
    _stub_open_dialog(monkeypatch, other)
    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )

    d.click_workspace_open()

    assert d._w._state.active.backing_file == other
    assert d._w._state.reference is None  # untouched


def test_choice_add_as_reference_docks_without_touching_the_session(
    app_driver, valid_spm_path, nmc_pouch_cell_path, monkeypatch
):
    d = app_driver
    d.open(valid_spm_path)
    original_session = d._w._state.active

    _stub_open_dialog(monkeypatch, nmc_pouch_cell_path)
    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.ADD_REFERENCE
    )

    d.click_workspace_open()

    assert d._w._state.active is original_session  # untouched
    assert d._w._state.reference is not None
    assert d._w._state.reference.filename == nmc_pouch_cell_path.name
    assert d.toast_text() == f"Added {nmc_pouch_cell_path.name} as reference"


def test_choice_cancel_does_nothing(app_driver, valid_spm_path, nmc_pouch_cell_path, monkeypatch):
    d = app_driver
    d.open(valid_spm_path)
    original_session = d._w._state.active

    _stub_open_dialog(monkeypatch, nmc_pouch_cell_path)
    monkeypatch.setattr(
        d._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.CANCEL
    )
    monkeypatch.setattr(main_window_module.QMessageBox, "question", _fail_if_called)

    d.click_workspace_open()

    assert d._w._state.active is original_session
    assert d._w._state.reference is None


def test_choice_dialog_offers_replace_reference_label_when_one_is_already_docked(
    app_driver, valid_spm_path, nmc_pouch_cell_path, monkeypatch
):
    """Second-button label switches from "Add as reference" to "Replace
    reference" once a reference is already docked -- exercised directly
    against the real (overridden-nowhere) ``_ask_open_intent``."""
    d = app_driver
    d.open(valid_spm_path)
    d._w._state.open_reference(nmc_pouch_cell_path)

    captured: dict = {}

    def _click_second_button():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["labels"] = [b.text() for b in box.buttons()]
            for button in box.buttons():
                if button.text() == "Replace reference":
                    button.click()
                    return

    QTimer.singleShot(0, _click_second_button)
    intent = d._w._ask_open_intent("other.json")

    # Qt's own QDialogButtonBox role layout decides on-screen order (platform
    # convention), so this checks membership, not position.
    assert set(captured["labels"]) == {"Replace main", "Replace reference", "Cancel"}
    assert intent is main_window_module.OpenIntent.ADD_REFERENCE


def test_ask_open_intent_real_dialog_replace_main(app_driver, valid_spm_path):
    """One real-dialog test (project convention): the actual QMessageBox, driven
    via the zero-delay ``QTimer.singleShot`` + ``activeModalWidget()`` idiom
    (``QMessageBox.exec()`` truly blocks; a Python monkeypatch of ``.exec()``
    does not intercept it)."""
    d = app_driver
    d.open(valid_spm_path)

    captured: dict = {}

    def _click_replace_main():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["title"] = box.windowTitle()
            captured["text"] = box.text()
            for button in box.buttons():
                if button.text() == "Replace main":
                    button.click()
                    return

    QTimer.singleShot(0, _click_replace_main)
    intent = d._w._ask_open_intent("incoming.json")

    assert captured["title"] == "Open incoming.json"
    assert captured["text"] == "A document is already open. Open this file as:"
    assert intent is main_window_module.OpenIntent.REPLACE_MAIN
