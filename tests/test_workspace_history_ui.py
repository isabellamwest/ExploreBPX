"""Workflow tests for the Workspace rail and board: workspaces shelve under
Recent, naming keeps them for good, and the record follows the workspace with
no save step anywhere.

Every test drives a live MainWindow through AppDriver; "relaunching the app"
is building a second window over the same history file. Widget knowledge
lives in ui_driver.py."""

from __future__ import annotations

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


def _name_workspace(driver, label, name):
    """Answer the name dialog with *name* through its monkeypatch seam (the
    ``_ask_open_intent`` convention), then click the row's Name action."""
    driver._w._ask_workspace_name = lambda *args: name
    try:
        driver.click_workspace_row_button(label, "Name")
    finally:
        del driver._w._ask_workspace_name


# ---------------------------------------------------------------------------
# opening starts a workspace; switching shelves it


def test_opening_a_file_starts_a_workspace_that_survives_a_relaunch(
    relaunch, spm_workfile
):
    first = relaunch()
    first.open(spm_workfile)

    fresh = relaunch()
    assert fresh.recent_workspace_labels() == [spm_workfile.name]
    assert fresh.named_workspace_labels() == []


def test_switching_shelves_rather_than_discards(
    relaunch, spm_workfile, second_workfile
):
    """Nothing is discarded by a click: the workspace being left is already
    under Recent, so it is simply still there."""
    d = relaunch()
    d.open(spm_workfile)
    d.click_new_workspace()
    d.open(second_workfile)

    assert d.recent_workspace_labels() == [second_workfile.name, spm_workfile.name]
    assert d.current_workspace_row_label() == second_workfile.name


def test_opening_a_file_swaps_the_main_of_an_untitled_workspace(
    relaunch, spm_workfile, second_workfile
):
    d = relaunch()
    d.open(spm_workfile)
    d.dock_library_reference(CHEN2020)

    d.open(second_workfile)

    # One workspace, a different main -- not two rows.
    assert d.recent_workspace_labels() == [second_workfile.name]
    assert d.workspace_row_reference_count(second_workfile.name) == 1


def test_new_workspace_clears_the_board_for_a_separate_line_of_work(
    relaunch, spm_workfile
):
    d = relaunch()
    d.open(spm_workfile)
    d.dock_library_reference(CHEN2020)

    d.click_new_workspace()

    assert d._w._state.active is None
    assert d._w._state.references == []
    assert d.current_view_index() == 2  # landed on the Workspace page
    assert d.recent_workspace_labels() == [spm_workfile.name]  # kept, not lost
    assert d.current_workspace_row_label() is None


def test_a_workspace_reopens_whole_from_its_rail_row(
    relaunch, spm_workfile, second_workfile
):
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first._w._open_reference_path(second_workfile)

    fresh = relaunch()
    fresh.click_workspace_row(spm_workfile.name)

    state = fresh._w._state
    assert state.active.backing_file == spm_workfile
    assert [ref.set_id for ref in state.references] == [CHEN2020, None]
    assert state.references[1].path == second_workfile


def test_the_current_workspace_wears_the_open_now_pill(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    assert d.current_workspace_row_label() == spm_workfile.name


def test_both_rail_groups_teach_themselves_when_empty(relaunch):
    """Always visible, empty or not -- a group that hides itself teaches
    nothing on a first launch."""
    d = relaunch()
    assert d.rail_empty_state_texts() == [
        "Name a workspace to keep it here for good.",
        "Open a file and the workspace it starts appears here.",
    ]


# ---------------------------------------------------------------------------
# naming is a promotion, and it is what stops a workspace decaying


def test_naming_moves_a_workspace_out_of_recent_for_good(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    _name_workspace(d, spm_workfile.name, "LG M50 study")

    assert d.named_workspace_labels() == ["LG M50 study"]
    assert d.recent_workspace_labels() == []
    assert d.workspace_name_text() == "LG M50 study"

    fresh = relaunch()
    assert fresh.named_workspace_labels() == ["LG M50 study"]


def test_the_board_header_renames_in_place(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    d.rename_workspace("first name")
    assert d.named_workspace_labels() == ["first name"]

    d.rename_workspace("second name")
    assert d.named_workspace_labels() == ["second name"]
    assert d.workspace_name_text() == "second name"


def test_a_name_in_use_is_refused_inline_and_never_overwrites(
    relaunch, spm_workfile, second_workfile
):
    d = relaunch()
    d.open(spm_workfile)
    d.rename_workspace("study")

    d.click_new_workspace()
    d.open(second_workfile)
    d.rename_workspace("study")

    assert d.workspace_name_error() == "That name is in use"
    # Neither workspace moved: the refusal changed nothing at all.
    assert d.named_workspace_labels() == ["study"]
    assert d._w._state.history.named("study").main.path == str(spm_workfile)


def test_an_untitled_workspace_invites_a_name(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    assert d.workspace_name_text() == "Untitled workspace — click to name it"


# ---------------------------------------------------------------------------
# rule 4: a workspace looks after itself


def test_a_named_workspace_is_live_not_a_snapshot(
    relaunch, spm_workfile, second_workfile
):
    """The deliberate reversal of the old snapshot semantics. A pin after
    naming *is* part of the workspace -- there is no save step to wait for
    and nothing that can go stale."""
    d = relaunch()
    d.open(spm_workfile)
    d.rename_workspace("study")

    d._w._open_reference_path(second_workfile)

    live = d._w._state.history.named("study")
    assert [ref.path for ref in live.references] == [str(second_workfile)]
    assert d.workspace_row_reference_count("study") == 1

    # And it is still live after a relaunch: the store, not a snapshot.
    fresh = relaunch()
    assert fresh.workspace_row_reference_count("study") == 1


def test_opening_a_file_beside_a_named_workspace_leaves_it_alone(
    relaunch, spm_workfile, second_workfile
):
    """Naming is the act that says "stop rewriting this", so an ordinary
    open starts a fresh untitled workspace rather than swapping the named
    one's main."""
    d = relaunch()
    d.open(spm_workfile)
    d.rename_workspace("study")

    d.open(second_workfile)

    assert d._w._state.history.named("study").main.path == str(spm_workfile)
    assert d.named_workspace_labels() == ["study"]
    assert d.recent_workspace_labels() == [second_workfile.name]
    assert d.current_workspace_row_label() == second_workfile.name


def test_duplicate_is_the_fork_that_live_identity_costs_us(
    relaunch, spm_workfile, second_workfile
):
    d = relaunch()
    d.open(spm_workfile)
    d.rename_workspace("study")

    d.click_workspace_row_button("study", "Duplicate")

    assert d.named_workspace_labels() == ["study", "study copy"]
    assert d.toast_text() == "Duplicated as 'study copy'"
    # The fork is a real fork: changing the original leaves the copy alone.
    d._w._open_reference_path(second_workfile)
    assert d.workspace_row_reference_count("study") == 1
    assert d.workspace_row_reference_count("study copy") == 0


def test_rename_and_remove_touch_the_entry_not_the_files(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    _name_workspace(d, spm_workfile.name, "old name")

    d._w._ask_workspace_name = lambda *args: "new name"
    d.click_workspace_row_button("old name", "Rename")
    del d._w._ask_workspace_name
    assert d.named_workspace_labels() == ["new name"]

    d._w._confirm_remove_workspace = lambda label: True
    d.click_workspace_row_button("new name", "Remove")
    assert d.named_workspace_labels() == []
    assert spm_workfile.exists()  # the entry went, the file never moves


def test_every_row_offers_the_same_actions_on_hover(relaunch, spm_workfile):
    """Hover-revealed row actions, never a ⋯ menu -- the app's own idiom."""
    d = relaunch()
    d.open(spm_workfile)
    assert d.workspace_row_actions(spm_workfile.name) == [
        "Name",
        "Duplicate",
        "Remove",
    ]

    d.rename_workspace("study")
    assert d.workspace_row_actions("study") == ["Rename", "Duplicate", "Remove"]


# ---------------------------------------------------------------------------
# missing files: open what is there, name what is not


def test_a_missing_main_opens_the_rest_and_offers_locate(
    relaunch, spm_workfile, second_workfile
):
    """It used to refuse the whole workspace over one moved file, throwing
    away the arrangement the record exists to protect."""
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first.click_new_workspace()
    spm_workfile.unlink()

    fresh = relaunch()
    assert fresh.workspace_row_is_missing(spm_workfile.name)
    fresh.click_workspace_row(spm_workfile.name)

    # The references came back even though the main did not.
    assert [ref.set_id for ref in fresh._w._state.references] == [CHEN2020]
    assert fresh._w._state.active is None
    assert fresh.missing_file_messages() == [
        f"Main document not found: {spm_workfile.name}"
    ]
    assert fresh.current_view_index() == 2  # landed where the banner is


def test_locate_repoints_the_workspace_and_reopens_it(
    relaunch, spm_workfile, second_workfile, tmp_path
):
    first = relaunch()
    first.open(spm_workfile)
    first.click_new_workspace()

    moved = tmp_path / "moved" / spm_workfile.name
    moved.parent.mkdir()
    spm_workfile.rename(moved)

    fresh = relaunch()
    fresh.click_workspace_row(spm_workfile.name)
    assert fresh.missing_file_messages()

    fresh._w._ask_locate_path = lambda label: moved
    fresh.click_missing_file_button(spm_workfile.name, "Locate…")

    assert fresh._w._state.active.backing_file == moved
    assert fresh.missing_file_messages() == []


def test_a_missing_reference_is_named_and_can_be_forgotten(
    relaunch, spm_workfile, second_workfile
):
    first = relaunch()
    first.open(spm_workfile)
    first._w._open_reference_path(second_workfile)
    first.click_new_workspace()
    second_workfile.unlink()

    fresh = relaunch()
    fresh.click_workspace_row(spm_workfile.name)

    assert fresh._w._state.active.backing_file == spm_workfile  # main opened
    assert fresh.missing_file_messages() == [
        f"Reference not found: {second_workfile.name}"
    ]

    fresh.click_missing_file_button(second_workfile.name, "Remove")

    assert fresh.missing_file_messages() == []
    assert fresh._w._state.history.current().references == ()
    assert fresh.workspace_row_reference_count(spm_workfile.name) == 0


def test_dirty_guard_runs_before_a_restore(relaunch, spm_workfile, second_workfile):
    d = relaunch()
    d.open(second_workfile)
    d.click_new_workspace()
    d.open(spm_workfile)
    d.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    d.edit_field("9.5").commit()
    assert d._w._state.active.dirty

    # Cancel at the unsaved-changes prompt stops the whole restore.
    d._w._confirm_discard_if_dirty = lambda: False
    d.show_view("Workspace")
    d.click_workspace_row(second_workfile.name)

    assert d._w._state.active.backing_file == spm_workfile  # unchanged


# ---------------------------------------------------------------------------
# the board's ＋ menu, and the store's own honesty


def test_the_plus_menu_offers_three_routes_including_recent_files(
    relaunch, spm_workfile, second_workfile
):
    """Recent *files* lost their rail rows and feed this menu instead."""
    d = relaunch()
    d.open(second_workfile)
    d.click_new_workspace()
    d.open(spm_workfile)

    assert d.add_menu_routes() == [
        "From the reference library…",
        "Open a BPX file…",
        "Recent files",
    ]
    assert d.add_menu_recent_files() == [spm_workfile.name, second_workfile.name]

    d.pin_recent_file(second_workfile.name)
    assert [ref.path for ref in d._w._state.references] == [second_workfile]


def test_corrupt_history_resets_and_announces_itself(relaunch, history_path, qtbot):
    history_path.write_text("{broken")
    fresh = relaunch()
    qtbot.wait(10)  # the notice is deferred one tick
    assert fresh.toast_text() == "Workspace history was unreadable and has been reset"
    assert fresh.workspace_row_labels() == []
