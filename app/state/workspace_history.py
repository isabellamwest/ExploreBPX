"""Persistent workspace history: recent files, the last workspace, and named
workspaces (frontend-agnostic).

A *workspace* here is the app's unit of work made durable: one main document
(path + how it was opened) and the ordered references pinned beside it (files
by path, bundled library sets by id). The store remembers **pointers only** —
never file content and never validation results, so nothing stale can ever be
presented as a current verdict; every restore re-reads and re-validates.

One JSON file per OS user. The UI shell supplies the location (it knows the
platform config directory); this module owns the schema and every mutation.
Writes are atomic (temp file + rename) and immediate — the history is tiny
and a crash must never half-write it. Two app instances sharing the store are
last-writer-wins, accepted for a single-user desktop tool.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

#: Recent-files cap. Eight rows fit the Workspace rail without scrolling and
#: outlast a typical week of use; older entries fall off the end.
RECENT_FILES_CAP = 8

#: Bumped when the JSON shape changes incompatibly; a reader seeing a newer
#: version than it understands resets rather than misreading it.
SCHEMA_VERSION = 1

#: How the main document was opened -- the D3 legacy intents plus the
#: everyday default. Restoring replays the recorded mode instead of
#: re-asking a question the user already answered.
MAIN_MODES = ("normal", "read_only", "converted_copy")


@dataclass(frozen=True)
class MainRecord:
    """The main document of a remembered workspace: where it lives and how
    it was opened (``MAIN_MODES``)."""

    path: str
    mode: str = "normal"


@dataclass(frozen=True)
class ReferenceRecord:
    """One remembered reference: a file by path (``kind`` "file") or a
    bundled library set by id (``kind`` "library"). Exactly one of ``path``
    and ``set_id`` is set, matching ``ReferenceSnapshot``'s own split."""

    kind: str
    path: str | None = None
    set_id: str | None = None


@dataclass(frozen=True)
class WorkspaceRecord:
    """A remembered workspace. ``name``/``saved_at`` are set only on named
    entries; the automatic last-workspace record has neither."""

    main: MainRecord
    references: tuple[ReferenceRecord, ...] = ()
    name: str | None = None
    saved_at: str | None = None


class WorkspaceHistory:
    """The store: load on construction, persist on every mutation.

    A missing file is the ordinary first launch and loads empty. An
    unreadable one (corrupt JSON, wrong shape, newer schema) also loads
    empty but sets :attr:`load_failed`, so the shell can say so once —
    the app never refuses to launch over its own history.
    """

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self.recent_files: list[str] = []
        self.last_workspace: WorkspaceRecord | None = None
        self.workspaces: list[WorkspaceRecord] = []
        self.load_failed = False
        self._load()

    # ------------------------------------------------------------------
    # mutations (each persists immediately)

    def add_recent(self, path: str) -> None:
        """Push *path* to the front of the recent files, newest first.

        Deduplicated on the resolved path so two spellings of one file are
        one row, but the newest spelling is the one kept: it is what the
        user actually typed or picked, so it is what the row should show.
        """
        resolved = _resolve(path)
        self.recent_files = [
            existing for existing in self.recent_files if _resolve(existing) != resolved
        ]
        self.recent_files.insert(0, path)
        del self.recent_files[RECENT_FILES_CAP:]
        self._persist()

    def remove_recent(self, path: str) -> None:
        """Drop *path* from the recent files (the row's explicit ✕)."""
        resolved = _resolve(path)
        self.recent_files = [
            existing for existing in self.recent_files if _resolve(existing) != resolved
        ]
        self._persist()

    def set_last_workspace(self, record: WorkspaceRecord) -> None:
        """Rewrite the automatic last-workspace snapshot."""
        self.last_workspace = replace(record, name=None, saved_at=None)
        self._persist()

    def named(self, name: str) -> WorkspaceRecord | None:
        """The named workspace called *name*, or None."""
        for workspace in self.workspaces:
            if workspace.name == name:
                return workspace
        return None

    def save_named(self, record: WorkspaceRecord) -> None:
        """Add or replace the named workspace ``record.name``.

        Overwrites silently — asking "replace?" is the shell's dialog, not
        the store's. Entries keep insertion order; an overwrite stays put.
        """
        if not record.name:
            raise ValueError("A named workspace needs a name")
        for index, existing in enumerate(self.workspaces):
            if existing.name == record.name:
                self.workspaces[index] = record
                break
        else:
            self.workspaces.append(record)
        self._persist()

    def rename_named(self, old: str, new: str) -> None:
        """Rename a workspace, displacing any existing entry called *new*
        (the shell confirms that first). Unknown *old* is a quiet no-op."""
        record = self.named(old)
        if record is None:
            return
        self.workspaces = [
            workspace for workspace in self.workspaces if workspace.name != new
        ]
        index = self.workspaces.index(record)
        self.workspaces[index] = replace(record, name=new)
        self._persist()

    def remove_named(self, name: str) -> None:
        """Delete the named workspace *name*; unknown names are a no-op."""
        self.workspaces = [
            workspace for workspace in self.workspaces if workspace.name != name
        ]
        self._persist()

    # ------------------------------------------------------------------
    # persistence

    def _load(self) -> None:
        try:
            text = self.store_path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return
        except OSError:
            self.load_failed = True
            return
        try:
            data = json.loads(text)
            if data.get("version") > SCHEMA_VERSION:
                raise ValueError("newer schema than this app understands")
            self.recent_files = [
                entry["path"] for entry in data.get("recent_files", [])
            ][:RECENT_FILES_CAP]
            last = data.get("last_workspace")
            self.last_workspace = _workspace_from_json(last) if last else None
            self.workspaces = [
                _workspace_from_json(entry) for entry in data.get("workspaces", [])
            ]
            if any(workspace.name is None for workspace in self.workspaces):
                raise ValueError("named workspace without a name")
        except (TypeError, KeyError, ValueError):
            # Unreadable history resets to empty; load_failed lets the shell
            # say so once instead of failing silently (honesty rule 3).
            self.recent_files = []
            self.last_workspace = None
            self.workspaces = []
            self.load_failed = True

    def _persist(self) -> None:
        data = {
            "version": SCHEMA_VERSION,
            "recent_files": [{"path": path} for path in self.recent_files],
            "last_workspace": (
                _workspace_to_json(self.last_workspace)
                if self.last_workspace
                else None
            ),
            "workspaces": [
                _workspace_to_json(workspace) for workspace in self.workspaces
            ],
        }
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_name(self.store_path.name + ".tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp, self.store_path)


def _resolve(path: str) -> str:
    """Identity key for deduplication: the resolved path when the file
    exists, the literal spelling otherwise (a missing file still deduplicates
    against its own spelling, and never collides via a half-resolved form)."""
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


def _workspace_to_json(record: WorkspaceRecord) -> dict:
    data: dict = {
        "main": {"path": record.main.path, "mode": record.main.mode},
        "references": [
            {"kind": ref.kind, "path": ref.path, "set_id": ref.set_id}
            for ref in record.references
        ],
    }
    if record.name is not None:
        data["name"] = record.name
    if record.saved_at is not None:
        data["saved_at"] = record.saved_at
    return data


def _workspace_from_json(data: dict) -> WorkspaceRecord:
    main = data["main"]
    mode = main.get("mode", "normal")
    if mode not in MAIN_MODES:
        raise ValueError(f"unknown main mode: {mode!r}")
    references = []
    for ref in data.get("references", []):
        if ref.get("kind") not in ("file", "library"):
            raise ValueError(f"unknown reference kind: {ref.get('kind')!r}")
        references.append(
            ReferenceRecord(
                kind=ref["kind"], path=ref.get("path"), set_id=ref.get("set_id")
            )
        )
    return WorkspaceRecord(
        main=MainRecord(path=main["path"], mode=mode),
        references=tuple(references),
        name=data.get("name"),
        saved_at=data.get("saved_at"),
    )
