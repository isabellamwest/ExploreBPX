"""Tests for AppState's workspace recording: opening a file starts or swaps
into a workspace, every reference change rewrites it live, and sessions with
no on-disk identity never rewrite the workspace they were started from."""

from __future__ import annotations

from state.app_state import AppState
from state.workspace_history import ReferenceRecord, WorkspaceHistory

CHEN2020 = "pybamm/chen2020"


def _state(tmp_path):
    return AppState(history=WorkspaceHistory(tmp_path / "history.json"))


def test_open_records_recent_and_starts_a_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)

    assert state.history.recent_files == [str(spm_workfile)]
    current = state.history.current()
    assert current.main.path == str(spm_workfile)
    assert current.main.mode == "normal"
    assert current.references == ()
    assert current.name is None  # untitled until named
    assert state.workspace_id == current.id


def test_read_only_open_records_its_mode(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open_read_only(spm_workfile)
    assert state.history.current().main.mode == "read_only"


def test_reference_changes_rewrite_the_current_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    ref_file = spm_workfile.parent / "ref.json"
    ref_file.write_text(spm_workfile.read_text())
    state.pin_reference_set(CHEN2020)
    state.pin_reference(ref_file)

    assert state.history.current().references == (
        ReferenceRecord(kind="library", set_id=CHEN2020),
        ReferenceRecord(kind="file", path=str(ref_file)),
    )

    state.remove_reference(state.references[0])
    assert state.history.current().references == (
        ReferenceRecord(kind="file", path=str(ref_file)),
    )


# ---------------------------------------------------------------------------
# opening a file: swap in place, except beside a named workspace


def test_opening_another_file_swaps_the_main_of_an_untitled_workspace(
    tmp_path, spm_workfile, second_workfile
):
    state = _state(tmp_path)
    state.open(spm_workfile)
    started = state.workspace_id
    state.pin_reference_set(CHEN2020)

    state.open(second_workfile)

    current = state.history.current()
    assert current.id == started  # the same workspace, a different main
    assert current.main.path == str(second_workfile)
    assert current.references == (ReferenceRecord(kind="library", set_id=CHEN2020),)
    assert len(state.history.recent_workspaces) == 1  # nothing piled up


def test_opening_a_file_beside_a_named_workspace_leaves_it_alone(
    tmp_path, spm_workfile, second_workfile
):
    """Naming a workspace is the act that says "stop rewriting this", so an
    ordinary open starts a fresh untitled workspace instead."""
    state = _state(tmp_path)
    state.open(spm_workfile)
    state.pin_reference_set(CHEN2020)
    kept = state.history.keep(state.workspace_id, "LG M50 study")

    state.open(second_workfile)

    named = state.history.named("LG M50 study")
    assert named.id == kept.id
    assert named.main.path == str(spm_workfile)  # untouched
    assert named.references == (ReferenceRecord(kind="library", set_id=CHEN2020),)

    current = state.history.current()
    assert current.id != kept.id
    assert current.name is None
    assert current.main.path == str(second_workfile)
    # The references were still pinned, so they came along.
    assert current.references == (ReferenceRecord(kind="library", set_id=CHEN2020),)


def test_reopening_the_same_main_is_not_a_swap(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    kept = state.history.keep(state.workspace_id, "study")

    state.open(spm_workfile)

    assert state.workspace_id == kept.id
    assert state.history.recent_workspaces == []  # no stray untitled entry


def test_a_named_workspace_still_tracks_its_references_live(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    kept = state.history.keep(state.workspace_id, "study")

    state.pin_reference_set(CHEN2020)

    live = state.history.named("study")
    assert live.id == kept.id
    assert live.references == (ReferenceRecord(kind="library", set_id=CHEN2020),)


# ---------------------------------------------------------------------------
# starting and entering workspaces


def test_new_workspace_clears_the_board_without_discarding_anything(
    tmp_path, spm_workfile
):
    state = _state(tmp_path)
    state.open(spm_workfile)
    state.pin_reference_set(CHEN2020)
    shelved = state.workspace_id

    state.new_workspace()

    assert state.active is None
    assert state.references == []
    assert state.workspace_id is None
    # Shelved, not discarded: it is still there to come back to.
    assert state.history.by_id(shelved) is not None
    assert state.history.by_id(shelved).references == (
        ReferenceRecord(kind="library", set_id=CHEN2020),
    )


def test_entering_a_workspace_adopts_its_main_before_anything_opens(
    tmp_path, spm_workfile
):
    state = _state(tmp_path)
    state.open(spm_workfile)
    target = state.workspace_id
    state.new_workspace()

    state.enter_workspace(target)

    assert state.workspace_id == target
    # The recorded main is adopted up front, so a main that no longer opens
    # still leaves the workspace pointing at where it was.
    assert state.current_workspace_record().main.path == str(spm_workfile)


def test_opens_after_entering_land_in_that_workspace(
    tmp_path, spm_workfile, second_workfile
):
    state = _state(tmp_path)
    state.open(spm_workfile)
    target = state.workspace_id
    state.new_workspace()
    state.open(second_workfile)  # a separate line of work
    assert state.workspace_id != target

    state.enter_workspace(target)
    state.open(spm_workfile)

    assert state.workspace_id == target
    assert len(state.history.recent_workspaces) == 2


# ---------------------------------------------------------------------------
# sessions with no on-disk identity


def test_scaffold_does_not_rewrite_the_workspace_it_came_from(
    tmp_path, spm_workfile
):
    state = _state(tmp_path)
    state.open(spm_workfile)
    state.pin_reference_set(CHEN2020)

    state.new_document("SPM")
    state.pin_reference_set("pybamm/prada2013")  # pin while on the scaffold

    current = state.history.current()
    assert current.main.path == str(spm_workfile)
    assert current.references == (ReferenceRecord(kind="library", set_id=CHEN2020),)
    assert state.current_workspace_record() is None  # nothing to name yet


def test_new_from_file_earns_a_recent_row_but_not_a_workspace(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.new_from_file(spm_workfile)
    assert state.history.recent_files == [str(spm_workfile)]
    assert state.history.current() is None
    assert state.history.recent_workspaces == []


def test_saving_a_scaffold_gives_it_an_identity(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.new_document("SPM")
    assert state.history.current() is None

    target = tmp_path / "fresh.json"
    state.active.backing_file = target
    state.active.save()
    state.note_main_saved()

    assert state.history.recent_files == [str(target)]
    assert state.history.current().main.path == str(target)
    assert state.history.current().main.mode == "normal"
    assert state.current_workspace_record() is not None


def test_close_keeps_the_record_but_stops_tracking(tmp_path, spm_workfile):
    state = _state(tmp_path)
    state.open(spm_workfile)
    state.close()
    state.pin_reference_set(CHEN2020)  # pin with no main open

    current = state.history.current()
    assert current.main.path == str(spm_workfile)
    assert current.references == ()  # the closed workspace's pins, not the new one


def test_history_free_state_records_nothing_and_never_crashes(spm_workfile):
    state = AppState()  # the default every existing test constructs
    state.open(spm_workfile)
    state.pin_reference_set(CHEN2020)
    state.new_document("SPM")
    state.note_main_saved()
    state.new_workspace()
    state.enter_workspace("anything")
    assert state.history is None
    assert state.workspace_id is None
