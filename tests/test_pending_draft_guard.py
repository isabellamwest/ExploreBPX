"""A typed-but-not-committed card draft must not vanish silently.

A card draft lives outside the document until Enter, so ``session.dirty``
stays False while a real edit sits on screen. Every file-level action used
to walk straight past it: Save wrote the old value and reported success,
and Open/New/close/Make-main reported "nothing to lose".

The contract now matches what a spreadsheet or a form does:

- Save applies the draft first, so what is on screen reaches the file;
- the destructive actions count the draft as unsaved work, so the existing
  Save/Discard/Cancel prompt appears;
- a draft that *cannot* be written (``commit_blocked_reason``) aborts the
  save instead of writing a file without it -- and the abort is spoken: a
  toast names the blocked edit, the reason, and offers the Editor page,
  because the card's inline reason is invisible from every other page.
  The toast dismisses itself, so the refusal also persists as a status-bar
  chip that stays until the blocked draft is fixed, discarded or replaced.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

import explore_bpx.ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _on_disk(path):
    return json.loads(path.read_text(encoding="utf-8"))["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]


def test_save_applies_a_draft_the_user_never_pressed_enter_on(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    assert window._state.active.dirty is False  # the draft is not in the document

    assert window._save() is True

    assert _on_disk(spm_workfile) == 6.5
    assert window._state.active.dirty is False


def test_an_applied_draft_is_a_single_undo_step(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY)
    before = app_driver._w._state.active.document.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    app_driver.edit_field(6.5)
    window = app_driver._w

    window._save()
    window._undo_document()

    assert window._state.active.document.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == before


def test_save_without_a_draft_is_unchanged(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5).commit()
    window = app_driver._w

    assert window._save() is True
    assert _on_disk(spm_workfile) == 6.5


def test_open_guard_treats_a_draft_as_unsaved_work(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    assert window._state.active.dirty is False

    assert window._has_unsaved_work() is True


def test_open_guard_offers_save_and_the_draft_reaches_the_file(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *a, **k: main_window_module.QMessageBox.Save,
    )

    assert window._confirm_discard_if_dirty() is True
    assert _on_disk(spm_workfile) == 6.5


def test_open_guard_cancel_keeps_the_draft(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    original = _on_disk(spm_workfile)
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *a, **k: main_window_module.QMessageBox.Cancel,
    )

    assert window._confirm_discard_if_dirty() is False
    assert _on_disk(spm_workfile) == original
    assert window._has_unsaved_work() is True


def test_new_workspace_treats_a_draft_as_unsaved_work(app_driver, spm_workfile, monkeypatch):
    """A pending draft is unsaved work wherever the discard guard runs.
    New workspace is where that matters now: New document has no guard,
    because it is only offered on a board with nothing to lose."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    before = window._state.workspace_id
    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args[1] if len(args) > 1 else None)
        return main_window_module.QMessageBox.Cancel

    monkeypatch.setattr(main_window_module.QMessageBox, "question", fake_question)

    app_driver.click_new_workspace()

    assert asked == ["Unsaved changes"]
    assert window._state.workspace_id == before  # nothing was started
    assert window._state.active is not None


def test_a_blocked_draft_aborts_the_save(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")
    original = _on_disk(spm_workfile)

    assert window._save() is False
    assert _on_disk(spm_workfile) == original


def test_a_blocked_save_refuses_out_loud(app_driver, spm_workfile, monkeypatch):
    """The abort names what is blocked, why, and the way back -- checked
    from another page, where the card's inline reason cannot be seen."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")
    app_driver.show_view("Workspace")

    assert window._save() is False

    assert app_driver.toast_text() == (
        'Cannot save: the edit to "Nominal cell capacity [A.h]" cannot be written. unparseable'
    )
    assert app_driver.toast_action_text() == "Show in Editor"
    # The way back changes no selection: the draft is still there to repair.
    app_driver.toast_click_action()
    assert app_driver.current_view_name() == "Editor"
    assert window._inspector.has_pending_draft()


def test_the_guard_save_choice_refuses_out_loud(app_driver, spm_workfile, monkeypatch):
    """Choosing "Save" in the Save/Discard/Cancel guard used to abort with
    no sign at all when the draft was blocked -- the dialog closed, nothing
    saved, nothing said."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "question",
        lambda *a, **k: main_window_module.QMessageBox.Save,
    )

    assert window._confirm_discard_if_dirty() is False
    assert app_driver.toast_text().startswith("Cannot save:")


# ----------------------------------------------------------------------
# The refusal persists: a status-bar chip outlives the toast and retires
# itself when the block it names stops existing (MainWindow._blocked_chip)
# ----------------------------------------------------------------------


def test_a_blocked_save_leaves_a_persistent_status_chip(app_driver, spm_workfile, monkeypatch):
    """The toast auto-dismisses; the chip does not. It names the blocked
    edit and the way back; the tooltip repeats the sentence (a squeezed
    status bar clips the chip with no ellipsis) and adds the reason."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    monkeypatch.setattr(window._inspector._card, "commit_blocked_reason", lambda: "unparseable")
    app_driver.show_view("Workspace")

    assert window._save() is False

    assert app_driver.blocked_write_chip_text() == (
        'Save blocked · fix or discard the edit to "Nominal cell capacity [A.h]"'
    )
    assert window._blocked_chip.toolTip() == (
        'Save blocked · fix or discard the edit to "Nominal cell capacity [A.h]"\nunparseable'
    )


def test_the_chip_links_back_to_the_editor(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    monkeypatch.setattr(window._inspector._card, "commit_blocked_reason", lambda: "unparseable")
    app_driver.show_view("Workspace")
    window._save()

    app_driver.blocked_write_chip_click()

    assert app_driver.current_view_name() == "Editor"
    assert window._inspector.has_pending_draft()  # still there to repair


def test_the_chip_retires_once_the_draft_is_writable(app_driver, spm_workfile, monkeypatch):
    """Editing the draft into something writable clears the refusal via the
    debounced ``_validate_draft`` (fired directly here, the suite's usual
    debounce bypass)."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")
    assert window._save() is False
    assert app_driver.blocked_write_chip_text() is not None

    monkeypatch.setattr(card, "commit_blocked_reason", lambda: None)
    window._inspector._validate_draft()

    assert app_driver.blocked_write_chip_text() is None


def test_the_chip_retires_when_the_card_is_replaced(app_driver, spm_workfile, monkeypatch):
    """Navigating away drops the draft with its card -- nothing blocks the
    next save, so nothing may keep claiming to."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    monkeypatch.setattr(window._inspector._card, "commit_blocked_reason", lambda: "unparseable")
    assert window._save() is False
    assert app_driver.blocked_write_chip_text() is not None

    app_driver.go_to(("Header", "BPX"))

    assert app_driver.blocked_write_chip_text() is None


def test_the_chip_retires_when_the_draft_is_discarded(app_driver, spm_workfile, monkeypatch):
    """Escape's ``_reset_draft`` clears ``_touched`` before ``draft_reset``
    fires, so the chip's re-check already sees a clean card. Fired on the
    inner editor, the widget Escape actually reaches."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")
    assert window._save() is False
    assert app_driver.blocked_write_chip_text() is not None

    card._editor._reset_draft()

    assert app_driver.blocked_write_chip_text() is None


# ----------------------------------------------------------------------
# Export mirrors Save's own draft-flush semantics (see MainWindow._export_as)
# ----------------------------------------------------------------------


def test_export_applies_a_draft_the_user_never_pressed_enter_on(app_driver, spm_workfile, tmp_path, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    assert window._state.active.dirty is False  # the draft is not in the document

    export_path = tmp_path / "exported.json"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(export_path), ""),
    )

    window._export_as("json")

    assert export_path.exists()
    assert _on_disk(export_path) == 6.5


def test_export_aborts_when_the_draft_is_unwritable(app_driver, spm_workfile, tmp_path, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")

    export_path = tmp_path / "exported.json"
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(export_path), ""),
    )

    window._export_as("json")

    assert not export_path.exists()


def test_a_blocked_export_refuses_out_loud(app_driver, spm_workfile, monkeypatch):
    """Export's refusal speaks too, before any file dialog appears."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")

    window._export_as("json")

    assert app_driver.toast_text().startswith("Cannot export:")
    assert app_driver.blocked_write_chip_text().startswith("Export blocked")
