"""Tests for state.workspace_history — the pure-Python store behind recent
files and the workspaces themselves. No Qt anywhere here."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from explore_bpx.state.workspace_history import (
    MAX_RECENT_WORKSPACES,
    RECENT_FILES_CAP,
    SCHEMA_VERSION,
    MainRecord,
    NameInUseError,
    ReferenceRecord,
    WorkspaceHistory,
    WorkspaceRecord,
    new_id,
)


def _store(tmp_path):
    return WorkspaceHistory(tmp_path / "history.json")


def _workspace(path="/cells/lgm50.json", mode="normal", references=None):
    return WorkspaceRecord(
        main=MainRecord(path=path, mode=mode),
        references=(
            (
                ReferenceRecord(kind="library", set_id="chen2020"),
                ReferenceRecord(kind="file", path="/cells/nmc.json"),
            )
            if references is None
            else references
        ),
    )


def _started(history, **kwargs):
    """Start a workspace and hand back its stored record (with its id)."""
    return history.start_workspace(_workspace(**kwargs))


# ---------------------------------------------------------------------------
# loading and round-tripping


def test_first_launch_loads_empty_without_complaint(tmp_path):
    history = _store(tmp_path)
    assert history.recent_files == []
    assert history.recent_workspaces == []
    assert history.workspaces == []
    assert history.current_id is None
    assert history.load_failed is False


def test_everything_round_trips_through_disk(tmp_path):
    history = _store(tmp_path)
    history.add_recent("/cells/lgm50.json")
    started = _started(history)
    kept = history.keep(started.id, "LG M50 study")
    _started(history, path="/cells/other.json")

    reloaded = _store(tmp_path)
    assert reloaded.recent_files == ["/cells/lgm50.json"]
    assert reloaded.workspaces == [kept]
    assert [w.main.path for w in reloaded.recent_workspaces] == ["/cells/other.json"]
    assert reloaded.current_id == reloaded.recent_workspaces[0].id
    assert reloaded.load_failed is False


# ---------------------------------------------------------------------------
# recent files (they feed the board's ＋ menu, not a rail group)


def test_recents_are_newest_first_deduplicated_and_capped(tmp_path):
    history = _store(tmp_path)
    for index in range(RECENT_FILES_CAP + 3):
        history.add_recent(f"/cells/file{index}.json")
    history.add_recent("/cells/file5.json")  # re-open: moves to front, no dup

    assert len(history.recent_files) == RECENT_FILES_CAP
    assert history.recent_files[0] == "/cells/file5.json"
    assert history.recent_files.count("/cells/file5.json") == 1
    assert "/cells/file0.json" not in history.recent_files  # fell off the end


def test_dedup_is_by_resolved_path_but_newest_spelling_wins(tmp_path):
    real = tmp_path / "cell.json"
    real.write_text("{}")
    history = _store(tmp_path)
    history.add_recent(str(real))
    history.add_recent(str(tmp_path / "sub" / ".." / "cell.json"))

    assert len(history.recent_files) == 1
    assert history.recent_files[0] == str(tmp_path / "sub" / ".." / "cell.json")


def test_remove_recent_drops_only_the_pointed_row(tmp_path):
    history = _store(tmp_path)
    history.add_recent("/cells/a.json")
    history.add_recent("/cells/b.json")
    history.remove_recent("/cells/a.json")
    assert history.recent_files == ["/cells/b.json"]


# ---------------------------------------------------------------------------
# starting, shelving, decaying


def test_starting_a_workspace_gives_it_an_identity_and_the_board(tmp_path):
    history = _store(tmp_path)
    started = _started(history)

    assert started.id
    assert started.name is None
    assert history.current_id == started.id
    assert history.current() == started
    assert history.recent_workspaces == [started]


def test_identity_is_the_id_not_the_main_path(tmp_path):
    """Two workspaces may point at one file, and a main swap does not make
    a workspace into a different one."""
    history = _store(tmp_path)
    first = _started(history, references=())
    second = _started(history, references=(ReferenceRecord(kind="library", set_id="x"),))
    assert first.id != second.id

    history.update_current(MainRecord(path="/cells/moved.json"), ())
    assert history.current_id == second.id  # same workspace, different main


def test_switching_away_shelves_rather_than_discards(tmp_path):
    history = _store(tmp_path)
    first = _started(history, path="/cells/a.json")
    second = _started(history, path="/cells/b.json")

    # Nothing was thrown away by starting the second, and switching back
    # brings the first to the front.
    assert {w.id for w in history.recent_workspaces} == {first.id, second.id}
    history.set_current(first.id)
    assert history.recent_workspaces[0].id == first.id
    assert history.current_id == first.id


def test_recent_workspaces_decay_oldest_first(tmp_path):
    history = _store(tmp_path)
    started = [_started(history, path=f"/cells/file{index}.json") for index in range(MAX_RECENT_WORKSPACES + 2)]

    assert len(history.recent_workspaces) == MAX_RECENT_WORKSPACES
    assert history.by_id(started[0].id) is None  # fell off the end
    assert history.by_id(started[-1].id) is not None


def test_the_workspace_on_the_board_never_decays(tmp_path):
    """The cap drops the oldest *spare* entry: the current one is in use."""
    history = _store(tmp_path)
    current = _started(history, path="/cells/current.json")
    # Pile up distinct spare entries above it without disturbing current_id.
    history.recent_workspaces[:0] = [
        replace(current, id=new_id(), main=MainRecord(path=f"/cells/other{i}.json"))
        for i in range(MAX_RECENT_WORKSPACES + 2)
    ]
    history.update_current(current.main, current.references)  # triggers the cap

    assert len(history.recent_workspaces) == MAX_RECENT_WORKSPACES
    assert history.by_id(current.id) is not None
    assert history.current_id == current.id


def test_content_duplicate_recents_merge_into_the_newest(tmp_path):
    history = _store(tmp_path)
    first = _started(history)
    _started(history, path="/cells/other.json")
    second = _started(history)  # same main + refs as `first`

    assert history.by_id(first.id) is None  # older merged away
    assert history.by_id(second.id) is not None
    assert len(history.recent_workspaces) == 2


def test_different_references_are_a_different_arrangement(tmp_path):
    history = _store(tmp_path)
    plain = _started(history, references=())
    with_ref = _started(history)  # same main, two references

    assert history.by_id(plain.id) is not None
    assert history.by_id(with_ref.id) is not None


def test_named_workspaces_never_merge_or_decay(tmp_path):
    history = _store(tmp_path)
    kept = history.keep(_started(history).id, "study")
    for index in range(MAX_RECENT_WORKSPACES + 2):
        _started(history, path=f"/cells/file{index}.json")
    _started(history)  # identical files to the named one

    assert history.named("study") == kept
    assert len(history.recent_workspaces) == MAX_RECENT_WORKSPACES


# ---------------------------------------------------------------------------
# live identity (rule 4): the record follows the workspace, with no save step


def test_update_current_rewrites_an_untitled_workspace_in_place(tmp_path):
    history = _store(tmp_path)
    started = _started(history, references=())

    history.update_current(
        MainRecord(path="/cells/swapped.json"),
        (ReferenceRecord(kind="library", set_id="chen2020"),),
    )

    current = history.current()
    assert current.id == started.id  # identity survived the main swap
    assert current.main.path == "/cells/swapped.json"
    assert current.references == (ReferenceRecord(kind="library", set_id="chen2020"),)


def test_a_named_workspace_is_live_not_a_snapshot(tmp_path):
    """The deliberate reversal of the old snapshot semantics: a named
    workspace looks after itself, so there is nothing to save and nothing
    to go stale."""
    history = _store(tmp_path)
    kept = history.keep(_started(history, references=()).id, "study")

    history.update_current(kept.main, (ReferenceRecord(kind="file", path="/cells/nmc.json"),))

    live = history.named("study")
    assert live.id == kept.id
    assert live.references == (ReferenceRecord(kind="file", path="/cells/nmc.json"),)
    assert history.recent_workspaces == []  # naming took it out of Recent


def test_updates_keep_their_place_in_both_lists(tmp_path):
    history = _store(tmp_path)
    first = history.keep(_started(history, path="/cells/a.json").id, "first")
    second = history.keep(_started(history, path="/cells/b.json").id, "second")
    history.set_current(first.id)
    history.update_current(MainRecord(path="/cells/c.json"), ())

    assert [w.name for w in history.workspaces] == ["first", "second"]
    assert history.named("first").main.path == "/cells/c.json"
    assert second.id == history.workspaces[1].id


def test_update_without_a_current_workspace_is_a_no_op(tmp_path):
    history = _store(tmp_path)
    history.update_current(MainRecord(path="/cells/a.json"), ())
    assert history.recent_workspaces == []
    assert history.workspaces == []


# ---------------------------------------------------------------------------
# naming: a promotion, and never an overwrite


def test_naming_promotes_out_of_recent_for_good(tmp_path):
    history = _store(tmp_path)
    started = _started(history)
    kept = history.keep(started.id, "LG M50 study")

    assert kept.id == started.id  # same workspace, now named
    assert kept.name == "LG M50 study"
    assert kept.saved_at is not None
    assert history.recent_workspaces == []
    assert history.workspaces == [kept]
    assert history.current_id == kept.id  # it is still the one on the board


def test_a_name_in_use_is_refused_never_overwritten(tmp_path):
    history = _store(tmp_path)
    first = history.keep(_started(history, path="/cells/a.json").id, "study")
    second = _started(history, path="/cells/b.json")

    assert history.name_in_use("study") is True
    with pytest.raises(NameInUseError):
        history.keep(second.id, "study")

    # Neither entry moved: the refusal changed nothing at all.
    assert history.named("study").main.path == first.main.path
    assert history.by_id(second.id) in history.recent_workspaces


def test_renaming_to_its_own_name_is_allowed(tmp_path):
    history = _store(tmp_path)
    kept = history.keep(_started(history).id, "study")
    assert history.name_in_use("study", excluding=kept.id) is False
    assert history.rename(kept.id, "study").name == "study"
    assert history.rename(kept.id, "renamed").name == "renamed"
    assert [w.name for w in history.workspaces] == ["renamed"]


def test_an_empty_name_is_not_a_name(tmp_path):
    history = _store(tmp_path)
    started = _started(history)
    with pytest.raises(ValueError, match="needs a name"):
        history.keep(started.id, "   ")


def test_remove_forgets_the_entry_and_clears_the_board(tmp_path):
    history = _store(tmp_path)
    keeper = history.keep(_started(history, path="/cells/a.json").id, "keep")
    doomed = _started(history, path="/cells/b.json")

    history.remove(doomed.id)
    history.remove("ghost-id")  # unknown: quiet no-op

    assert history.current_id is None
    assert history.recent_workspaces == []
    assert history.workspaces == [keeper]


# ---------------------------------------------------------------------------
# relocate: the only path edit there is


def test_relocate_main_repoints_the_path_and_keeps_the_mode(tmp_path):
    history = _store(tmp_path)
    started = _started(history, mode="read_only")
    history.relocate_main(started.id, "/moved/lgm50.json")

    current = history.current()
    assert current.main.path == "/moved/lgm50.json"
    assert current.main.mode == "read_only"
    assert current.id == started.id


def test_relocate_reference_repoints_only_that_file(tmp_path):
    history = _store(tmp_path)
    started = _started(history)
    history.relocate_reference(started.id, 1, "/moved/nmc.json")

    references = history.current().references
    assert references[0] == ReferenceRecord(kind="library", set_id="chen2020")
    assert references[1] == ReferenceRecord(kind="file", path="/moved/nmc.json")


def test_relocate_ignores_library_sets_and_bad_indices(tmp_path):
    history = _store(tmp_path)
    started = _started(history)
    before = history.current()

    history.relocate_reference(started.id, 0, "/nowhere.json")  # a library set
    history.relocate_reference(started.id, 9, "/nowhere.json")  # past the end
    history.relocate_main("ghost-id", "/nowhere.json")

    assert history.current() == before


def test_removing_a_reference_edits_the_record(tmp_path):
    history = _store(tmp_path)
    started = _started(history)
    history.remove_reference(started.id, 0)
    history.remove_reference(started.id, 9)  # past the end: no-op

    assert history.current().references == (ReferenceRecord(kind="file", path="/cells/nmc.json"),)


# ---------------------------------------------------------------------------
# migration and corruption


def test_version_1_stores_migrate_without_losing_anything(tmp_path):
    store_path = tmp_path / "history.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 1,
                "recent_files": [{"path": "/cells/lgm50.json"}],
                "last_workspace": {
                    "main": {"path": "/cells/lgm50.json", "mode": "read_only"},
                    "references": [{"kind": "library", "set_id": "chen2020"}],
                },
                "workspaces": [
                    {
                        "name": "old study",
                        "saved_at": "2026-01-01T00:00:00",
                        "main": {"path": "/cells/nmc.json", "mode": "normal"},
                        "references": [],
                    }
                ],
            }
        )
    )
    history = WorkspaceHistory(store_path)

    assert history.load_failed is False
    assert history.recent_files == ["/cells/lgm50.json"]
    # The automatic last-workspace slot became the first Recent entry.
    assert len(history.recent_workspaces) == 1
    migrated = history.recent_workspaces[0]
    assert migrated.main == MainRecord(path="/cells/lgm50.json", mode="read_only")
    assert migrated.references == (ReferenceRecord(kind="library", set_id="chen2020"),)
    assert migrated.id  # every record gains an identity
    # Named workspaces carry over untouched but for their new id.
    assert [w.name for w in history.workspaces] == ["old study"]
    assert history.workspaces[0].id
    # The old automatic slot meant "what you had open", which is the
    # question current_id now answers -- so the first launch after an
    # upgrade hands it back rather than starting empty.
    assert history.current_id == migrated.id

    # The migrated store rewrites itself at the current version on the next
    # mutation.
    history.add_recent("/cells/new.json")
    assert json.loads(store_path.read_text())["version"] == SCHEMA_VERSION


def test_a_current_id_pointing_nowhere_is_dropped_not_fatal(tmp_path):
    store_path = tmp_path / "history.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 2,
                "recent_files": [],
                "recent_workspaces": [],
                "workspaces": [],
                "current_id": "a workspace that is gone",
            }
        )
    )
    history = WorkspaceHistory(store_path)
    assert history.load_failed is False
    assert history.current_id is None


def test_corrupt_file_resets_to_empty_and_says_so(tmp_path):
    store_path = tmp_path / "history.json"
    store_path.write_text("{not json")
    history = WorkspaceHistory(store_path)
    assert history.load_failed is True
    assert history.recent_files == []
    # The store is usable again immediately, and the flag is one-shot.
    history.add_recent("/cells/a.json")
    assert WorkspaceHistory(store_path).load_failed is False


def test_newer_schema_version_resets_rather_than_misreading(tmp_path):
    store_path = tmp_path / "history.json"
    store_path.write_text(json.dumps({"version": 99, "recent_files": []}))
    history = WorkspaceHistory(store_path)
    assert history.load_failed is True
    assert history.recent_files == []


def test_unknown_mode_or_reference_kind_counts_as_corrupt(tmp_path):
    store_path = tmp_path / "history.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 2,
                "recent_files": [],
                "recent_workspaces": [
                    {
                        "id": "abc",
                        "main": {"path": "/x.json", "mode": "telepathic"},
                        "references": [],
                    }
                ],
                "workspaces": [],
            }
        )
    )
    assert WorkspaceHistory(store_path).load_failed is True


# ---------------------------------------------------------------------------
# workspaces that hold no main


def test_a_mainless_workspace_round_trips(tmp_path):
    history = _store(tmp_path)
    started = history.start_workspace(WorkspaceRecord(main=None))
    kept = history.keep(started.id, "planning")

    reloaded = _store(tmp_path)
    assert reloaded.workspaces == [kept]
    assert reloaded.workspaces[0].main is None
    assert reloaded.load_failed is False


def test_version_2_stores_load_unchanged(tmp_path):
    """A version-2 record simply always has a main, so it reads through the
    version-3 path untouched."""
    store_path = tmp_path / "history.json"
    store_path.write_text(
        json.dumps(
            {
                "version": 2,
                "recent_files": [{"path": "/cells/lgm50.json"}],
                "recent_workspaces": [
                    {
                        "id": "abc",
                        "main": {"path": "/cells/lgm50.json", "mode": "read_only"},
                        "references": [{"kind": "library", "set_id": "chen2020"}],
                    }
                ],
                "workspaces": [],
                "current_id": "abc",
            }
        )
    )
    history = WorkspaceHistory(store_path)

    assert history.load_failed is False
    assert history.current().main == MainRecord("/cells/lgm50.json", "read_only")
    assert history.current().references == (ReferenceRecord(kind="library", set_id="chen2020"),)


def test_an_empty_untitled_workspace_is_never_written(tmp_path):
    """No name, no main, no references: nothing to come back to, so the
    next launch starts clean rather than restoring a blank row."""
    history = _store(tmp_path)
    history.start_workspace(WorkspaceRecord(main=None))

    written = json.loads((tmp_path / "history.json").read_text())
    assert written["recent_workspaces"] == []
    # The workspace is real in memory even so -- it is the board.
    assert history.current() is not None
    assert _store(tmp_path).current_id is None


def test_a_named_or_referenced_mainless_workspace_is_written(tmp_path):
    history = _store(tmp_path)
    named = history.keep(history.start_workspace(WorkspaceRecord(main=None)).id, "planning")
    referenced = history.start_workspace(
        WorkspaceRecord(main=None, references=(ReferenceRecord(kind="library", set_id="chen2020"),))
    )

    reloaded = _store(tmp_path)
    assert [w.id for w in reloaded.workspaces] == [named.id]
    assert [w.id for w in reloaded.recent_workspaces] == [referenced.id]
    assert reloaded.current_id == referenced.id


def test_repeated_empty_workspaces_collapse_to_one(tmp_path):
    """Two empty boards are the same arrangement, so asking again heals to
    the one row rather than piling them up."""
    history = _store(tmp_path)
    for _ in range(4):
        history.start_workspace(WorkspaceRecord(main=None))

    assert len(history.recent_workspaces) == 1
    assert history.current_id == history.recent_workspaces[0].id


def test_locating_a_workspace_with_no_main_is_a_no_op(tmp_path):
    history = _store(tmp_path)
    started = history.start_workspace(WorkspaceRecord(main=None))
    history.relocate_main(started.id, "/cells/found.json")
    assert history.current().main is None


def test_store_never_contains_content_or_verdicts(tmp_path):
    """The written JSON holds paths, ids and modes — nothing else. Guards
    the honesty rule at the file level, not just in prose."""
    history = _store(tmp_path)
    _started(history, path="/cells/other.json")
    history.keep(_started(history).id, "study")
    written = json.loads((tmp_path / "history.json").read_text())

    def keys_of(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from keys_of(value)
        elif isinstance(node, list):
            for item in node:
                yield from keys_of(item)

    allowed = {
        "version",
        "recent_files",
        "recent_workspaces",
        "workspaces",
        "current_id",
        "id",
        "main",
        "path",
        "mode",
        "references",
        "kind",
        "set_id",
        "name",
        "saved_at",
    }
    assert set(keys_of(written)) <= allowed
