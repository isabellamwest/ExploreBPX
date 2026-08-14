"""The save gates: the stale-on-disk block and the once-per-document YAML
comment confirmation.

Both dialogs are dumb overridable seams (``_ask_stale_resolution`` /
``_ask_comment_loss``, the ``_ask_open_intent`` convention), so these tests
drive the real gate logic in ``_save`` and monkeypatch only the ask; one
test per dialog exercises the actual QMessageBox via the zero-delay
``QTimer.singleShot`` + ``activeModalWidget()`` idiom (``exec()`` truly
blocks offscreen; a Python monkeypatch of ``.exec()`` does not intercept it).
"""

from __future__ import annotations

import json
import os
from datetime import datetime

import pytest

pytest.importorskip("PySide6")

import yaml
from platform_facts import assert_alert_title
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

import ui_qt.main_window as main_window_module
from core.document import BPXDocument
from core.load_record import LoadRecord
from state.app_state import AppState
from state.document_session import DocumentSession
from ui_qt.main_window import StaleChoice, _format_disk_time

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")


def _bump_mtime(path, seconds: float = 120.0) -> float:
    """Age *path*'s mtime forward deterministically (no sleeping) and
    return the new value -- what an external edit leaves behind."""
    stat = path.stat()
    os.utime(path, (stat.st_atime, stat.st_mtime + seconds))
    return path.stat().st_mtime


def _capacity_on_disk(path) -> float:
    raw = json.loads(path.read_text("utf-8"))
    return raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]


def _arm_stale(window, monkeypatch, choice, calls=None):
    def fake_ask(filename, disk_mtime):
        if calls is not None:
            calls.append((filename, disk_mtime))
        return choice

    monkeypatch.setattr(window, "_ask_stale_resolution", fake_ask)


def _arm_comment(window, monkeypatch, answer, calls=None):
    def fake_ask(source_name, document_name):
        if calls is not None:
            calls.append((source_name, document_name))
        return answer

    monkeypatch.setattr(window, "_ask_comment_loss", fake_ask)


@pytest.fixture
def commented_yaml_workfile(valid_spm_dict, tmp_path):
    """A writable YAML copy of the valid SPM fixture with a comment line."""
    text = "# calibration notes\n" + yaml.safe_dump(valid_spm_dict, sort_keys=False)
    path = tmp_path / "cell.yaml"
    path.write_text(text, encoding="utf-8")
    return path


@pytest.fixture
def plain_yaml_workfile(valid_spm_dict, tmp_path):
    path = tmp_path / "plain.yaml"
    path.write_text(yaml.safe_dump(valid_spm_dict, sort_keys=False), encoding="utf-8")
    return path


# ----------------------------------------------------------------------
# stale-on-disk block
# ----------------------------------------------------------------------


def test_save_with_unchanged_disk_never_asks(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    calls = []
    _arm_stale(window, monkeypatch, StaleChoice.CANCEL, calls)
    assert window._save() is True
    assert calls == []
    assert window._state.active.dirty is False


def test_stale_cancel_blocks_the_save(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    disk_mtime = _bump_mtime(spm_workfile)
    calls = []
    _arm_stale(window, monkeypatch, StaleChoice.CANCEL, calls)
    assert window._save() is False
    assert calls == [(spm_workfile.name, disk_mtime)]
    assert window._state.active.dirty is True
    assert _capacity_on_disk(spm_workfile) != 6.0


def test_stale_overwrite_saves_and_the_check_rearms(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    _bump_mtime(spm_workfile)
    calls = []
    _arm_stale(window, monkeypatch, StaleChoice.OVERWRITE, calls)
    assert window._save() is True
    assert len(calls) == 1
    assert _capacity_on_disk(spm_workfile) == 6.0
    # save() re-captured the record from the written file, so the next save
    # over an untouched disk asks nothing.
    app_driver.go_to(_CAPACITY).edit_field(7.0).commit()
    assert window._save() is True
    assert len(calls) == 1


def test_stale_reload_discards_and_opens_the_disk_version(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    raw = json.loads(spm_workfile.read_text("utf-8"))
    raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = 9.9
    spm_workfile.write_text(json.dumps(raw), encoding="utf-8")
    _bump_mtime(spm_workfile)
    _arm_stale(window, monkeypatch, StaleChoice.RELOAD)
    assert window._save() is False
    session = window._state.active
    assert session.document.raw["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] == 9.9
    assert session.dirty is False


def test_stale_save_as_copy_retargets_and_leaves_the_disk_version(app_driver, spm_workfile, tmp_path, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    _bump_mtime(spm_workfile)
    disk_before = spm_workfile.read_bytes()
    copy_path = tmp_path / "kept-elsewhere.json"
    seen = {}

    def fake_get_save_file_name(parent, caption, start, filter_):
        seen["start"] = start
        return (str(copy_path), "")

    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName", fake_get_save_file_name)
    _arm_stale(window, monkeypatch, StaleChoice.SAVE_AS_COPY)
    assert window._save() is True
    session = window._state.active
    assert session.backing_file == copy_path
    assert session.dirty is False
    assert _capacity_on_disk(copy_path) == 6.0
    # The changed disk version keeps its file, byte for byte.
    assert spm_workfile.read_bytes() == disk_before
    # The proposed name is the Export convention, beside the backing file.
    assert seen["start"].endswith(f"{spm_workfile.stem} (copy){spm_workfile.suffix}")


def test_stale_save_as_copy_cancelled_saves_nothing(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    _bump_mtime(spm_workfile)
    monkeypatch.setattr(main_window_module.QFileDialog, "getSaveFileName", lambda *a, **k: ("", ""))
    _arm_stale(window, monkeypatch, StaleChoice.SAVE_AS_COPY)
    assert window._save() is False
    session = window._state.active
    assert session.backing_file == spm_workfile
    assert session.dirty is True


def test_stale_save_as_copy_failure_restores_the_backing_file(app_driver, spm_workfile, tmp_path, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    _bump_mtime(spm_workfile)
    session = window._state.active
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: (str(tmp_path / "target.json"), ""),
    )
    monkeypatch.setattr(main_window_module.QMessageBox, "critical", lambda *a, **k: None)

    def failing_save():
        raise OSError("disk full")

    monkeypatch.setattr(session, "save", failing_save)
    _arm_stale(window, monkeypatch, StaleChoice.SAVE_AS_COPY)
    assert window._save() is False
    # Unlike a failed first Save As (backing reset to None), the original
    # path was valid and must survive the failed copy.
    assert session.backing_file == spm_workfile


def test_deleted_backing_file_saves_without_asking(app_driver, spm_workfile, monkeypatch):
    """A vanished file blocks nothing: a save there can destroy no newer
    version, so Save simply writes the file again."""
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    spm_workfile.unlink()
    calls = []
    _arm_stale(window, monkeypatch, StaleChoice.CANCEL, calls)
    assert window._save() is True
    assert calls == []
    assert _capacity_on_disk(spm_workfile) == 6.0


def test_stale_mtime_state_facts(spm_workfile):
    state = AppState()
    state.open(spm_workfile)
    session = state.active
    assert session.stale_mtime() is None
    bumped = _bump_mtime(spm_workfile)
    assert session.stale_mtime() == bumped
    session.load_record = None
    assert session.stale_mtime() is None


def test_disk_time_same_day_is_time_only():
    now = datetime.now()
    assert _format_disk_time(now.timestamp()) == f"at {now:%H:%M}"


def test_disk_time_another_day_names_the_date():
    moment = datetime(2026, 3, 5, 14, 22)
    assert _format_disk_time(moment.timestamp()) == "on 5 Mar 2026 at 14:22"


# ----------------------------------------------------------------------
# YAML comment confirmation
# ----------------------------------------------------------------------


def test_commented_yaml_cancel_blocks_the_first_save(app_driver, commented_yaml_workfile, monkeypatch):
    app_driver.open(commented_yaml_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    calls = []
    _arm_comment(window, monkeypatch, False, calls)
    assert window._save() is False
    assert calls == [("cell.yaml", "cell.yaml")]
    assert "# calibration notes" in commented_yaml_workfile.read_text("utf-8")
    assert window._state.active.dirty is True


def test_commented_yaml_confirm_saves_and_never_asks_again(app_driver, commented_yaml_workfile, monkeypatch):
    app_driver.open(commented_yaml_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    calls = []
    _arm_comment(window, monkeypatch, True, calls)
    assert window._save() is True
    assert len(calls) == 1
    assert "calibration notes" not in commented_yaml_workfile.read_text("utf-8")
    # The written file truthfully carries no comments, so the re-captured
    # record cleared the fact and the next save asks nothing.
    assert window._state.active.load_record.has_yaml_comments is False
    app_driver.go_to(_CAPACITY).edit_field(7.0).commit()
    assert window._save() is True
    assert len(calls) == 1


def test_json_document_never_asks(app_driver, spm_workfile, monkeypatch):
    app_driver.open(spm_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    calls = []
    _arm_comment(window, monkeypatch, False, calls)
    assert window._save() is True
    assert calls == []


def test_uncommented_yaml_never_asks(app_driver, plain_yaml_workfile, monkeypatch):
    app_driver.open(plain_yaml_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    calls = []
    _arm_comment(window, monkeypatch, False, calls)
    assert window._save() is True
    assert calls == []


def test_clone_of_commented_source_names_both_files(app_driver, commented_yaml_workfile, monkeypatch):
    """A never-saved session whose content came from another file (the shape
    a converted copy has) keeps its comments in that origin: the dialog's
    first sentence names the origin, the asked-once sentence the document.

    The session is built here rather than opened, because the one flow that
    produced this shape from an ordinary file has been retired; the shape
    itself is still reachable through the legacy converted-copy route.
    """
    window = app_driver._w
    data = commented_yaml_workfile.read_bytes()
    document = BPXDocument.from_bytes(data, "cell (copy).yaml")
    session = DocumentSession(document)
    session.dirty = True
    session.load_record = LoadRecord.capture(data, document, path=commented_yaml_workfile)
    window._state.active = session
    calls = []
    _arm_comment(window, monkeypatch, False, calls)
    assert window._confirm_comment_loss(session) is False
    assert calls == [("cell.yaml", "cell (copy).yaml")]


def test_stale_asks_first_then_comments_on_one_save(app_driver, commented_yaml_workfile, monkeypatch):
    app_driver.open(commented_yaml_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    _bump_mtime(commented_yaml_workfile)
    order = []
    monkeypatch.setattr(
        window,
        "_ask_stale_resolution",
        lambda *a: order.append("stale") or StaleChoice.OVERWRITE,
    )
    monkeypatch.setattr(window, "_ask_comment_loss", lambda *a: order.append("comments") or True)
    assert window._save() is True
    assert order == ["stale", "comments"]


def test_stale_save_as_copy_still_confirms_comment_loss(app_driver, commented_yaml_workfile, monkeypatch):
    """The copy written by Save as copy is comment-free too, so consent
    comes before its file dialog ever opens."""
    app_driver.open(commented_yaml_workfile).go_to(_CAPACITY).edit_field(6.0).commit()
    window = app_driver._w
    _bump_mtime(commented_yaml_workfile)
    monkeypatch.setattr(
        main_window_module.QFileDialog,
        "getSaveFileName",
        lambda *a, **k: pytest.fail("file dialog opened before comment consent"),
    )
    _arm_stale(window, monkeypatch, StaleChoice.SAVE_AS_COPY)
    _arm_comment(window, monkeypatch, False)
    assert window._save() is False
    assert window._state.active.dirty is True


# ----------------------------------------------------------------------
# one real-dialog test per box (the rest monkeypatch them)
# ----------------------------------------------------------------------


def test_stale_dialog_real_box_words_and_default(app_driver):
    window = app_driver._w
    captured: dict = {}

    def _cancel():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["title"] = box.windowTitle()
            captured["text"] = box.text()
            captured["informative"] = box.informativeText()
            captured["labels"] = [b.text() for b in box.buttons()]
            captured["default"] = box.defaultButton().text()
            for button in box.buttons():
                if button.text() == "Cancel":
                    button.click()
                    return

    QTimer.singleShot(0, _cancel)
    moment = datetime(2026, 3, 5, 14, 22)
    choice = window._ask_stale_resolution("lgm50.json", moment.timestamp())

    assert choice is StaleChoice.CANCEL
    assert_alert_title(captured["title"], "Cannot save")
    assert captured["text"] == (
        "lgm50.json changed on disk on 5 Mar 2026 at 14:22, after it was "
        "opened here. Saving now would replace that version."
    )
    assert captured["informative"] == (
        "Reload discards your unsaved changes and opens the disk version. "
        "Save as copy writes your version to a new file and leaves the "
        "disk version alone. Overwrite replaces the disk version with "
        "your version."
    )
    assert set(captured["labels"]) == {
        "Reload",
        "Save as copy…",
        "Overwrite",
        "Cancel",
    }
    assert captured["default"] == "Save as copy…"


def test_comment_dialog_real_box_words_and_default(app_driver):
    window = app_driver._w
    captured: dict = {}

    def _confirm():
        box = QApplication.instance().activeModalWidget()
        if box is not None:
            captured["title"] = box.windowTitle()
            captured["text"] = box.text()
            captured["informative"] = box.informativeText()
            captured["default"] = box.defaultButton().text()
            for button in box.buttons():
                if button.text() == "Save without comments":
                    button.click()
                    return

    QTimer.singleShot(0, _confirm)
    answer = window._ask_comment_loss("nmc_pouch.yaml", "nmc_pouch.yaml")

    assert answer is True
    assert_alert_title(captured["title"], "Comments will not survive saving")
    assert captured["text"] == (
        "nmc_pouch.yaml contains comments. Saving rewrites the whole file: comments and formatting will not survive."
    )
    assert captured["informative"] == (
        "This is asked once for nmc_pouch.yaml. The file record keeps the note either way."
    )
    assert captured["default"] == "Cancel"
