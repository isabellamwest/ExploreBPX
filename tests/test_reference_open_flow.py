"""Reference pin lifecycle, toast feedback, and the Open-dialog choice flow.

Before extending this file: the choice dialog only ever appears while a main
document is already open (main or reference, dirty or not) -- with no document
open, Open/drop behave exactly as before. Pinning appends (multi-reference
Phase 1): a second pin never replaces the first, and the fifth is rejected
with the cap toast.
"""

from __future__ import annotations

import json
import shutil

import pytest
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module
from state.app_state import REFERENCE_PIN_CAP

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _fail_if_called(*args, **kwargs):
    raise AssertionError("This dialog should not have been shown")


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def _pin_copies(app_driver, source, tmp_path, count, monkeypatch) -> list:
    """Pin *count* distinct on-disk copies of *source* via the real open
    flow, returning their paths."""
    paths = []
    for index in range(count):
        target = tmp_path / f"pin_{index}.json"
        shutil.copy(source, target)
        _stub_open_dialog(monkeypatch, target)
        app_driver.click_workspace_open_reference()
        paths.append(target)
    return paths


def test_references_section_shows_the_empty_state_with_nothing_pinned(app_driver):
    """With nothing pinned the section stays on screen as the reference
    library's front door, not a row list."""
    assert app_driver.reference_pin_count() == 0
    assert app_driver.reference_empty_state_visible()
    assert app_driver.reference_pin_cap_note() is None


def test_clicking_open_as_reference_pins_and_shows_a_row(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.reference_pin_count() == 1
    assert not d.reference_empty_state_visible()
    header = d.reference_pin_header_texts()[0]
    # Badge letters from the display name ("valid_spm_example" -> "Va"),
    # then the name (extension dropped) and the model -- no validity dot in
    # the collapsed row (design rule 1).
    assert valid_spm_path.stem in header
    assert header.endswith("SPM")
    assert d.reference_pin_cap_note() == "1 of 4 pinned"


def test_expanding_a_pin_row_shows_the_full_record(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()
    assert not d.reference_pin_expanded(0)

    d.toggle_reference_pin(0)

    assert d.reference_pin_expanded(0)
    detail = d.reference_pin_detail_text(0)
    assert "Origin: File on disk" in detail
    assert "Validity: Valid" in detail
    assert "Model: SPM" in detail
    assert "Contents: 11 sections · 44 parameters" in detail
    # A long path is middle-shortened in the row (full path in the tooltip),
    # so pin the row's presence and its tail, not the full string.
    assert "File path:" in detail
    assert detail.strip().endswith(valid_spm_path.name)

    d.toggle_reference_pin(0)
    assert not d.reference_pin_expanded(0)


def test_pin_detail_validity_line_for_an_invalid_reference(
    app_driver, valid_spm_path, tmp_path, monkeypatch
):
    """Breaking a copy of a real fixture surfaces the validator's own error
    count in the expanded detail -- never an invented one."""
    raw = json.loads(valid_spm_path.read_text("utf-8"))
    del raw["Header"]["Model"]
    broken = tmp_path / "broken_reference.json"
    broken.write_text(json.dumps(raw), encoding="utf-8")

    d = app_driver
    _stub_open_dialog(monkeypatch, broken)
    d.click_workspace_open_reference()

    d.toggle_reference_pin(0)
    detail = d.reference_pin_detail_text(0)
    assert "1 error" in detail
    # Zero counts are dropped, matching the document badge convention.
    assert "0 warnings" not in detail


def test_a_second_pin_appends_instead_of_replacing(
    app_driver, valid_spm_path, nmc_pouch_cell_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()
    _stub_open_dialog(monkeypatch, nmc_pouch_cell_path)

    d.click_workspace_open_reference()

    assert d.reference_pin_count() == 2
    assert [r.filename for r in d._w._state.references] == [
        valid_spm_path.name,
        nmc_pouch_cell_path.name,
    ]
    assert d.reference_pin_cap_note() == "2 of 4 pinned"


def test_removing_a_pin_removes_exactly_that_row(
    app_driver, valid_spm_path, nmc_pouch_cell_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()
    _stub_open_dialog(monkeypatch, nmc_pouch_cell_path)
    d.click_workspace_open_reference()

    d.click_reference_remove(0)

    assert d.reference_pin_count() == 1
    assert d._w._state.references[0].filename == nmc_pouch_cell_path.name


def test_removing_the_last_pin_returns_the_section_to_its_empty_state(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()
    assert d.reference_pin_count() == 1

    d.click_reference_remove(0)

    assert d.reference_pin_count() == 0
    assert d.reference_empty_state_visible()
    assert d._w._state.references == []
    assert d.reference_pin_cap_note() is None


def test_pin_buttons_disable_at_the_cap_and_reenable_after_a_remove(
    app_driver, valid_spm_path, tmp_path, monkeypatch
):
    d = app_driver
    _pin_copies(d, valid_spm_path, tmp_path, REFERENCE_PIN_CAP, monkeypatch)

    assert d.reference_pin_count() == REFERENCE_PIN_CAP
    assert d.reference_pin_cap_note() == "4 of 4 pinned"
    assert not d.reference_pin_buttons_enabled()

    d.click_reference_remove(0)

    assert d.reference_pin_buttons_enabled()
    assert d.reference_pin_cap_note() == "3 of 4 pinned"


def test_a_fifth_pin_is_rejected_with_the_cap_toast(
    app_driver, valid_spm_path, tmp_path, monkeypatch
):
    d = app_driver
    _pin_copies(d, valid_spm_path, tmp_path, REFERENCE_PIN_CAP, monkeypatch)
    fifth = tmp_path / "fifth.json"
    shutil.copy(valid_spm_path, fifth)

    # The workspace button is disabled at the cap, so drive the underlying
    # flow directly (the same path a drop/open-intent choice reaches).
    d._w._open_reference_path(fifth)

    assert d.reference_pin_count() == REFERENCE_PIN_CAP
    assert d.toast_text() == (
        "4 references already pinned · remove one to pin another"
    )


def test_references_can_be_pinned_with_no_main_document_open(
    app_driver, valid_spm_path, monkeypatch
):
    """A reference-only workspace is a legal state."""
    d = app_driver
    assert d._w._state.active is None
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.reference_pin_count() == 1
    assert d._w._state.active is None


def test_toast_shows_pinned_message_after_pinning(app_driver, valid_spm_path, monkeypatch):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.toast_text() == f"Pinned {valid_spm_path.name} as reference"


def test_toast_shows_already_pinned_on_the_same_path_again(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()

    d.click_workspace_open_reference()

    assert d.toast_text() == "Already pinned as reference"
    assert d.reference_pin_count() == 1


def test_toast_shows_is_main_when_pinning_the_open_main_file(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    d.open(valid_spm_path)
    _stub_open_dialog(monkeypatch, valid_spm_path)

    d.click_workspace_open_reference()

    assert d.toast_text() == "Already open as the main file"
    assert d._w._state.references == []


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
    assert d._w._state.references == []  # untouched


def test_choice_pin_as_reference_pins_without_touching_the_session(
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
    assert len(d._w._state.references) == 1
    assert d._w._state.references[0].filename == nmc_pouch_cell_path.name
    assert d.toast_text() == f"Pinned {nmc_pouch_cell_path.name} as reference"


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
    assert d._w._state.references == []


def test_ask_open_intent_real_dialog_pin_as_reference(
    app_driver, valid_spm_path, nmc_pouch_cell_path
):
    """The real dialog's second button reads "Pin as reference" in every
    state -- pinning appends, so the old "Replace reference" wording is
    gone even with a reference already pinned."""
    d = app_driver
    d.open(valid_spm_path)
    d._w._state.pin_reference(nmc_pouch_cell_path)

    captured: dict = {}

    def _click_pin_button():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["labels"] = [b.text() for b in box.buttons()]
            for button in box.buttons():
                if button.text() == "Pin as reference":
                    button.click()
                    return

    QTimer.singleShot(0, _click_pin_button)
    intent = d._w._ask_open_intent("other.json")

    # Qt's own QDialogButtonBox role layout decides on-screen order (platform
    # convention), so this checks membership, not position.
    assert set(captured["labels"]) == {"Replace main", "Pin as reference", "Cancel"}
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
