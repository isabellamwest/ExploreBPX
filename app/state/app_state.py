"""Application-level state container (frontend-agnostic).

AppState owns the single active DocumentSession. It is the entry point for
opening and closing documents from the UI layer. All per-document state
(selection, undo, document reference) lives in DocumentSession.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from core import bpx_gateway, document_factory
from core.document import BPXDocument
from core.load_record import LoadRecord
from state.document_session import DocumentSession
from state.reference_snapshot import ReferenceSnapshot


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
    the order is the identity the UI layer colours and letters them by (see
    ``PLAN-multi-reference.md``). Nothing here knows about badges.
    """

    def __init__(self) -> None:
        self.active: DocumentSession | None = None
        self.references: list[ReferenceSnapshot] = []

    @property
    def reference(self) -> ReferenceSnapshot | None:
        """The first pinned reference, or ``None`` -- a compatibility shim
        for call sites not yet converted to ``references`` (the Source page,
        Phase 2). Read-only: mutators below assign ``self.references``
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

    def legacy_version(self, path: Path) -> str | None:
        """The file's own ``Header.BPX`` version when *path* holds a
        detectably legacy v0.x object, else ``None`` -- the cheap look the
        D3 open prompt decides from. No session is touched and nothing is
        validated; the chosen open re-reads the file, and that read is the
        one that counts.

        Raises ``core.bpx_gateway.LoadError`` / ``OSError`` exactly like
        :meth:`open`, so a caller's error handling covers both.
        """
        raw, _fmt = bpx_gateway.load_raw(path.read_bytes(), path.name)
        return bpx_gateway.legacy_version(raw)

    def open_read_only(self, path: Path) -> None:
        """Open *path* as-is, read-only (decision D3's second path).

        The raw content is installed unconverted, ``read_only`` is set so
        no command can execute, and no backing file is adopted -- this
        session never writes *path*. For a legacy object ``bpx`` still
        checks a converted copy internally; the record's Read as / Checked
        rows state that, verbatim Phase 4.
        """
        data = path.read_bytes()
        document = BPXDocument.from_bytes(data, path.name)
        session = DocumentSession(document)
        session.read_only = True
        session.load_record = LoadRecord.capture(data, document, path=path)
        self.active = session

    def open_converted_copy(self, path: Path) -> None:
        """Open a converted v1.x copy of legacy *path* as a new unsaved
        document (decision D3's primary path).

        The copy is named "{stem} (converted){suffix}", keeps the source's
        format, and has no backing file with ``dirty`` set -- the
        never-saved shape ``new_document`` creates, so the first Save
        routes through Save As and *path* itself is never written. The
        record keeps the source's provenance (From facts, YAML-comment
        fact), the ``new_from_file`` convention; ``is_legacy`` is judged
        on the converted content, so the record truthfully reads v1.x.
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

    def new_from_file(self, path: Path) -> PinReferenceOutcome:
        """Clone *path* into a fresh unsaved session and pin *path* itself
        as a read-only reference ("New from source").

        The clone is built from the file's on-disk bytes under a derived
        "{stem} (copy)" filename (the Export naming convention), keeping the
        file's own format, with no backing file and ``dirty`` set -- exactly
        the never-saved shape ``new_document`` creates, so the first Save
        routes through Save As and the origin on disk is never at risk.

        Loads the clone and the snapshot before touching either field: a
        failure (``core.bpx_gateway.LoadError``/``OSError``) leaves the
        state completely unchanged. Already-pinned references survive: the
        source is *appended* to them, so a comparison set built up before
        the clone is not thrown away by it.

        The returned outcome describes the pin only -- the new document is
        always created (decision D2). At the cap the source is not pinned
        and ``AT_CAP`` says so; a source already pinned returns
        ``ALREADY_REFERENCE`` and is left as-is.
        """
        clone_name = f"{path.stem} (copy){path.suffix}"
        data = path.read_bytes()
        document = BPXDocument.from_bytes(data, clone_name)
        existing = self._pinned_at(path)
        outcome = PinReferenceOutcome.ADDED
        reference: ReferenceSnapshot | None = None
        if existing is not None:
            outcome = PinReferenceOutcome.ALREADY_REFERENCE
        elif self.at_reference_cap:
            outcome = PinReferenceOutcome.AT_CAP
        else:
            reference = ReferenceSnapshot.load(path)
        session = DocumentSession(document)
        session.dirty = True
        # The clone's content came from *path* even though nothing will be
        # saved there -- the record's From facts state that provenance.
        session.load_record = LoadRecord.capture(data, document, path=path)
        self.active = session
        if reference is not None:
            self.references.append(reference)
        return outcome

    def close(self) -> None:
        """Close the active session.

        Leaves ``reference`` untouched: closing the main file is just closing
        the main file, never a prompt about the docked reference.
        """
        self.active = None

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
        left untouched (the caller surfaces the error -- C3).

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
