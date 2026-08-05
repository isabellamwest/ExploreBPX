"""New from an existing file: clone a file into a fresh unsaved main and
pin the origin as a read-only reference (Workspace rail entry, "From
existing file…") -- at the pin cap the clone is still created and the
source simply is not pinned (decision D2). Also pins the Save As
default-folder rule for never-saved mains, whose first real customer is
the clone.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from core import export
from core.bpx_gateway import LoadError
from state.app_state import REFERENCE_PIN_CAP, AppState, PinReferenceOutcome

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module
from PySide6.QtCore import QStandardPaths


@pytest.fixture
def origin_path(valid_spm_path, tmp_path) -> Path:
    """A writable copy of the valid SPM fixture named so the derived clone
    name ("main (copy).json") is observable."""
    path = tmp_path / "main.json"
    shutil.copy(valid_spm_path, path)
    return path


@pytest.fixture
def bad_path(tmp_path) -> Path:
    """A file that fails to parse as JSON/YAML at all."""
    path = tmp_path / "bad.json"
    path.write_text("{this is not json", encoding="utf-8")
    return path


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


# ---------------------------------------------------------------------------
# State layer: AppState.new_from_file
# ---------------------------------------------------------------------------


def test_new_from_file_clones_raw_and_derives_name(origin_path):
    state = AppState()
    state.new_from_file(origin_path)

    origin_raw = json.loads(origin_path.read_text("utf-8"))
    session = state.active
    assert session is not None
    assert session.document.raw == origin_raw
    assert session.document.filename == "main (copy).json"
    assert session.document.fmt == "json"
    assert session.dirty is True
    assert session.backing_file is None
    assert len(state.references) == 1
    assert state.references[0].path == origin_path


def test_new_from_file_preserves_yaml_format(valid_spm_dict, tmp_path):
    origin = tmp_path / "cell.yaml"
    origin.write_bytes(export.to_bytes(valid_spm_dict, "yaml"))
    state = AppState()
    state.new_from_file(origin)

    assert state.active.document.filename == "cell (copy).yaml"
    assert state.active.document.fmt == "yaml"


def test_new_from_file_unparseable_leaves_state_untouched(origin_path, bad_path):
    state = AppState()
    state.open(origin_path)
    before_session = state.active

    with pytest.raises(LoadError):
        state.new_from_file(bad_path)

    assert state.active is before_session
    assert state.active.backing_file == origin_path
    assert state.references == []


def test_new_from_file_keeps_snapshot_when_origin_is_already_pinned(origin_path):
    state = AppState()
    state.pin_reference(origin_path)
    snapshot = state.references[0]

    outcome = state.new_from_file(origin_path)

    assert outcome is PinReferenceOutcome.ALREADY_PINNED
    assert state.references == [snapshot]


def test_new_from_file_pins_beside_a_different_reference(origin_path, valid_spm_path, tmp_path):
    """Pinning appends: the origin joins any references already pinned."""
    other = tmp_path / "other.json"
    shutil.copy(valid_spm_path, other)
    state = AppState()
    state.pin_reference(other)

    outcome = state.new_from_file(origin_path)

    assert outcome is PinReferenceOutcome.PINNED
    assert [r.path for r in state.references] == [other, origin_path]


def test_new_from_file_at_cap_still_creates_the_clone_without_pinning(
    origin_path, valid_spm_path, tmp_path
):
    """Decision D2: at 4 pinned the new document is still created; the
    source is simply not pinned."""
    state = AppState()
    for index in range(REFERENCE_PIN_CAP):
        copy = tmp_path / f"pin_{index}.json"
        shutil.copy(valid_spm_path, copy)
        state.pin_reference(copy)
    before = list(state.references)

    outcome = state.new_from_file(origin_path)

    assert outcome is PinReferenceOutcome.AT_CAP
    assert state.active is not None
    assert state.active.document.filename == "main (copy).json"
    assert state.references == before


def test_new_from_file_origin_may_be_the_current_main(origin_path):
    state = AppState()
    state.open(origin_path)

    state.new_from_file(origin_path)

    assert state.active.document.filename == "main (copy).json"
    assert state.active.backing_file is None
    assert len(state.references) == 1
    assert state.references[0].path == origin_path


# ---------------------------------------------------------------------------
# UI flow: the Workspace rail row
# ---------------------------------------------------------------------------


def test_rail_row_label_and_descriptor(app_driver):
    label, descriptor = app_driver.workspace_new_from_file_texts()
    assert label == "From existing file…"
    assert descriptor == "Start from a copy · the file is pinned as a reference"


def test_click_flow_clones_docks_and_stays_on_workspace(app_driver, origin_path, monkeypatch):
    d = app_driver
    page_before = d.current_view_index()
    _stub_open_dialog(monkeypatch, origin_path)

    d.click_workspace_new_from_file()

    assert d.current_view_index() == page_before
    assert d.toast_text() == "New document from main.json · source pinned as reference"
    assert d.reference_pin_count() == 1
    assert "main" in d.reference_pin_header_texts()[0]
    assert "State: Modified" in d.workspace_info_text()
    assert not d.undo_enabled()
    assert d._w._state.active.document.filename == "main (copy).json"
    # Equal clone and origin: the comparison exists and reports no differences.
    assert d._w._comparisons != []
    assert d._w._comparisons[0].differ_count == 0


def test_picker_cancel_asks_no_guard_and_changes_nothing(app_driver, monkeypatch):
    d = app_driver
    _stub_open_dialog(monkeypatch, "")
    monkeypatch.setattr(
        d._w, "_confirm_new", lambda: pytest.fail("guard asked before a file was chosen")
    )

    d.click_workspace_new_from_file()

    assert d._w._state.active is None
    assert d.toast_text() is None


def test_guard_runs_after_picker_and_cancel_aborts(app_driver, origin_path, tmp_path, monkeypatch):
    d = app_driver
    d.open(origin_path)
    before_session = d._w._state.active
    other = tmp_path / "other.json"
    shutil.copy(origin_path, other)
    _stub_open_dialog(monkeypatch, other)
    asked = []
    monkeypatch.setattr(d._w, "_confirm_new", lambda: asked.append(True) or False)

    d.click_workspace_new_from_file()

    assert asked == [True]
    assert d._w._state.active is before_session
    assert d._w._state.references == []


def test_load_failure_after_guard_keeps_previous_session(
    app_driver, origin_path, bad_path, monkeypatch
):
    d = app_driver
    d.open(origin_path)
    before_session = d._w._state.active
    _stub_open_dialog(monkeypatch, bad_path)
    monkeypatch.setattr(d._w, "_confirm_new", lambda: True)
    errors = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        lambda parent, title, text: errors.append(title),
    )

    d.click_workspace_new_from_file()

    assert errors == ["Cannot open file"]
    assert d._w._state.active is before_session
    assert d._w._state.active.backing_file == origin_path
    assert d._w._state.references == []


# ---------------------------------------------------------------------------
# Save As default folder for never-saved mains
# ---------------------------------------------------------------------------


def _capture_save_dialog(monkeypatch, result="") -> list:
    captured = []

    def fake_get_save_file_name(parent, title, default, filt):
        captured.append(default)
        return (str(result) if result else "", "")

    monkeypatch.setattr(
        main_window_module.QFileDialog, "getSaveFileName", fake_get_save_file_name
    )
    return captured


def test_save_as_for_clone_suggests_documents_and_derived_name(
    app_driver, origin_path, monkeypatch
):
    d = app_driver
    _stub_open_dialog(monkeypatch, origin_path)
    d.click_workspace_new_from_file()
    captured = _capture_save_dialog(monkeypatch)

    assert d._w._save() is False  # dialog cancelled -- nothing written
    documents = QStandardPaths.writableLocation(QStandardPaths.DocumentsLocation)
    assert captured == [str(Path(documents) / "main (copy).json")]


def test_save_as_starts_in_the_last_save_folder(app_driver, origin_path, tmp_path, monkeypatch):
    d = app_driver
    _stub_open_dialog(monkeypatch, origin_path)
    d.click_workspace_new_from_file()
    target = tmp_path / "somewhere" / "cell_B.json"
    target.parent.mkdir()
    _capture_save_dialog(monkeypatch, result=target)
    assert d._w._save() is True

    monkeypatch.setattr(d._w, "_confirm_new", lambda: True)
    _stub_open_dialog(monkeypatch, origin_path)
    d.click_workspace_new_from_file()
    captured = _capture_save_dialog(monkeypatch)
    assert d._w._save() is False
    assert captured == [str(target.parent / "main (copy).json")]
