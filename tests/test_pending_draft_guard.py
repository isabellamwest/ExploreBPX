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
  save instead of writing a file without it.
"""

from __future__ import annotations

import json

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _on_disk(path):
    return json.loads(path.read_text(encoding="utf-8"))["Parameterisation"]["Cell"][
        "Nominal cell capacity [A.h]"
    ]


def test_save_applies_a_draft_the_user_never_pressed_enter_on(
    app_driver, spm_workfile
):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    assert window._state.active.dirty is False  # the draft is not in the document

    assert window._save() is True

    assert _on_disk(spm_workfile) == 6.5
    assert window._state.active.dirty is False


def test_an_applied_draft_is_a_single_undo_step(app_driver, spm_workfile):
    app_driver.open(spm_workfile).go_to(_CAPACITY)
    before = app_driver._w._state.active.document.raw["Parameterisation"]["Cell"][
        "Nominal cell capacity [A.h]"
    ]
    app_driver.edit_field(6.5)
    window = app_driver._w

    window._save()
    window._undo_document()

    assert (
        window._state.active.document.raw["Parameterisation"]["Cell"][
            "Nominal cell capacity [A.h]"
        ]
        == before
    )


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


def test_open_guard_offers_save_and_the_draft_reaches_the_file(
    app_driver, spm_workfile, monkeypatch
):
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


def test_new_guard_treats_a_draft_as_unsaved_work(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    asked = []

    def fake_question(*args, **kwargs):
        asked.append(args[1] if len(args) > 1 else None)
        return main_window_module.QMessageBox.Cancel

    monkeypatch.setattr(main_window_module.QMessageBox, "question", fake_question)

    assert window._confirm_new() is False
    # The dirty path, not the lightweight "this will replace X" confirm.
    assert asked == ["Unsaved changes"]


def test_a_blocked_draft_aborts_the_save(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.5)
    window = app_driver._w
    card = window._inspector._card
    monkeypatch.setattr(card, "commit_blocked_reason", lambda: "unparseable")
    original = _on_disk(spm_workfile)

    assert window._save() is False
    assert _on_disk(spm_workfile) == original


# ----------------------------------------------------------------------
# Export mirrors Save's own draft-flush semantics (see MainWindow._export_as)
# ----------------------------------------------------------------------


def test_export_applies_a_draft_the_user_never_pressed_enter_on(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
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


def test_export_aborts_when_the_draft_is_unwritable(
    app_driver, spm_workfile, tmp_path, monkeypatch
):
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
