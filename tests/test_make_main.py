"""Make main: role-swap between the docked reference and the active main
(multi-file track M4). See PLAN-multi-file.md section "M4 -- Make main" for
the full spec (entry point, dialog copy, toast copy, post-swap contract)
this file pins.
"""

from __future__ import annotations

import json
import shutil

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _fail_if_called(*args, **kwargs):
    raise AssertionError("This dialog should not have been shown")


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def _dock_reference(app_driver, ref_path, monkeypatch) -> None:
    _stub_open_dialog(monkeypatch, ref_path)
    app_driver.click_workspace_open_reference()


def _stub_switch_intent(monkeypatch, driver, intent) -> None:
    monkeypatch.setattr(driver._w, "_ask_switch_intent", lambda main_name, ref_name: intent)


@pytest.fixture
def main_and_ref(valid_spm_path, tmp_path) -> tuple:
    """Two valid SPM files differing only in Nominal cell capacity, so a
    swap's pull-direction reversal and value round-trip are both
    observable."""
    main_path = tmp_path / "main.json"
    shutil.copy(valid_spm_path, main_path)
    ref_raw = json.loads(valid_spm_path.read_text("utf-8"))
    ref_raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = 6.0
    ref_path = tmp_path / "reference.json"
    ref_path.write_text(json.dumps(ref_raw), encoding="utf-8")
    return main_path, ref_path


@pytest.fixture
def invalid_main_and_valid_ref(valid_spm_path, tmp_path) -> tuple:
    """A main missing Header.Model (1 validator error, pinned by
    test_reference_open_flow.py's own broken-reference fixture) paired with
    a fully valid reference -- proves Diagnostics follows the *role*, not
    the file, across a swap."""
    broken = json.loads(valid_spm_path.read_text("utf-8"))
    del broken["Header"]["Model"]
    main_path = tmp_path / "broken_main.json"
    main_path.write_text(json.dumps(broken), encoding="utf-8")
    ref_path = tmp_path / "valid_reference.json"
    ref_path.write_text(valid_spm_path.read_text("utf-8"), encoding="utf-8")
    return main_path, ref_path


# ---------------------------------------------------------------------------
# Entry point: the card button itself
# ---------------------------------------------------------------------------


def test_make_main_button_present_and_hidden_with_the_card(app_driver, main_and_ref, monkeypatch):
    d = app_driver
    main_path, ref_path = main_and_ref
    assert not d.reference_make_main_button_visible()  # no reference docked yet

    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    assert d.reference_make_main_button_visible()
    assert d._w._workspace._reference_make_main_button.text() == "Make main"

    d.click_reference_remove()
    assert not d.reference_make_main_button_visible()


# ---------------------------------------------------------------------------
# Clean swap
# ---------------------------------------------------------------------------


def test_clean_swap_round_trip(app_driver, main_and_ref, monkeypatch):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    assert d._w._state.active.dirty is False

    d.click_reference_make_main()

    assert d._w._state.active.backing_file == ref_path
    assert d._w._state.reference.path == main_path
    assert d.toast_text() == f"{ref_path.name} is now the main file"


def test_clean_swap_undo_stack_empty_and_swap_itself_is_not_undoable(
    app_driver, main_and_ref, monkeypatch
):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)

    d.click_reference_make_main()

    assert d._w._state.active.can_undo is False
    assert d.undo_enabled() is False
    promoted_capacity = d._w._state.active.document.raw["Parameterisation"]["Cell"][
        "Nominal cell capacity [A.h]"
    ]
    d.press_undo_shortcut()  # Ctrl+Z: a no-op, the swap is not a command
    assert (
        d._w._state.active.document.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
        == promoted_capacity
    )


# ---------------------------------------------------------------------------
# Dirty branches
# ---------------------------------------------------------------------------


def test_save_and_switch_saves_the_old_main_then_swaps(app_driver, main_and_ref, monkeypatch):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    d.go_to(_CAPACITY).edit_field(7.0).commit()
    assert d._w._state.active.dirty is True
    _stub_switch_intent(monkeypatch, d, main_window_module.SwitchIntent.SAVE_AND_SWITCH)

    d.click_reference_make_main()

    saved = json.loads(main_path.read_text("utf-8"))
    assert saved["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 7.0
    assert d._w._state.active.backing_file == ref_path
    assert d._w._state.reference.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 7.0
    assert d.toast_text() == f"{ref_path.name} is now the main file"


def test_discard_and_switch_edits_gone_and_absent_from_new_reference(
    app_driver, main_and_ref, monkeypatch
):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    d.go_to(_CAPACITY).edit_field(7.0).commit()
    assert d._w._state.active.dirty is True
    _stub_switch_intent(monkeypatch, d, main_window_module.SwitchIntent.DISCARD_AND_SWITCH)

    d.click_reference_make_main()

    # The discarded edit never reached disk, so the new reference (read
    # fresh from disk) carries the original value, not the discarded 7.0.
    assert d._w._state.reference.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 5
    on_disk = json.loads(main_path.read_text("utf-8"))
    assert on_disk["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 5
    assert d._w._state.active.backing_file == ref_path
    assert d.toast_text() == f"{ref_path.name} is now the main file"


def test_cancel_leaves_roles_and_session_unchanged(app_driver, main_and_ref, monkeypatch):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    d.go_to(_CAPACITY).edit_field(7.0).commit()
    original_session = d._w._state.active
    original_reference = d._w._state.reference
    before_toast = d.toast_text()
    _stub_switch_intent(monkeypatch, d, main_window_module.SwitchIntent.CANCEL)
    monkeypatch.setattr(main_window_module.QMessageBox, "critical", _fail_if_called)

    d.click_reference_make_main()

    assert d._w._state.active is original_session
    assert d._w._state.reference is original_reference
    assert d._w._state.active.dirty is True  # the edit is still there, untouched
    assert d.toast_text() == before_toast  # no swap toast fired


def test_dirty_dialog_shown_only_while_dirty(app_driver, main_and_ref, monkeypatch):
    """A clean main swaps straight through -- no prompt at all."""
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    monkeypatch.setattr(d._w, "_ask_switch_intent", _fail_if_called)

    d.click_reference_make_main()

    assert d._w._state.active.backing_file == ref_path


# ---------------------------------------------------------------------------
# Never-saved main
# ---------------------------------------------------------------------------


def test_never_saved_main_save_as_cancel_unwinds_the_whole_switch(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    d.click_workspace_new("SPM")
    assert d._w._state.active.backing_file is None
    assert d._w._state.active.dirty is True
    _dock_reference(d, valid_spm_path, monkeypatch)
    before_toast = d.toast_text()
    _stub_switch_intent(monkeypatch, d, main_window_module.SwitchIntent.SAVE_AND_SWITCH)
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))

    d.click_reference_make_main()

    assert d._w._state.active.backing_file is None  # still never-saved -- swap unwound
    assert d._w._state.reference is not None
    assert d._w._state.reference.filename == valid_spm_path.name  # still docked
    assert d.toast_text() == before_toast


def test_never_saved_main_successful_save_as_continues_the_swap(
    app_driver, valid_spm_path, tmp_path, monkeypatch
):
    d = app_driver
    d.click_workspace_new("SPM")
    _dock_reference(d, valid_spm_path, monkeypatch)
    save_path = tmp_path / "new_main.json"
    _stub_switch_intent(monkeypatch, d, main_window_module.SwitchIntent.SAVE_AND_SWITCH)
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", lambda *a, **k: (str(save_path), "")
    )

    d.click_reference_make_main()

    assert save_path.exists()
    assert d._w._state.active.backing_file == valid_spm_path
    assert d._w._state.reference.path == save_path
    assert d.toast_text() == f"{valid_spm_path.name} is now the main file"


# ---------------------------------------------------------------------------
# Unreadable promoted file
# ---------------------------------------------------------------------------


def test_unreadable_promoted_file_shows_error_and_leaves_roles_unchanged(
    app_driver, main_and_ref, monkeypatch
):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)
    original_session = d._w._state.active
    original_reference = d._w._state.reference
    ref_path.unlink()  # the promoted file vanishes from disk

    calls = []
    monkeypatch.setattr(
        main_window_module.QMessageBox, "critical", lambda *a, **k: calls.append(a)
    )

    d.click_reference_make_main()

    assert len(calls) == 1
    assert d._w._state.active is original_session
    assert d._w._state.reference is original_reference


# ---------------------------------------------------------------------------
# Diagnostics + pull direction follow the roles
# ---------------------------------------------------------------------------


def test_diagnostics_follow_the_new_main_after_swap(
    app_driver, invalid_main_and_valid_ref, monkeypatch
):
    d = app_driver
    main_path, ref_path = invalid_main_and_valid_ref
    d.open(main_path)
    assert d.validation_badge_count() == 1  # the broken main's own error
    _dock_reference(d, ref_path, monkeypatch)

    d.click_reference_make_main()

    assert d.validation_badge_count() == 0  # the promoted (valid) file is now main
    assert d._w._state.reference.error_count == 1  # the demoted file's issue, tile-only


def test_copy_up_pulls_from_the_old_main_after_swap(app_driver, main_and_ref, monkeypatch):
    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)

    d.click_reference_make_main()

    d.go_to(_CAPACITY)
    assert d.field_value() == 6.0  # the promoted file's own value
    assert d.copy_up_enabled()

    d.click_copy_up()

    assert d.field_value() == 5.0  # pulled from the old main, now the reference


# ---------------------------------------------------------------------------
# Real dialog (project convention: at least one test drives the actual QMessageBox)
# ---------------------------------------------------------------------------


def test_ask_switch_intent_real_dialog_save_and_switch(app_driver, main_and_ref, monkeypatch):
    """One real-dialog test: the actual ``QMessageBox``, driven via the
    zero-delay ``QTimer.singleShot`` + ``activeModalWidget()`` idiom
    (``QMessageBox.exec()`` truly blocks; a Python monkeypatch of ``.exec()``
    does not intercept it)."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    d = app_driver
    main_path, ref_path = main_and_ref
    d.open(main_path)
    _dock_reference(d, ref_path, monkeypatch)

    captured: dict = {}

    def _click_save_and_switch():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["title"] = box.windowTitle()
            captured["text"] = box.text()
            captured["informative"] = box.informativeText()
            captured["labels"] = [b.text() for b in box.buttons()]
            for button in box.buttons():
                if button.text() == "Save && switch":
                    button.click()
                    return

    QTimer.singleShot(0, _click_save_and_switch)
    intent = d._w._ask_switch_intent(main_path.name, ref_path.name)

    assert captured["title"] == "Unsaved changes"
    assert captured["text"] == f"{main_path.name} has unsaved changes. Save before switching?"
    assert captured["informative"] == (
        f"{ref_path.name} becomes the main file; {main_path.name} becomes the read-only reference."
    )
    # "&&" is Qt's escape for a literal ampersand -- on screen these read
    # "Save & switch" / "Discard & switch".
    assert set(captured["labels"]) == {"Save && switch", "Discard && switch", "Cancel"}
    assert intent is main_window_module.SwitchIntent.SAVE_AND_SWITCH


# ---------------------------------------------------------------------------
# Fallback branch: no file to demote (open + remove_reference), reachable
# with no main open at all, or a never-saved main that gets discarded.
# ---------------------------------------------------------------------------


def test_no_main_open_promotes_the_reference_and_undocks_it(app_driver, valid_spm_path, monkeypatch):
    d = app_driver
    assert d._w._state.active is None
    _dock_reference(d, valid_spm_path, monkeypatch)

    d.click_reference_make_main()

    assert d._w._state.active is not None
    assert d._w._state.active.backing_file == valid_spm_path
    assert d._w._state.reference is None
    assert not d.reference_tile_visible()
    assert d.toast_text() == f"{valid_spm_path.name} is now the main file"


def test_never_saved_main_discard_and_switch_promotes_and_undocks(
    app_driver, valid_spm_path, monkeypatch
):
    d = app_driver
    d.click_workspace_new("SPM")
    assert d._w._state.active.backing_file is None
    assert d._w._state.active.dirty is True
    _dock_reference(d, valid_spm_path, monkeypatch)
    _stub_switch_intent(monkeypatch, d, main_window_module.SwitchIntent.DISCARD_AND_SWITCH)

    d.click_reference_make_main()

    assert d._w._state.active.backing_file == valid_spm_path
    assert d._w._state.reference is None
    assert not d.reference_tile_visible()
    assert d.toast_text() == f"{valid_spm_path.name} is now the main file"
