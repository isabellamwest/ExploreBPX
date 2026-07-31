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

    def new_from_file(self, path: Path) -> None:
        """Clone *path* into a fresh unsaved session and dock *path* itself
        as the read-only reference ("New from source", PLAN-multi-file.md
        decision 8).

        The clone is built from the file's on-disk bytes under a derived
        "{stem} (copy)" filename (the Export naming convention), keeping the
        file's own format, with no backing file and ``dirty`` set -- exactly
        the never-saved shape ``new_document`` creates, so the first Save
        routes through Save As and the origin on disk is never at risk.

        Loads the clone and the snapshot before touching either field: a
        failure (``core.bpx_gateway.LoadError``/``OSError``) leaves the
        state completely unchanged. A reference already docked at *path*
        is kept as-is (dedupe by path); any other reference is replaced --
        the one-reference rule.
        """
        clone_name = f"{path.stem} (copy){path.suffix}"
        document = BPXDocument.from_bytes(path.read_bytes(), clone_name)
        if (
            self.reference is not None
            and self.reference.path is not None
            and self.reference.path.resolve() == path.resolve()
        ):
            reference = self.reference
        else:
            reference = ReferenceSnapshot.load(path)
        session = DocumentSession(document)
        session.dirty = True
        self.active = session
        self.reference = reference

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
        if (
            self.reference is not None
            and self.reference.path is not None
            and self.reference.path.resolve() == resolved
        ):
            return OpenReferenceOutcome.ALREADY_REFERENCE
        if (
            self.active is not None
            and self.active.backing_file is not None
            and self.active.backing_file.resolve() == resolved
        ):
            return OpenReferenceOutcome.IS_MAIN
        self.reference = ReferenceSnapshot.load(path)
        return OpenReferenceOutcome.ADDED

    def open_reference_set(self, set_id: str) -> OpenReferenceOutcome:
        """Dock bundled reference-library set *set_id* as the reference,
        replacing any reference already docked (silent replace -- signed
        decision, Phase B 2026-07-31: a snapshot is disposable, immutable
        state, and re-docking the old one is one click).

        Dedupes by set id against the docked reference (returns
        ``ALREADY_REFERENCE``, quiet no-op). ``IS_MAIN`` can never apply: a
        bundled set is not a file on disk, so it can never be the active
        session's backing file.

        Raises ``KeyError`` for an unknown id, exactly as
        ``ReferenceSnapshot.from_library`` does; the caller decides how to
        surface it.
        """
        if self.reference is not None and self.reference.set_id == set_id:
            return OpenReferenceOutcome.ALREADY_REFERENCE
        self.reference = ReferenceSnapshot.from_library(set_id)
        return OpenReferenceOutcome.ADDED

    def remove_reference(self) -> None:
        """Undock the reference, if any."""
        self.reference = None

    def reload_reference(self) -> None:
        """Re-snapshot the docked reference from its own path on disk (the
        Source page's stale-band Reload, PLAN-multi-file.md decision 11).

        Raises ``core.bpx_gateway.LoadError``/``OSError`` exactly as
        ``ReferenceSnapshot.load`` does; on failure the docked snapshot is
        left untouched (the caller surfaces the error -- C3).

        A library-set reference (``path`` is None) is a quiet no-op: a
        bundled set is immutable, so there is nothing on disk to reload.
        """
        if self.reference is None or self.reference.path is None:
            return
        self.reference = ReferenceSnapshot.load(self.reference.path)

    def swap_roles(self, promoted_path: Path, demoted_path: Path) -> None:
        """The "Make main" swap: promote *promoted_path* (today's reference)
        to the active session, demoting *demoted_path* (today's main) to a
        fresh reference snapshot -- both loaded from disk (PLAN-multi-file.md
        M4).

        Loads both files before touching either field: if either raises
        (``core.bpx_gateway.LoadError``/``OSError``, exactly as ``open`` and
        ``ReferenceSnapshot.load`` do), ``self.active`` and ``self.reference``
        are left completely unchanged. The demoted snapshot always reflects
        what is on disk, so a discarded edit on the old main can never appear
        in it.
        """
        document = BPXDocument.from_bytes(promoted_path.read_bytes(), promoted_path.name)
        session = DocumentSession(document)
        session.backing_file = promoted_path
        reference = ReferenceSnapshot.load(demoted_path)
        self.active = session
        self.reference = reference
