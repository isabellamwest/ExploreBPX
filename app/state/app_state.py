"""Application-level state container (frontend-agnostic).

AppState owns the single active DocumentSession. It is the entry point for
opening and closing documents from the UI layer. All per-document state
(selection, undo, document reference) lives in DocumentSession.
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path

from core import document_factory
from core.document import BPXDocument
from state.document_session import DocumentSession
from state.reference_snapshot import ReferenceSnapshot

#: Hard cap on pinned references (multi-reference track, signed design):
#: a fifth pin is rejected with ``PinReferenceOutcome.AT_CAP``, never a
#: silent replace.
REFERENCE_PIN_CAP = 4


class PinReferenceOutcome(Enum):
    """Result of the pin mutators below, for toast feedback."""

    PINNED = "pinned"
    ALREADY_PINNED = "already_pinned"
    IS_MAIN = "is_main"
    AT_CAP = "at_cap"


class AppState:
    """Application-level container for the active document session and the
    pinned reference snapshots.

    AppState holds one optional DocumentSession (the main, editable
    document) and an ordered list of pinned ReferenceSnapshots (frozen,
    read-only files docked beside it). Pinning **appends**, in pin order, up
    to ``REFERENCE_PIN_CAP``; a pin's identity (badge letters/colour, see
    ``ui_qt.reference_identity``) derives from its position in this list.
    Pin persistence across restart and pin reorder are deferred (see
    ``PLAN-multi-reference.md``).
    """

    def __init__(self) -> None:
        self.active: DocumentSession | None = None
        self.references: list[ReferenceSnapshot] = []

    @property
    def reference(self) -> ReferenceSnapshot | None:
        """The first pinned reference, or ``None`` -- a compatibility shim
        for the call sites deliberately deferred to a later phase (the
        Source page and its stale-band machinery show the first pin until
        the Phase 2 selector lands). Read-only: mutators below assign
        ``self.references`` directly.
        """
        return self.references[0] if self.references else None

    @property
    def has_document(self) -> bool:
        """True when a document session is open."""
        return self.active is not None

    @property
    def at_reference_cap(self) -> bool:
        """True when no further reference can be pinned."""
        return len(self.references) >= REFERENCE_PIN_CAP

    def open(self, path: Path) -> None:
        """Open a file, creating a fresh DocumentSession.

        Reads bytes from ``path``, parses the BPX document, and sets
        ``backing_file`` on the session so that subsequent saves write back
        to the same location.

        Raises ``core.bpx_gateway.LoadError`` for unparseable files and
        ``OSError`` if the file cannot be read.
        """
        document = BPXDocument.from_bytes(path.read_bytes(), path.name)
        session = DocumentSession(document)
        session.backing_file = path
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

        Pinning routes through the same rules as :meth:`pin_reference`
        (decision D2): the clone is **always** created, and the returned
        outcome says what happened to the pin -- appended (``PINNED``), kept
        (``ALREADY_PINNED``, dedupe by path), or skipped because four
        references are already pinned (``AT_CAP``; the caller says so).

        Loads the clone (and any new snapshot) before touching either
        field: a failure (``core.bpx_gateway.LoadError``/``OSError``)
        leaves the state completely unchanged.
        """
        clone_name = f"{path.stem} (copy){path.suffix}"
        document = BPXDocument.from_bytes(path.read_bytes(), clone_name)
        outcome = PinReferenceOutcome.PINNED
        reference: ReferenceSnapshot | None = None
        if self._pinned_at_path(path) is not None:
            outcome = PinReferenceOutcome.ALREADY_PINNED
        elif self.at_reference_cap:
            outcome = PinReferenceOutcome.AT_CAP
        else:
            reference = ReferenceSnapshot.load(path)
        session = DocumentSession(document)
        session.dirty = True
        self.active = session
        if reference is not None:
            self.references = self.references + [reference]
        return outcome

    def close(self) -> None:
        """Close the active session.

        Leaves ``references`` untouched: closing the main file is just
        closing the main file, never a prompt about the pinned references.
        """
        self.active = None

    def pin_reference(self, path: Path) -> PinReferenceOutcome:
        """Pin *path* as a reference, appending to the pin list.

        Dedupes by resolved path against every pinned reference (returns
        ``ALREADY_PINNED``, quiet no-op) and the active session's backing
        file (returns ``IS_MAIN``, quiet no-op), then enforces the hard cap
        (``AT_CAP``, nothing loaded) before loading. Pinning never replaces:
        the fifth pin is rejected, not swapped in.

        Raises ``core.bpx_gateway.LoadError``/``OSError`` exactly as
        ``ReferenceSnapshot.load`` does; the caller decides how to surface a
        load failure.
        """
        if self._pinned_at_path(path) is not None:
            return PinReferenceOutcome.ALREADY_PINNED
        resolved = path.resolve()
        if (
            self.active is not None
            and self.active.backing_file is not None
            and self.active.backing_file.resolve() == resolved
        ):
            return PinReferenceOutcome.IS_MAIN
        if self.at_reference_cap:
            return PinReferenceOutcome.AT_CAP
        self.references = self.references + [ReferenceSnapshot.load(path)]
        return PinReferenceOutcome.PINNED

    def pin_reference_set(self, set_id: str) -> PinReferenceOutcome:
        """Pin bundled reference-library set *set_id*, appending to the pin
        list.

        Dedupes by set id against every pinned reference (returns
        ``ALREADY_PINNED``, quiet no-op), then enforces the hard cap
        (``AT_CAP``). ``IS_MAIN`` can never apply: a bundled set is not a
        file on disk, so it can never be the active session's backing file.

        Raises ``KeyError`` for an unknown id, exactly as
        ``ReferenceSnapshot.from_library`` does; the caller decides how to
        surface it.
        """
        if any(reference.set_id == set_id for reference in self.references):
            return PinReferenceOutcome.ALREADY_PINNED
        if self.at_reference_cap:
            return PinReferenceOutcome.AT_CAP
        self.references = self.references + [ReferenceSnapshot.from_library(set_id)]
        return PinReferenceOutcome.PINNED

    def remove_reference(self, reference: ReferenceSnapshot) -> None:
        """Unpin *reference* (matched by identity, never equality -- two
        pins could conceivably hold equal snapshots of one regenerated
        file). Later pins shift up: badge colour follows the current list
        index (decision D1), with no extra state to reconcile. Unknown
        *reference* is a quiet no-op (a stale click on a just-removed row).
        """
        self.references = [r for r in self.references if r is not reference]

    def reload_reference(self) -> None:
        """Re-snapshot the first pinned reference from its own path on disk
        (the Source page's stale-band Reload -- the Source page shows the
        first pin until the Phase 2 selector lands).

        Replaces slot 0 in place; every other pin is untouched, so pin
        order -- and with it every badge identity -- survives the reload.

        Raises ``core.bpx_gateway.LoadError``/``OSError`` exactly as
        ``ReferenceSnapshot.load`` does; on failure the pinned snapshot is
        left untouched (the caller surfaces the error -- C3).

        A library-set reference (``path`` is None) is a quiet no-op: a
        bundled set is immutable, so there is nothing on disk to reload.
        """
        existing = self.reference
        if existing is None or existing.path is None:
            return
        reloaded = ReferenceSnapshot.load(existing.path)
        self.references = [reloaded] + self.references[1:]

    def _pinned_at_path(self, path: Path) -> ReferenceSnapshot | None:
        """The pinned reference snapshotted from *path*, if any."""
        resolved = path.resolve()
        for reference in self.references:
            if reference.path is not None and reference.path.resolve() == resolved:
                return reference
        return None
