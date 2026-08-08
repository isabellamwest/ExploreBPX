"""Tests for state.workspace_history — the pure-Python store behind recent
files, the last workspace, and named workspaces. No Qt anywhere here."""

from __future__ import annotations

import json

from state.workspace_history import (
    RECENT_FILES_CAP,
    MainRecord,
    ReferenceRecord,
    WorkspaceHistory,
    WorkspaceRecord,
)


def _store(tmp_path):
    return WorkspaceHistory(tmp_path / "history.json")


def _workspace(name=None, path="/cells/lgm50.json", mode="normal"):
    return WorkspaceRecord(
        main=MainRecord(path=path, mode=mode),
        references=(
            ReferenceRecord(kind="library", set_id="chen2020"),
            ReferenceRecord(kind="file", path="/cells/nmc.json"),
        ),
        name=name,
    )


def test_first_launch_loads_empty_without_complaint(tmp_path):
    history = _store(tmp_path)
    assert history.recent_files == []
    assert history.last_workspace is None
    assert history.workspaces == []
    assert history.load_failed is False


def test_everything_round_trips_through_disk(tmp_path):
    history = _store(tmp_path)
    history.add_recent("/cells/lgm50.json")
    history.set_last_workspace(_workspace())
    history.save_named(_workspace(name="LG M50 study"))

    reloaded = _store(tmp_path)
    assert reloaded.recent_files == ["/cells/lgm50.json"]
    assert reloaded.last_workspace == _workspace()
    assert reloaded.workspaces == [_workspace(name="LG M50 study")]
    assert reloaded.load_failed is False


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


def test_last_workspace_never_keeps_a_name(tmp_path):
    history = _store(tmp_path)
    history.set_last_workspace(_workspace(name="smuggled"))
    assert history.last_workspace.name is None
    assert history.last_workspace.saved_at is None


def test_save_named_overwrites_in_place_and_keeps_order(tmp_path):
    history = _store(tmp_path)
    history.save_named(_workspace(name="first"))
    history.save_named(_workspace(name="second"))
    history.save_named(_workspace(name="first", path="/cells/other.json"))

    assert [workspace.name for workspace in history.workspaces] == ["first", "second"]
    assert history.workspaces[0].main.path == "/cells/other.json"


def test_rename_moves_the_entry_and_displaces_the_target_name(tmp_path):
    history = _store(tmp_path)
    history.save_named(_workspace(name="old"))
    history.save_named(_workspace(name="taken", path="/cells/other.json"))
    history.rename_named("old", "taken")

    assert [workspace.name for workspace in history.workspaces] == ["taken"]
    assert history.named("taken").main.path == "/cells/lgm50.json"
    history.rename_named("ghost", "anything")  # unknown old: quiet no-op
    assert [workspace.name for workspace in history.workspaces] == ["taken"]


def test_remove_named_deletes_only_that_entry(tmp_path):
    history = _store(tmp_path)
    history.save_named(_workspace(name="keep"))
    history.save_named(_workspace(name="drop"))
    history.remove_named("drop")
    history.remove_named("ghost")  # no-op
    assert [workspace.name for workspace in history.workspaces] == ["keep"]


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
                "version": 1,
                "recent_files": [],
                "last_workspace": {
                    "main": {"path": "/x.json", "mode": "telepathic"},
                    "references": [],
                },
                "workspaces": [],
            }
        )
    )
    assert WorkspaceHistory(store_path).load_failed is True


def test_store_never_contains_content_or_verdicts(tmp_path):
    """The written JSON holds paths, ids and modes — nothing else. Guards
    the honesty rule at the file level, not just in prose."""
    history = _store(tmp_path)
    history.set_last_workspace(_workspace())
    history.save_named(_workspace(name="study"))
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
        "version", "recent_files", "last_workspace", "workspaces",
        "main", "path", "mode", "references", "kind", "set_id", "name", "saved_at",
    }
    assert set(keys_of(written)) <= allowed
