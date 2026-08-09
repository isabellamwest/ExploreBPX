"""Persistent workspace history: recent files and the workspaces themselves
(frontend-agnostic).

A *workspace* is the files worked with together: one main document (path +
how it was opened) and the references pinned beside it (files by path,
bundled library sets by id). A workspace is a **live identity, not a
snapshot** -- swapping the main or adding a reference rewrites the stored
record in place, so there is nothing to save and nothing to go stale. It is
identified by an internal ``id`` rather than by its main's path, so identity
survives a main swap and two workspaces may point at the same file.

Every workspace lives in exactly one of two lists:

* :attr:`WorkspaceHistory.recent_workspaces` -- untitled, newest first,
  capped at ``MAX_RECENT_WORKSPACES``. The oldest falls off the end, and a
  workspace whose contents duplicate another's merges into the newer of the
  two. Nothing is discarded by a click: switching away shelves here.
* :attr:`WorkspaceHistory.workspaces` -- named, in the order they were
  named, never decaying. Naming is a promotion out of Recent, not a rescue.

The store remembers **pointers only** -- never file content and never
validation results, so nothing stale can ever be presented as a current
verdict; every restore re-reads and re-validates.

One JSON file per OS user. The UI shell supplies the location (it knows the
platform config directory); this module owns the schema and every mutation.
Writes are atomic (temp file + rename) and immediate -- the history is tiny
and a crash must never half-write it. Two app instances sharing the store are
last-writer-wins, accepted for a single-user desktop tool.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

#: Recent-files cap. Feeds the board's ＋ menu; eight outlasts a typical
#: week of use and older entries fall off the end.
RECENT_FILES_CAP = 8

#: Untitled-workspace cap. Eight rows fit the Workspace rail without
#: scrolling; the ninth pushes the oldest off. Naming one moves it out of
#: this list entirely, which is the only way to stop it decaying.
MAX_RECENT_WORKSPACES = 8

#: Bumped when the JSON shape changes incompatibly; a reader seeing a newer
#: version than it understands resets rather than misreading it. Version 2
#: replaced the single ``last_workspace`` slot with ``recent_workspaces``
#: and gave every record an ``id``.
SCHEMA_VERSION = 2

#: How the main document was opened -- the D3 legacy intents plus the
#: everyday default. Restoring replays the recorded mode instead of
#: re-asking a question the user already answered.
MAIN_MODES = ("normal", "read_only", "converted_copy")


class NameInUse(ValueError):
    """Raised by :meth:`WorkspaceHistory.keep`/:meth:`rename` when the
    requested name already belongs to another workspace.

    Names are unique because they are how a person refers to a workspace;
    identity itself is the id, so nothing is ever overwritten to make room
    for a name. The shell checks :meth:`WorkspaceHistory.name_in_use` first
    to say so inline -- this exception is the backstop, not the message.
    """


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
    """A remembered workspace.

    ``id`` is the identity and is assigned by the store, so a record built
    by a caller may leave it empty. ``name``/``saved_at`` are set only once
    the workspace has been named (kept); untitled ones have neither.
    """

    main: MainRecord
    references: tuple[ReferenceRecord, ...] = ()
    name: str | None = None
    saved_at: str | None = None
    id: str = ""

    @property
    def is_named(self) -> bool:
        return self.name is not None


def new_id() -> str:
    """A fresh workspace identity. Random rather than sequential: two app
    instances sharing one store must never mint the same id."""
    return uuid4().hex


class WorkspaceHistory:
    """The store: load on construction, persist on every mutation.

    A missing file is the ordinary first launch and loads empty. An
    unreadable one (corrupt JSON, wrong shape, newer schema) also loads
    empty but sets :attr:`load_failed`, so the shell can say so once --
    the app never refuses to launch over its own history.
    """

    def __init__(self, store_path: Path) -> None:
        self.store_path = store_path
        self.recent_files: list[str] = []
        #: Untitled workspaces, newest first, capped.
        self.recent_workspaces: list[WorkspaceRecord] = []
        #: Named workspaces, in the order they were named.
        self.workspaces: list[WorkspaceRecord] = []
        #: The workspace on the board, by id -- what launch reopens.
        self.current_id: str | None = None
        self.load_failed = False
        self._load()

    # ------------------------------------------------------------------
    # recent files (the board's ＋ menu, not a rail group)

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

    # ------------------------------------------------------------------
    # reading

    def all_workspaces(self) -> list[WorkspaceRecord]:
        """Every workspace, named first then recent -- the rail's own order."""
        return [*self.workspaces, *self.recent_workspaces]

    def by_id(self, workspace_id: str | None) -> WorkspaceRecord | None:
        """The workspace with *workspace_id*, or None."""
        if not workspace_id:
            return None
        for workspace in self.all_workspaces():
            if workspace.id == workspace_id:
                return workspace
        return None

    def current(self) -> WorkspaceRecord | None:
        """The workspace on the board, or None."""
        return self.by_id(self.current_id)

    def named(self, name: str) -> WorkspaceRecord | None:
        """The named workspace called *name*, or None."""
        for workspace in self.workspaces:
            if workspace.name == name:
                return workspace
        return None

    def name_in_use(self, name: str, excluding: str | None = None) -> bool:
        """Whether *name* already belongs to a workspace other than the one
        with id *excluding* -- the seam the name dialog says "that name is
        in use" from, before anything is attempted."""
        for workspace in self.workspaces:
            if workspace.name == name and workspace.id != excluding:
                return True
        return False

    # ------------------------------------------------------------------
    # mutations (each persists immediately)

    def start_workspace(self, record: WorkspaceRecord) -> WorkspaceRecord:
        """Begin a new untitled workspace from *record* and make it current.

        Opening a file starts a workspace; this is that. The new entry goes
        to the front of Recent with a fresh id, any older entry holding the
        same files merges into it, and the oldest falls off the cap.
        Returns the stored record, which is where the caller reads the id.
        """
        stored = replace(record, name=None, saved_at=None, id=new_id())
        self.recent_workspaces.insert(0, stored)
        self.current_id = stored.id
        self._dedupe_and_cap()
        self._persist()
        return stored

    def update_current(self, main: MainRecord, references: tuple[ReferenceRecord, ...]) -> None:
        """Rewrite the current workspace's files in place -- named or not.

        This is rule 4 made mechanical: a workspace looks after itself, so
        adding a reference or swapping the main is simply what the workspace
        now *is*. There is no save step and no "changed since saved", because
        there is no snapshot to differ from. A no-op when nothing is current.
        """
        current = self.current()
        if current is None:
            return
        self._replace_record(replace(current, main=main, references=references))
        self._dedupe_and_cap()
        self._persist()

    def set_current(self, workspace_id: str | None) -> None:
        """Make *workspace_id* the workspace on the board.

        Switching away shelves whatever was current: an untitled workspace
        is already in Recent, so shelving is simply leaving it there, and
        the newly-current untitled one moves to the front. Nothing is
        discarded by a click.
        """
        workspace = self.by_id(workspace_id)
        self.current_id = workspace.id if workspace is not None else None
        if workspace is not None and not workspace.is_named:
            self.recent_workspaces.remove(workspace)
            self.recent_workspaces.insert(0, workspace)
        self._persist()

    def keep(self, workspace_id: str, name: str) -> WorkspaceRecord:
        """Name a workspace, promoting it out of Recent for good.

        Naming is the one act that stops a workspace decaying, so it moves
        the entry from ``recent_workspaces`` to ``workspaces``. Raises
        :class:`NameInUse` rather than overwriting; the shell asks again.
        """
        workspace = self.by_id(workspace_id)
        if workspace is None:
            raise KeyError(workspace_id)
        name = name.strip()
        if not name:
            raise ValueError("A named workspace needs a name")
        if self.name_in_use(name, excluding=workspace_id):
            raise NameInUse(name)
        named = replace(workspace, name=name, saved_at=_now_stamp())
        if workspace in self.recent_workspaces:
            self.recent_workspaces.remove(workspace)
            self.workspaces.append(named)
        else:
            self.workspaces[self.workspaces.index(workspace)] = named
        self._persist()
        return named

    def rename(self, workspace_id: str, name: str) -> WorkspaceRecord:
        """Rename a named workspace. Same uniqueness rule as :meth:`keep`,
        and the same refusal: an existing entry is never displaced."""
        return self.keep(workspace_id, name)

    def remove(self, workspace_id: str) -> None:
        """Forget a workspace entirely -- its files are never touched.
        Unknown ids are a quiet no-op; removing the current one leaves the
        board with nothing current."""
        workspace = self.by_id(workspace_id)
        if workspace is None:
            return
        if workspace in self.recent_workspaces:
            self.recent_workspaces.remove(workspace)
        else:
            self.workspaces.remove(workspace)
        if self.current_id == workspace_id:
            self.current_id = None
        self._persist()

    def duplicate(self, workspace_id: str) -> WorkspaceRecord:
        """Fork a workspace, leaving the original untouched.

        The escape hatch live identity costs us: with no snapshot to
        experiment against, Duplicate is how a person keeps the arrangement
        they have while trying another. A named workspace forks to a named
        copy ("Foo copy", uniquified) sitting beside it -- a fork of
        something deliberately kept should be equally safe. An untitled one
        forks to another untitled entry at the front of Recent. Neither
        becomes current: duplicating is not switching.
        """
        workspace = self.by_id(workspace_id)
        if workspace is None:
            raise KeyError(workspace_id)
        if workspace.is_named:
            copy = replace(
                workspace,
                id=new_id(),
                name=self._free_name(f"{workspace.name} copy"),
                saved_at=_now_stamp(),
            )
            self.workspaces.insert(self.workspaces.index(workspace) + 1, copy)
        else:
            copy = replace(workspace, id=new_id(), name=None, saved_at=None)
            self.recent_workspaces.insert(0, copy)
            # Capped but not deduped: the fork is content-identical to its
            # source by definition, and merging it back would defeat the
            # whole action.
            self._cap()
        self._persist()
        return copy

    def relocate_main(self, workspace_id: str, path: str) -> None:
        """Repoint a workspace's main at *path* (the Locate… action).

        The only path edit that exists: a file that moved is still the same
        workspace, and re-finding it must not mean rebuilding the
        arrangement by hand. The recorded open mode is kept -- relocating
        answers "where", never "how"."""
        workspace = self.by_id(workspace_id)
        if workspace is None:
            return
        self._replace_record(
            replace(workspace, main=replace(workspace.main, path=path))
        )
        self._persist()

    def relocate_reference(self, workspace_id: str, index: int, path: str) -> None:
        """Repoint the file reference at *index* at *path* (Locate…, again).

        Out-of-range indices and library references are quiet no-ops: a
        bundled set is not a file on disk, so it has no path to relocate.
        """
        workspace = self.by_id(workspace_id)
        if workspace is None or not 0 <= index < len(workspace.references):
            return
        existing = workspace.references[index]
        if existing.kind != "file":
            return
        references = list(workspace.references)
        references[index] = replace(existing, path=path)
        self._replace_record(replace(workspace, references=tuple(references)))
        self._persist()

    def remove_reference(self, workspace_id: str, index: int) -> None:
        """Drop the reference at *index* from a workspace's record -- the
        missing-file banner's Remove, which acts on the record rather than
        on the board (the file never loaded, so there is no pin to unpin)."""
        workspace = self.by_id(workspace_id)
        if workspace is None or not 0 <= index < len(workspace.references):
            return
        references = list(workspace.references)
        del references[index]
        self._replace_record(replace(workspace, references=tuple(references)))
        self._persist()

    # ------------------------------------------------------------------
    # internals

    def _replace_record(self, record: WorkspaceRecord) -> None:
        """Swap a record for an updated version of itself, in place, in
        whichever list holds it -- position is meaning in both (Recent is
        newest-first, Workspaces is naming order), so an update must never
        reorder."""
        for entries in (self.recent_workspaces, self.workspaces):
            for index, existing in enumerate(entries):
                if existing.id == record.id:
                    entries[index] = record
                    return

    def _dedupe_and_cap(self) -> None:
        self._dedupe_against_current()
        self._cap()

    def _dedupe_against_current(self) -> None:
        """Merge older Recent entries holding the same files into the
        current one -- newest wins, exactly like the recent-files dedup.

        Deliberately anchored on the *current* workspace rather than sweeping
        the whole list: it is the one that just moved, so it is the newer of
        any colliding pair, and anchoring this way means a fork made by
        :meth:`duplicate` can never swallow the workspace it was forked
        from. Named workspaces are exempt on both sides -- two of them may
        hold the same files, because someone said so twice.
        """
        current = self.current()
        if current is None or current.is_named:
            return
        key = _content_key(current)
        self.recent_workspaces = [
            workspace
            for workspace in self.recent_workspaces
            if workspace.id == current.id or _content_key(workspace) != key
        ]

    def _cap(self) -> None:
        """Let the oldest untitled workspaces fall off the end.

        The current one is never the one dropped -- it is on the board, so
        however old its entry is, it is not spare. The oldest entry that
        is not current goes instead.
        """
        while len(self.recent_workspaces) > MAX_RECENT_WORKSPACES:
            for index in reversed(range(len(self.recent_workspaces))):
                if self.recent_workspaces[index].id != self.current_id:
                    del self.recent_workspaces[index]
                    break
            else:  # pragma: no cover - unreachable above the cap
                return

    def _free_name(self, base: str) -> str:
        """*base* if no workspace holds it, else "base 2", "base 3", …"""
        if not self.name_in_use(base):
            return base
        suffix = 2
        while self.name_in_use(f"{base} {suffix}"):
            suffix += 1
        return f"{base} {suffix}"

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
            version = data.get("version")
            if version > SCHEMA_VERSION:
                raise ValueError("newer schema than this app understands")
            self.recent_files = [
                entry["path"] for entry in data.get("recent_files", [])
            ][:RECENT_FILES_CAP]
            if version < SCHEMA_VERSION:
                self._load_v1(data)
            else:
                self._load_v2(data)
            if any(workspace.name is None for workspace in self.workspaces):
                raise ValueError("named workspace without a name")
            if self.by_id(self.current_id) is None:
                self.current_id = None
        except (TypeError, KeyError, ValueError):
            # Unreadable history resets to empty; load_failed lets the shell
            # say so once instead of failing silently (honesty rule 3).
            self.recent_files = []
            self.recent_workspaces = []
            self.workspaces = []
            self.current_id = None
            self.load_failed = True

    def _load_v1(self, data: dict) -> None:
        """Migrate a version-1 store: the single automatic last-workspace
        slot becomes the first Recent entry, named workspaces carry over,
        and every record gains an id. Nothing is current -- version 1 never
        recorded which workspace was on the board."""
        last = data.get("last_workspace")
        self.recent_workspaces = (
            [replace(_workspace_from_json(last), id=new_id())] if last else []
        )
        self.workspaces = [
            replace(_workspace_from_json(entry), id=new_id())
            for entry in data.get("workspaces", [])
        ]
        self.current_id = None

    def _load_v2(self, data: dict) -> None:
        self.recent_workspaces = [
            _workspace_from_json(entry)
            for entry in data.get("recent_workspaces", [])
        ][:MAX_RECENT_WORKSPACES]
        self.workspaces = [
            _workspace_from_json(entry) for entry in data.get("workspaces", [])
        ]
        self.current_id = data.get("current_id")

    def _persist(self) -> None:
        data = {
            "version": SCHEMA_VERSION,
            "recent_files": [{"path": path} for path in self.recent_files],
            "recent_workspaces": [
                _workspace_to_json(workspace) for workspace in self.recent_workspaces
            ],
            "workspaces": [
                _workspace_to_json(workspace) for workspace in self.workspaces
            ],
            "current_id": self.current_id,
        }
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.store_path.with_name(self.store_path.name + ".tmp")
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        os.replace(temp, self.store_path)


def _now_stamp() -> str:
    from datetime import datetime

    return datetime.now().isoformat(timespec="seconds")


def _resolve(path: str) -> str:
    """Identity key for deduplication: the resolved path when the file
    exists, the literal spelling otherwise (a missing file still deduplicates
    against its own spelling, and never collides via a half-resolved form)."""
    try:
        return str(Path(path).resolve())
    except OSError:
        return path


def _content_key(record: WorkspaceRecord) -> tuple:
    """What makes two untitled workspaces the same arrangement: the main
    (where and how) and the ordered references. Different references are a
    different arrangement, so both entries stay."""
    return (
        _resolve(record.main.path),
        record.main.mode,
        tuple(
            (reference.kind, reference.set_id)
            if reference.kind == "library"
            else (reference.kind, _resolve(reference.path or ""))
            for reference in record.references
        ),
    )


def _workspace_to_json(record: WorkspaceRecord) -> dict:
    data: dict = {
        "id": record.id,
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
        # A record written without one predates the id or was hand-edited;
        # minting a fresh one keeps the store usable rather than declaring
        # the whole file corrupt over an identity nobody has referenced yet.
        id=data.get("id") or new_id(),
    )
