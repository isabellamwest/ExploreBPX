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


class OpenReferenceOutcome(Enum):
    """Result of :meth:`AppState.open_reference`, for toast feedback."""

    ADDED = "added"
    ALREADY_REFERENCE = "already_reference"
    IS_MAIN = "is_main"


class AppState:
    """Application-level container for the active document session and the
    docked reference snapshot.

    In the current design, AppState holds one optional DocumentSession (the
    main, editable document) and at most one optional ReferenceSnapshot (a
    frozen, read-only file docked beside it). Future multi-document support
    can extend this class further without changing how the UI interacts with
    individual sessions.
    """

    def __init__(self) -> None:
        self.active: DocumentSession | None = None
        self.reference: ReferenceSnapshot | None = None

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

    def close(self) -> None:
        """Close the active session.

        Leaves ``reference`` untouched: closing the main file is just closing
        the main file, never a prompt about the docked reference (decision 9,
        PLAN-multi-file.md).
        """
        self.active = None

    def open_reference(self, path: Path) -> OpenReferenceOutcome:
        """Dock *path* as the reference, replacing any reference already docked.

        Dedupes by resolved path against both the docked reference (returns
        ``ALREADY_REFERENCE``, quiet no-op) and the active session's backing
        file (returns ``IS_MAIN``, quiet no-op) before loading. At most one
        reference exists at a time -- opening a second reference replaces the
        first, since it is a disposable snapshot with nothing to lose.

        Raises ``core.bpx_gateway.LoadError``/``OSError`` exactly as
        ``ReferenceSnapshot.load`` does; the caller decides how to surface a
        load failure.
        """
        resolved = path.resolve()
        if self.reference is not None and self.reference.path.resolve() == resolved:
            return OpenReferenceOutcome.ALREADY_REFERENCE
        if (
            self.active is not None
            and self.active.backing_file is not None
            and self.active.backing_file.resolve() == resolved
        ):
            return OpenReferenceOutcome.IS_MAIN
        self.reference = ReferenceSnapshot.load(path)
        return OpenReferenceOutcome.ADDED

    def remove_reference(self) -> None:
        """Undock the reference, if any."""
        self.reference = None
