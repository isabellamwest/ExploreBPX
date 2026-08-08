"""Tests for AppState's workspace-history recording: every open and every
reference change lands in the injected WorkspaceHistory, and sessions with no
on-disk identity never erase the last restorable workspace."""

from __future__ import annotations

from state.app_state import AppState
from state.workspace_history import ReferenceRecord, WorkspaceHistory

CHEN2020 = "pybamm/chen2020"


def _state(tmp_path):
    return AppState(history=WorkspaceHistory(tmp_path / "history.json"))


def test_open_records_recent_and_last_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)

    assert state.history.recent_files == [str(spm_workfile)]
    last = state.history.last_workspace
    assert last.main.path == str(spm_workfile)
    assert last.main.mode == "normal"
    assert last.references == ()


def test_read_only_open_records_its_mode(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open_read_only(spm_workfile)
    assert state.history.last_workspace.main.mode == "read_only"


def test_reference_changes_rewrite_the_last_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    ref_file = spm_workfile.parent / "ref.json"
    ref_file.write_text(spm_workfile.read_text())
    state.pin_reference_set(CHEN2020)
    state.pin_reference(ref_file)

    assert state.history.last_workspace.references == (
        ReferenceRecord(kind="library", set_id=CHEN2020),
        ReferenceRecord(kind="file", path=str(ref_file)),
    )

    state.remove_reference(state.references[0])
    assert state.history.last_workspace.references == (
        ReferenceRecord(kind="file", path=str(ref_file)),
    )


def test_scaffold_does_not_erase_the_last_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    state.pin_reference_set(CHEN2020)

    state.new_document("SPM")
    state.pin_reference_set("pybamm/prada2013")  # pin while on the scaffold

    last = state.history.last_workspace
    assert last.main.path == str(spm_workfile)
    assert last.references == (ReferenceRecord(kind="library", set_id=CHEN2020),)
    assert state.current_workspace_record() is None  # nothing to name yet


def test_new_from_file_earns_a_recent_row_but_not_a_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.new_from_file(spm_workfile)
    assert state.history.recent_files == [str(spm_workfile)]
    assert state.history.last_workspace is None


def test_saving_a_scaffold_gives_it_an_identity(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.new_document("SPM")
    assert state.history.last_workspace is None

    target = tmp_path / "fresh.json"
    state.active.backing_file = target
    state.active.save()
    state.note_main_saved()

    assert state.history.recent_files == [str(target)]
    assert state.history.last_workspace.main.path == str(target)
    assert state.history.last_workspace.main.mode == "normal"
    assert state.current_workspace_record() is not None


def test_close_keeps_the_record_but_stops_tracking(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    state.close()
    state.pin_reference_set(CHEN2020)  # pin with no main open

    last = state.history.last_workspace
    assert last.main.path == str(spm_workfile)
    assert last.references == ()  # the closed workspace's pins, not the new one


def test_history_free_state_records_nothing_and_never_crashes(spm_workfile):
    state = AppState()  # the default every existing test constructs
    state.open(spm_workfile)
    state.pin_reference_set(CHEN2020)
    state.new_document("SPM")
    state.note_main_saved()
    assert state.history is None
