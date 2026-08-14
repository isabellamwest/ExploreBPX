"""Application-level state container (frontend-agnostic).

AppState owns the single active DocumentSession. It is the entry point for
opening and closing documents from the UI layer. All per-document state
(selection, undo, document reference) lives in DocumentSession.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from core import bpx_gateway, document_factory
from core.document import BPXDocument
from core.load_record import LoadRecord
from state.document_session import DocumentSession
from state.reference_snapshot import ReferenceSnapshot
from state.workspace_history import (
    MainRecord,
    ReferenceRecord,
    WorkspaceHistory,
    WorkspaceRecord,
)

if TYPE_CHECKING:
    from pathlib import Path

#: The hard cap on pinned references. Four is what the comparison surfaces
#: were designed to carry -- four badge colours that stay tellable apart, four
#: chips in the strip at a ~700px window, four curves on one chart. Pinning a
#: fifth is refused outright rather than silently dropping an earlier pin.
MAX_PINNED_REFERENCES = 4


class PinReferenceOutcome(Enum):
    """Result of :meth:`AppState.pin_reference`/:meth:`pin_reference_set`,
    for toast feedback."""

    ADDED = "added"
    ALREADY_REFERENCE = "already_reference"
    IS_MAIN = "is_main"
    AT_CAP = "at_cap"


class AppState:
    """Application-level container for the active document session and the
    pinned reference snapshots.

    AppState holds one optional DocumentSession (the main, editable document)
    and an ordered list of pinned ReferenceSnapshots (frozen, read-only files
    compared against it). Pinning **appends**: up to
    ``MAX_PINNED_REFERENCES`` references coexist, ordered by pin time, and
    the order is the identity the UI layer colours and letters them by.
    Nothing here knows about badges.
    """

    def __init__(self, history: WorkspaceHistory | None = None) -> None:
        self.active: DocumentSession | None = None
        self.references: list[ReferenceSnapshot] = []
        #: Optional persistent workspace history. Recording happens here at
        #: the open/pin funnel -- not in the UI layer -- so every UI path
        #: that changes the workspace is recorded without remembering to.
        #: ``None`` (the default, and what most tests construct) records
        #: nothing.
        self.history = history
        #: What the history should call the current main document: set by
        #: the three real opens (path + open mode), cleared when the session
        #: has no on-disk identity (scaffolds, clones, closed). While
        #: ``None``, reference changes leave the workspace record untouched
        #: -- a scaffold session must not erase a restorable workspace.
        self._last_main: MainRecord | None = None

    @property
    def reference(self) -> ReferenceSnapshot | None:
        """The first pinned reference, or ``None`` -- a compatibility shim
        for call sites not yet converted to ``references`` (the Source page).
        Read-only: mutators below assign ``self.references``
        directly.
        """
        return self.references[0] if self.references else None

    @property
    def at_reference_cap(self) -> bool:
        """True when no further reference can be pinned -- the seam the
        Workspace's two entry buttons disable themselves from."""
        return len(self.references) >= MAX_PINNED_REFERENCES

    def _pinned_at(self, path: Path) -> ReferenceSnapshot | None:
        """The pinned reference loaded from *path*, if any (resolved-path
        match, so two spellings of one file are one pin)."""
        resolved = path.resolve()
        for reference in self.references:
            if reference.path is not None and reference.path.resolve() == resolved:
                return reference
        return None

    @property
    def has_document(self) -> bool:
        """True when a document session is open."""
        return self.active is not None

    def open(self, path: Path) -> None:
        """Open a file, creating a fresh DocumentSession.

        Reads bytes from ``path``, parses the BPX document, and sets
        ``backing_file`` on the session so that subsequent saves write back
        to the same location.

        Raises ``core.bpx_gateway.LoadError`` for unparseable files and
        ``OSError`` if the file cannot be read.
        """
        data = path.read_bytes()
        document = BPXDocument.from_bytes(data, path.name)
        session = DocumentSession(document)
        session.backing_file = path
        # Captured from the same bytes the document was built from, so the
        # record states what this load actually did (format, legacy, reach,
        # comments, disk facts) -- never a second look at the file.
        session.load_record = LoadRecord.capture(data, document, path=path)
        self.active = session
        self._note_main_opened(path, "normal")

    def legacy_version(self, path: Path) -> str | None:
        """The file's own ``Header.BPX`` version when *path* holds a
        detectably legacy v0.x object, else ``None`` -- the cheap look the
        legacy-file open prompt decides from. No session is touched and
        nothing is validated; the chosen open re-reads the file, and that
        read is the one that counts.

        Raises ``core.bpx_gateway.LoadError`` / ``OSError`` exactly like
        :meth:`open`, so a caller's error handling covers both.
        """
        raw, _fmt = bpx_gateway.load_raw(path.read_bytes(), path.name)
        return bpx_gateway.legacy_version(raw)

    def open_read_only(self, path: Path) -> None:
        """Open *path* as-is, read-only.

        The raw content is installed unconverted, ``read_only`` is set so
        no command can execute, and no backing file is adopted -- this
        session never writes *path*. For a legacy object ``bpx`` still
        checks a converted copy internally; the record's Read as / Checked
        rows state that plainly.
        """
        data = path.read_bytes()
        document = BPXDocument.from_bytes(data, path.name)
        session = DocumentSession(document)
        session.read_only = True
        session.load_record = LoadRecord.capture(data, document, path=path)
        self.active = session
        self._note_main_opened(path, "read_only")

    def open_converted_copy(self, path: Path) -> None:
        """Open a converted v1.x copy of legacy *path* as a new unsaved
        document.

        The copy is named "{stem} (converted){suffix}", keeps the source's
        format, and has no backing file with ``dirty`` set -- the
        never-saved shape ``new_document`` creates, so the first Save
        routes through Save As and *path* itself is never written. The
        record keeps the source's provenance (From facts, YAML-comment
        fact) even though nothing will be written there; ``is_legacy`` is
        judged on the converted content, so the record truthfully reads
        v1.x.
        """
        data = path.read_bytes()
        raw, fmt = bpx_gateway.load_raw(data, path.name)
        converted = bpx_gateway.convert_legacy(raw)
        name = f"{path.stem} (converted){path.suffix}"
        document = BPXDocument.from_raw(converted, filename=name, fmt=fmt)
        session = DocumentSession(document)
        session.dirty = True
        session.load_record = LoadRecord.capture(data, document, path=path)
        self.active = session
        self._note_main_opened(path, "converted_copy")

    def new_document(self, model: str) -> None:
        """Create a fresh incomplete document scaffold, replacing the active session.

        Builds the scaffold via ``document_factory.create`` (no invented
        scientific values), wraps it in a new ``DocumentSession`` with no
        backing file, and marks it dirty since it has never been saved.

        Raises ``ValueError`` for an unsupported ``model``.
        """
        raw = document_factory.create(model)
        document = BPXDocument.from_raw(raw, filename="untitled.json", fmt="json")
        session = DocumentSession(document)
        session.dirty = True
        self.active = session
        # A scaffold has no on-disk identity yet; it joins the history only
        # once saved (note_main_saved).
        self._last_main = None

    def close(self) -> None:
        """Close the active session.

        Leaves ``reference`` untouched: closing the main file is just closing
        the main file, never a prompt about the docked reference.
        """
        self.active = None
        # The recorded last workspace survives the close -- that is the
        # point of it -- but later pin changes no longer belong to it.
        self._last_main = None

    def pin_reference(self, path: Path) -> PinReferenceOutcome:
        """Pin *path* as a reference, appending it after those already pinned.

        Every no-op outcome is decided before loading: *path* already pinned
        (``ALREADY_REFERENCE``), *path* being the active session's backing
        file (``IS_MAIN``), or the cap already reached (``AT_CAP``). The
        already-pinned check comes first, so re-pinning at the cap reads as
        the harmless duplicate it is rather than as a refusal.

        Raises ``core.bpx_gateway.LoadError``/``OSError`` exactly as
        ``ReferenceSnapshot.load`` does; the caller decides how to surface a
        load failure.
        """
        if self._pinned_at(path) is not None:
            return PinReferenceOutcome.ALREADY_REFERENCE
        if (
            self.active is not None
            and self.active.backing_file is not None
            and self.active.backing_file.resolve() == path.resolve()
        ):
            return PinReferenceOutcome.IS_MAIN
        if self.at_reference_cap:
            return PinReferenceOutcome.AT_CAP
        self.references.append(ReferenceSnapshot.load(path))
        self._sync_workspace()
        return PinReferenceOutcome.ADDED

    def pin_reference_set(self, set_id: str) -> PinReferenceOutcome:
        """Pin bundled reference-library set *set_id*, appending it after
        those already pinned.

        Dedupes by set id (returns ``ALREADY_REFERENCE``, quiet no-op) and
        refuses at the cap (``AT_CAP``). ``IS_MAIN`` can never apply: a
        bundled set is not a file on disk, so it can never be the active
        session's backing file.

        Raises ``KeyError`` for an unknown id, exactly as
        ``ReferenceSnapshot.from_library`` does; the caller decides how to
        surface it.
        """
        if any(reference.set_id == set_id for reference in self.references):
            return PinReferenceOutcome.ALREADY_REFERENCE
        if self.at_reference_cap:
            return PinReferenceOutcome.AT_CAP
        self.references.append(ReferenceSnapshot.from_library(set_id))
        self._sync_workspace()
        return PinReferenceOutcome.ADDED

    def remove_reference(self, reference: ReferenceSnapshot) -> None:
        """Unpin *reference*, leaving the rest of the pins in their order.

        Matched by identity, not equality: two pins can hold equal snapshot
        contents (the same file pinned under two names is prevented, but a
        library set and a file copy of it are not), and only the one the
        caller pointed at should go. Unknown references are a quiet no-op.
        """
        for index, pinned in enumerate(self.references):
            if pinned is reference:
                del self.references[index]
                self._sync_workspace()
                return

    def reload_reference(self, index: int = 0) -> None:
        """Re-snapshot the reference pinned at *index* from its own path on
        disk (the Source page's stale-band Reload).

        The index is the Source page's own selection, so Reload always acts
        on the reference being read rather than on whichever happened to be
        pinned first. Replaced in place: reloading is a refresh of one pin,
        never a reordering of the set.

        Raises ``core.bpx_gateway.LoadError``/``OSError`` exactly as
        ``ReferenceSnapshot.load`` does; on failure the pinned snapshot is
        left untouched, and the caller surfaces the error.

        A library-set reference (``path`` is None) is a quiet no-op: a
        bundled set is immutable, so there is nothing on disk to reload. So
        is an index past the end -- a pin removed between the band appearing
        and Reload being clicked.
        """
        if not 0 <= index < len(self.references):
            return
        existing = self.references[index]
        if existing.path is None:
            return
        self.references[index] = ReferenceSnapshot.load(existing.path)

    # ------------------------------------------------------------------
    # workspaces

    @property
    def workspace_id(self) -> str | None:
        """The id of the workspace on the board, or ``None``.

        Read straight from the store rather than mirrored here: one place
        knows which workspace is current, so the two can never drift.
        """
        return self.history.current_id if self.history is not None else None

    def new_workspace(self) -> None:
        """Start a separate line of work: a real, empty workspace.

        The workspace being left is not discarded -- an untitled one is
        already shelved under Recent and a named one lives in Workspaces --
        so this only lets go of it. The session and its pins go with it:
        a separate line of work starts empty, which is the whole difference
        between this and opening a file (which swaps the main in place).

        The new workspace is created *now* rather than at the first save,
        so it can be seen and named before it holds anything. Asking twice
        in a row does not pile up rows: two empty boards are the same
        arrangement, so the store's dedup merges them.
        """
        self.active = None
        self.references = []
        self._last_main = None
        if self.history is not None:
            self.history.start_workspace(WorkspaceRecord(main=None))

    def enter_workspace(self, workspace_id: str) -> None:
        """Make a remembered workspace current *before* its files reopen.

        Ordering matters: the opens that follow must land in this workspace
        rather than start another, and the recorded main is adopted up
        front so that a main which no longer exists still leaves the
        workspace pointing at where it was -- the pointer Locate… repoints.
        """
        if self.history is None:
            return
        self.history.set_current(workspace_id)
        record = self.history.current()
        self._last_main = record.main if record is not None else None

    # ------------------------------------------------------------------
    # workspace history recording

    def note_main_saved(self) -> None:
        """Record that the active session was saved to its backing file.

        Called by the shell after a successful save: a Save As gives a
        never-saved scaffold/clone/converted-copy its on-disk identity (and
        a saved converted copy is from then on an ordinary v1.x file, so
        the mode resets to ``normal``). A no-op without a backing file.
        """
        session = self.active
        if session is None or session.backing_file is None:
            return
        self._note_main_opened(session.backing_file, "normal")

    def current_workspace_record(self) -> WorkspaceRecord | None:
        """The current workspace's files as a record, or ``None`` when no
        workspace is current at all. Live by construction: it is read off
        the board, not off a snapshot taken earlier.

        ``main`` is ``None`` when the board holds nothing with an on-disk
        identity -- an empty workspace, or a scaffold that has never been
        saved. That is a workspace with nothing in it yet, not the absence
        of a workspace.
        """
        if self.history is None or self.history.current() is None:
            return None
        return WorkspaceRecord(
            main=self._last_main,
            references=self._reference_records(),
            id=self.workspace_id or "",
        )

    def _note_main_opened(self, path: Path, mode: str) -> None:
        """Record *path* as the main document, in whichever workspace should
        own it.

        Opening a file *starts* a workspace when there is none, and
        otherwise swaps into the Main slot of the one already on the board.
        The exception is a **named** workspace, which an ordinary open never
        rewrites: naming a workspace is the act that says "stop rewriting
        this", so a plain open beside one starts a fresh untitled workspace
        instead (carrying the references, which are still pinned) and leaves
        the named entry exactly as it was. Reopening the same main in the
        same mode is not a swap at all, so it stays put.

        A named workspace with no main yet is the exception to the
        exception: filling its empty Main slot is what it was named for, so
        that fills it in place. Only swapping a main it already records
        branches away.
        """
        main = MainRecord(path=str(path), mode=mode)
        self._last_main = main
        if self.history is None:
            return
        self.history.add_recent(str(path))
        current = self.history.current()
        if current is None or (current.is_named and current.main is not None and current.main != main):
            self.history.start_workspace(WorkspaceRecord(main=main, references=self._reference_records()))
        else:
            self.history.update_current(main, self._reference_records())

    def _sync_workspace(self) -> None:
        """Rewrite the current workspace's record from current state.

        Runs at every reference change -- named or not, because a workspace
        looks after itself and there is no save step to wait for.

        The one thing a sync must never do is erase a *recorded* main: a
        scaffold session has no on-disk identity of its own (``_last_main``
        is None), and letting it write that emptiness over the workspace it
        was started from would lose a restorable arrangement. A workspace
        that records no main has nothing to lose, so it records its
        references like any other.
        """
        if self.history is None:
            return
        current = self.history.current()
        if current is None or (self._last_main is None and current.main is not None):
            return
        self.history.update_current(self._last_main, self._reference_records())

    def _reference_records(self) -> tuple[ReferenceRecord, ...]:
        return tuple(
            ReferenceRecord(kind="library", set_id=reference.set_id)
            if reference.set_id is not None
            else ReferenceRecord(kind="file", path=str(reference.path))
            for reference in self.references
        )
