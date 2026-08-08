"""Workflow tests for the Workspace rail's persistent history (increment 1:
the automatic Recent group — recents, the resume row, missing files).

Every test drives a live MainWindow through AppDriver; "relaunching the app"
is building a second window over the same history file. Widget knowledge
lives in ui_driver.py."""

from __future__ import annotations

import shutil

import pytest

pytest.importorskip("PySide6")

CHEN2020 = "pybamm/chen2020"


@pytest.fixture
def history_path(tmp_path):
    return tmp_path / "workspace_history.json"


@pytest.fixture
def relaunch(qtbot, history_path):
    """Build a fresh window + driver over the same on-disk history store.

    Calling it again is an app relaunch: nothing carries over but the file.
    """

    def build():
        from ui_driver import AppDriver
        from state.workspace_history import WorkspaceHistory
        from ui_qt.main_window import MainWindow

        window = MainWindow(history=WorkspaceHistory(history_path))
        qtbot.addWidget(
            window,
            before_close_func=lambda w: setattr(w, "_suppress_close_guard", True),
        )
        return AppDriver(window, qtbot)

    return build


@pytest.fixture
def second_file(spm_workfile, tmp_path):
    copy = tmp_path / "second.json"
    shutil.copyfile(spm_workfile, copy)
    return copy


def test_opened_files_survive_a_relaunch_newest_first(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(spm_workfile)
    first.open(second_file)

    fresh = relaunch()
    names = fresh.history_row_names()
    # Resume row first (labelled with the last main), then recents.
    assert fresh.resume_row_present()
    assert names[0] == second_file.name
    assert names[1:] == [second_file.name, spm_workfile.name]


def test_resume_restores_main_and_references_in_order(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first._w._open_reference_path(second_file)

    fresh = relaunch()
    fresh.click_resume_row()

    state = fresh._w._state
    assert state.active is not None
    assert state.active.backing_file == spm_workfile
    assert [ref.set_id for ref in state.references] == [CHEN2020, None]
    assert state.references[1].path == second_file


def test_resume_row_hides_while_a_document_is_open(relaunch, spm_workfile):
    first = relaunch()
    first.open(spm_workfile)
    fresh = relaunch()
    assert fresh.resume_row_present()

    fresh.open(spm_workfile)
    assert not fresh.resume_row_present()
    # The plain recent rows stay: they are still shortcuts mid-session.
    assert fresh.history_row_names() == [spm_workfile.name]


def test_missing_file_is_struck_through_and_removed_only_explicitly(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(spm_workfile)
    first.open(second_file)
    second_file.unlink()

    fresh = relaunch()
    assert fresh.history_row_is_missing(second_file.name)
    assert not fresh.history_row_is_missing(spm_workfile.name)

    # The row answers only its explicit ✕ -- never silent pruning. Only the
    # recents list changes: the last-workspace record keeps its own row.
    fresh.click_history_row_button(second_file.name, "✕")
    assert second_file.name not in fresh.recent_row_names()
    assert spm_workfile.name in fresh.recent_row_names()


def test_recent_row_click_opens_the_file(relaunch, spm_workfile):
    relaunch().open(spm_workfile)

    fresh = relaunch()
    fresh.click_history_row(spm_workfile.name)
    assert fresh._w._state.active is not None
    assert fresh._w._state.active.backing_file == spm_workfile


def test_recent_row_pin_docks_the_file_as_reference(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(spm_workfile)
    first.open(second_file)

    fresh = relaunch()
    fresh.open(spm_workfile)
    fresh.show_view("Workspace")
    fresh.click_history_row_button(second_file.name, "Pin")

    state = fresh._w._state
    assert state.active.backing_file == spm_workfile  # main untouched
    assert [ref.path for ref in state.references] == [second_file]


def test_partial_restore_opens_what_exists_and_names_what_does_not(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first._w._open_reference_path(second_file)
    second_file.unlink()

    fresh = relaunch()
    fresh.click_resume_row()

    state = fresh._w._state
    assert state.active.backing_file == spm_workfile
    assert [ref.set_id for ref in state.references] == [CHEN2020]
    assert fresh.toast_text() == f"1 reference not restored: {second_file.name}"


def test_dirty_guard_runs_before_a_restore(relaunch, spm_workfile, second_file):
    first = relaunch()
    first.open(second_file)

    fresh = relaunch()
    fresh.open(spm_workfile)
    fresh.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    fresh.edit_field("9.5").commit()
    assert fresh._w._state.active.dirty

    # Cancel at the unsaved-changes prompt stops the whole restore.
    fresh._w._confirm_discard_if_dirty = lambda: False
    fresh.show_view("Workspace")
    # The resume row is hidden while a document is open; the restore engine
    # is still reachable for the recent row via the replace-main intent --
    # drive the guarded engine directly at its seam.
    fresh._w._restore_workspace(fresh._w._state.history.last_workspace)
    assert fresh._w._state.active.backing_file == spm_workfile  # unchanged


def test_corrupt_history_resets_and_announces_itself(
    relaunch, history_path, qtbot
):
    history_path.write_text("{broken")
    fresh = relaunch()
    qtbot.wait(10)  # the notice is deferred one tick
    assert fresh.toast_text() == "Workspace history was unreadable and has been reset"
    assert fresh.history_row_names() == []


# ---------------------------------------------------------------------------
# Increment 2: named workspaces


def _save_workspace_as(driver, name):
    """Answer the name dialog with *name* through its monkeypatch seam (the
    ``_ask_open_intent`` convention), then click Save."""
    driver._w._ask_workspace_name = lambda *args: name
    try:
        driver.click_workspace_save()
    finally:
        del driver._w._ask_workspace_name


def test_save_needs_a_document_with_an_on_disk_identity(relaunch, spm_workfile):
    fresh = relaunch()
    # Nothing open: the group is hidden outright on a true first launch.
    assert not fresh.workspace_save_button_enabled()

    fresh.open(spm_workfile)
    fresh.show_view("Workspace")
    assert fresh.workspace_save_button_enabled()

    fresh._w._confirm_new = lambda: True  # the real replace-confirm blocks
    fresh.click_workspace_new("SPM")
    # A scaffold has no path to remember; the button says why on hover.
    assert not fresh.workspace_save_button_enabled()
    tooltip = fresh._w._workspace._save_workspace_button.toolTip()
    assert tooltip == "Save the document first"


def test_saved_workspace_reopens_whole_by_name(relaunch, spm_workfile, second_file):
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first._w._open_reference_path(second_file)
    first.show_view("Workspace")
    _save_workspace_as(first, "LG M50 study")
    assert first.toast_text() == "Saved workspace 'LG M50 study'"

    fresh = relaunch()
    assert fresh.workspace_row_names() == ["LG M50 study"]
    fresh.click_workspace_row("LG M50 study")

    state = fresh._w._state
    assert state.active.backing_file == spm_workfile
    assert [ref.set_id for ref in state.references] == [CHEN2020, None]


def test_named_workspaces_are_snapshots_not_live(relaunch, spm_workfile, second_file):
    first = relaunch()
    first.open(spm_workfile)
    first.show_view("Workspace")
    _save_workspace_as(first, "study")
    # A pin after the save changes the session and the automatic record --
    # never the named entry, until the user saves again.
    first._w._open_reference_path(second_file)

    saved = first._w._state.history.named("study")
    assert saved.references == ()
    assert len(first._w._state.history.last_workspace.references) == 1


def test_replacing_a_name_asks_first_and_cancel_keeps_the_old(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(spm_workfile)
    first.show_view("Workspace")
    _save_workspace_as(first, "study")

    first.open(second_file)
    first.show_view("Workspace")
    first._w._confirm_replace_workspace = lambda name: False
    _save_workspace_as(first, "study")
    assert first._w._state.history.named("study").main.path == str(spm_workfile)

    first._w._confirm_replace_workspace = lambda name: True
    _save_workspace_as(first, "study")
    assert first._w._state.history.named("study").main.path == str(second_file)


def test_rename_and_remove_touch_the_entry_not_the_files(relaunch, spm_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first.show_view("Workspace")
    _save_workspace_as(first, "old name")

    first._w._ask_workspace_name = lambda *args: "new name"
    first.click_workspace_row_button("old name", "Rename")
    del first._w._ask_workspace_name
    assert first.workspace_row_names() == ["new name"]

    first._w._confirm_remove_workspace = lambda name: True
    first.click_workspace_row_button("new name", "Remove")
    assert first.workspace_row_names() == []
    assert spm_workfile.exists()  # the entry went, the file never moves


def test_workspace_with_missing_main_says_so_and_wont_open(
    relaunch, spm_workfile, second_file
):
    first = relaunch()
    first.open(second_file)
    first.show_view("Workspace")
    _save_workspace_as(first, "doomed")
    second_file.unlink()

    fresh = relaunch()
    assert fresh.workspace_row_is_missing("doomed")
    # The row is inert -- clicking must not raise, open, or half-restore.
    fresh.click_workspace_row("doomed")
    assert fresh._w._state.active is None
