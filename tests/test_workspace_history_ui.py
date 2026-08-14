"""Workflow tests for the Workspace rail and board: workspaces shelve under
Recent, naming keeps them for good, and the record follows the workspace with
no save step anywhere.

Every test drives a live MainWindow through AppDriver; "relaunching the app"
is building a second window over the same history file. Widget knowledge
lives in ui_driver.py."""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from explore_bpx.ui_qt.workspace_panel import UNTITLED_WORKSPACE

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

        from explore_bpx.state.workspace_history import WorkspaceHistory
        from explore_bpx.ui_qt.main_window import MainWindow

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


def test_opening_a_file_starts_a_workspace_that_survives_a_relaunch(relaunch, spm_workfile):
    first = relaunch()
    first.open(spm_workfile)

    fresh = relaunch()
    assert fresh.recent_workspace_labels() == [spm_workfile.name]
    assert fresh.named_workspace_labels() == []


def test_switching_shelves_rather_than_discards(relaunch, spm_workfile, second_workfile):
    """Nothing is discarded by a click: the workspace being left is already
    under Recent, so it is simply still there."""
    d = relaunch()
    d.open(spm_workfile)
    d.click_new_workspace()
    d.open(second_workfile)

    assert d.recent_workspace_labels() == [second_workfile.name, spm_workfile.name]
    assert d.current_workspace_row_label() == second_workfile.name


def test_opening_a_file_swaps_the_main_of_an_untitled_workspace(relaunch, spm_workfile, second_workfile):
    d = relaunch()
    d.open(spm_workfile)
    d.dock_library_reference(CHEN2020)

    d.open(second_workfile)

    # One workspace, a different main -- not two rows.
    assert d.recent_workspace_labels() == [second_workfile.name]
    assert d.workspace_row_reference_count(second_workfile.name) == 1


def test_new_workspace_clears_the_board_for_a_separate_line_of_work(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    d.dock_library_reference(CHEN2020)

    d.click_new_workspace()

    assert d._w._state.active is None
    assert d._w._state.references == []
    assert d.current_view_index() == 2  # landed on the Workspace page
    # The new workspace is a visible row from the moment it is asked for,
    # and it is the one on the board; the one left behind is kept, not lost.
    assert d.recent_workspace_labels() == [UNTITLED_WORKSPACE, spm_workfile.name]
    assert d.current_workspace_row_label() == UNTITLED_WORKSPACE


def test_the_board_header_invites_a_name_on_an_empty_workspace(relaunch):
    """The header appears with the workspace, not with its first document:
    naming is what stops a workspace decaying, so nobody should have to
    fill one before saying what it is for."""
    d = relaunch()
    assert d.workspace_name_text() == ""  # no workspace at all, no header

    d.click_new_workspace()

    assert d.workspace_name_text() == UNTITLED_WORKSPACE  # the ghost invites
    d.rename_workspace("planning")
    assert d.named_workspace_labels() == ["planning"]
    assert d.workspace_name_text() == "planning"


def test_a_new_workspace_can_be_named_before_it_holds_anything(relaunch, spm_workfile):
    """Creation is instant, so naming does not have to wait for a document:
    the fresh row promotes out of Recent and survives a relaunch empty."""
    d = relaunch()
    d.open(spm_workfile)
    d.click_new_workspace()

    _name_workspace(d, UNTITLED_WORKSPACE, "planning")

    assert d.named_workspace_labels() == ["planning"]
    assert d.recent_workspace_labels() == [spm_workfile.name]
    assert not d.workspace_row_has_main_bar("planning")

    fresh = relaunch()
    assert fresh.named_workspace_labels() == ["planning"]


def test_an_empty_workspace_row_is_neither_missing_nor_barred(relaunch):
    """Nothing recorded is nothing lost: no ▌ bar, no strike, no "Not
    found" chip, and the row still answers a click."""
    d = relaunch()
    d.click_new_workspace()

    assert not d.workspace_row_has_main_bar(UNTITLED_WORKSPACE)
    assert d.workspace_row_reference_count(UNTITLED_WORKSPACE) == 0
    assert not d.workspace_row_is_missing(UNTITLED_WORKSPACE)


def test_a_scaffold_row_shows_its_filename_and_the_card_says_unsaved(relaunch):
    d = relaunch()
    d.click_new_workspace()

    d.click_workspace_new("DFN")

    assert d.workspace_main_name() == "untitled.json"
    assert d.workspace_unsaved_tag_visible()
    d.show_view("Workspace")
    assert not d.start_surface_visible()


def test_a_recent_row_opens_that_file_as_the_main(relaunch, spm_workfile):
    """A recent row is the Open act pre-filled, so it lands exactly where
    the dialog would: that file open as the main of this workspace."""
    d = relaunch()
    d.open(spm_workfile)
    d.click_new_workspace()
    created = d._w._state.workspace_id

    assert d.start_recent_labels() == [spm_workfile.name]
    d.click_start_recent(spm_workfile.name)

    assert d._w._state.active.backing_file == spm_workfile
    assert d._w._state.workspace_id == created  # filled in place, not branched


def test_an_empty_workspace_restores_to_the_start_surface(relaunch, spm_workfile):
    """A restored workspace with no recorded main lands on the start
    surface, and the missing-files banner stays silent -- it is reserved
    for a file that was recorded and would not open."""
    first = relaunch()
    first.open(spm_workfile)
    first.click_new_workspace()
    first.dock_library_reference(CHEN2020)  # gives the empty workspace a record
    empty_id = first._w._state.workspace_id

    fresh = relaunch()
    assert fresh._w._state.workspace_id == empty_id  # restored on launch
    assert fresh._w._state.active is None
    assert fresh.start_surface_visible()
    assert fresh.missing_file_messages() == []


def test_a_workspace_reopens_whole_from_its_rail_row(relaunch, spm_workfile, second_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first._w._open_reference_path(second_workfile)
    # Leave a different workspace on the board, so launch does not restore
    # the one under test and the row is what does the work.
    first.click_new_workspace()
    first.open(second_workfile)

    fresh = relaunch()
    assert fresh._w._state.active.backing_file == second_workfile
    fresh.click_workspace_row(spm_workfile.name)

    state = fresh._w._state
    assert state.active.backing_file == spm_workfile
    assert [ref.set_id for ref in state.references] == [CHEN2020, None]
    assert state.references[1].path == second_workfile


def test_the_current_workspace_wears_the_open_now_pill(relaunch, spm_workfile):
    d = relaunch()
    d.open(spm_workfile)
    assert d.current_workspace_row_label() == spm_workfile.name


def test_both_rail_groups_hide_when_empty(relaunch):
    """An empty group has nothing to teach, so it simply is not there."""
    d = relaunch()
    assert d.visible_rail_groups() == []


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


def test_a_name_in_use_is_refused_inline_and_never_overwrites(relaunch, spm_workfile, second_workfile):
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
    assert d.workspace_name_text() == "Untitled workspace"


# ---------------------------------------------------------------------------
# rule 4: a workspace looks after itself


def test_a_named_workspace_is_live_not_a_snapshot(relaunch, spm_workfile, second_workfile):
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


def test_opening_a_file_beside_a_named_workspace_leaves_it_alone(relaunch, spm_workfile, second_workfile):
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
    assert d.workspace_row_actions(spm_workfile.name) == ["Name", "Remove"]

    d.rename_workspace("study")
    assert d.workspace_row_actions("study") == ["Rename", "Remove"]


# ---------------------------------------------------------------------------
# missing files: open what is there, name what is not


def test_a_missing_main_opens_the_rest_and_offers_locate(relaunch, spm_workfile, second_workfile):
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
    assert fresh.missing_file_messages() == [f"Main not found: {spm_workfile.name}"]
    assert fresh.current_view_index() == 2  # landed where the banner is


def test_locate_repoints_the_workspace_and_reopens_it(relaunch, spm_workfile, second_workfile, tmp_path):
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


def test_a_missing_reference_is_named_and_can_be_forgotten(relaunch, spm_workfile, second_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first._w._open_reference_path(second_workfile)
    first.click_new_workspace()
    second_workfile.unlink()

    fresh = relaunch()
    fresh.click_workspace_row(spm_workfile.name)

    assert fresh._w._state.active.backing_file == spm_workfile  # main opened
    assert fresh.missing_file_messages() == [f"Reference not found: {second_workfile.name}"]

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
# the board's routes out: the page must never be a dead end


def test_the_main_card_routes_to_the_editor_and_to_its_errors(relaunch, spm_workfile, invalid_bpx_path):
    d = relaunch()
    d.open(spm_workfile)
    d.show_view("Workspace")
    # Nothing wrong: no route to a Diagnostics page with nothing on it.
    assert d.issue_route_text() == ""
    d.click_edit_route()
    assert d.current_view_index() == 0

    d.open(invalid_bpx_path)
    d.show_view("Workspace")
    assert d.issue_route_text() == "Diagnostics ▸"
    d.click_issue_route()
    assert d.current_view_index() == 1


def test_each_slot_names_how_much_differs_and_routes_to_the_diff(relaunch, spm_workfile, second_workfile):
    """The count was already computed for every comparison and shown
    nowhere but a tooltip. It is a route now -- and it must survive the
    recompute that lands after the page has refreshed."""
    d = relaunch()
    d.open(spm_workfile)
    d._w._open_reference_path(second_workfile)  # a byte-identical copy
    d.dock_library_reference(CHEN2020)
    d.show_view("Workspace")

    assert d.reference_diff_text(0) == "Identical ▸"
    assert d.reference_diff_text(1).endswith("values differ ▸")

    d.click_reference_diff(1)

    assert d.current_view_index() == 3  # the Source page
    assert d._w._source_reference_index == 1


def test_the_counts_survive_a_relaunch_restore(relaunch, spm_workfile, second_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first._w._open_reference_path(second_workfile)

    fresh = relaunch()
    fresh.show_view("Workspace")

    assert fresh.reference_diff_text(0) == "Identical ▸"


def test_the_board_offers_no_name_when_there_is_no_workspace(relaunch, spm_workfile):
    """An invitation that would silently do nothing is worse than none, so
    the header waits for a workspace to exist -- but only for that. Once one
    does, empty or not, it invites."""
    d = relaunch()
    assert d.workspace_name_text() == ""

    d.open(spm_workfile)
    assert d.workspace_name_text() == UNTITLED_WORKSPACE

    d.click_new_workspace()
    assert d.workspace_name_text() == UNTITLED_WORKSPACE


# ---------------------------------------------------------------------------
# the board's ＋ menu, and the store's own honesty


def test_the_plus_menu_offers_three_routes_including_recent_files(relaunch, spm_workfile, second_workfile):
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
    # Nothing to reopen, and above all nothing that refuses to launch.
    assert fresh._w._state.active is None


# ---------------------------------------------------------------------------
# launch: the workspace is handed back whole


def test_launch_reopens_the_workspace_that_was_on_the_board(relaunch, spm_workfile, second_workfile):
    """The workspace is the unit of work, so a relaunch hands it back whole
    rather than an empty page and the job of finding everything again."""
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    first._w._open_reference_path(second_workfile)

    fresh = relaunch()  # no clicks: this is what launching does

    state = fresh._w._state
    assert state.active.backing_file == spm_workfile
    assert [ref.set_id for ref in state.references] == [CHEN2020, None]
    assert fresh.current_workspace_row_label() == spm_workfile.name
    assert fresh.current_view_index() == 0  # back where the work was


def test_launch_reopens_a_named_workspace_by_its_name(relaunch, spm_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first.rename_workspace("LG M50 study")

    fresh = relaunch()

    assert fresh._w._state.active.backing_file == spm_workfile
    assert fresh.workspace_name_text() == "LG M50 study"
    assert fresh.current_workspace_row_label() == "LG M50 study"


def test_launch_replays_the_recorded_open_mode(relaunch, fixtures_dir):
    """A file opened as-is comes back as-is: the legacy-open prompt exists
    to learn intent, and the record already holds the answer."""
    first = relaunch()
    first.open_as_is(fixtures_dir / "nmc_pouch_cell_BPX.json")
    assert first._w._state.active.read_only is True

    fresh = relaunch()

    assert fresh._w._state.active is not None
    assert fresh._w._state.active.read_only is True


def test_launch_after_new_workspace_starts_on_an_empty_board(relaunch, spm_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first.click_new_workspace()  # deliberately left nothing on the board

    fresh = relaunch()

    assert fresh._w._state.active is None
    assert fresh.current_view_index() == 2
    assert fresh.recent_workspace_labels() == [spm_workfile.name]


def test_launch_with_a_missing_main_never_refuses(relaunch, spm_workfile):
    first = relaunch()
    first.open(spm_workfile)
    first.dock_library_reference(CHEN2020)
    spm_workfile.unlink()

    fresh = relaunch()

    assert fresh.missing_file_messages() == [f"Main not found: {spm_workfile.name}"]
    assert [ref.set_id for ref in fresh._w._state.references] == [CHEN2020]
    assert fresh.current_view_index() == 2  # landed where the banner is


def test_launch_with_an_unreadable_main_says_so_without_a_modal(relaunch, spm_workfile, monkeypatch):
    """A file that will not parse is not a file that is missing, and the
    banner must not call it one. Nor may it meet the user with a modal
    error before the window has settled."""
    import explore_bpx.ui_qt.main_window as main_window_module

    first = relaunch()
    first.open(spm_workfile)
    spm_workfile.write_text("{not valid json", encoding="utf-8")

    monkeypatch.setattr(main_window_module.QMessageBox, "critical", _fail_if_called)
    fresh = relaunch()

    assert fresh.missing_file_messages() == [f"Main could not be read: {spm_workfile.name}"]
    assert fresh._w._state.active is None


def _fail_if_called(*args, **kwargs):
    raise AssertionError("Launching must not show a modal error")
