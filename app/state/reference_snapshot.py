"""Reference snapshot: a frozen, read-only BPX file docked beside the main
document.

A ``ReferenceSnapshot`` is loaded once (raw dict, model identity, section/
parameter counts, a one-shot validation summary) and never mutates
afterwards -- no session, no undo, no dirty state, no file watching.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core import reference_library
from core.bpx_gateway import load_raw
from core.document import BPXDocument


@dataclass(frozen=True)
class ReferenceSnapshot:
    """An immutable, read-only reference document loaded once at open time.

    ``model``/counts/validity are derived through :class:`core.document.
    BPXDocument` -- the same helper the main document's own identity and
    Workspace tile counts come from -- so a reference is judged identically
    to a main document, never by ad hoc parsing here.

    A snapshot has exactly one origin: a file on disk (``path`` set,
    ``set_id`` None) or a bundled reference-library set (``set_id`` set,
    ``path``/``mtime`` None -- there is no file to go stale against or
    reload, and no path to promote via "Make main"). ``filename`` doubles
    as the display label either way: the file's name, or the set's curated
    short title. ``mtime`` is captured for stale-on-disk detection and
    otherwise unused.
    """

    raw: dict
    path: Path | None
    filename: str
    model: str | None
    error_count: int
    warning_count: int
    section_count: int
    parameter_count: int
    mtime: float | None
    set_id: str | None = None

    @classmethod
    def load(cls, path: Path) -> "ReferenceSnapshot":
        """Load a reference snapshot from *path*.

        Raises :class:`core.bpx_gateway.LoadError` for undecodable content
        and ``OSError`` if the file cannot be read -- the same failure modes
        as ``AppState.open``.
        """
        raw, fmt = load_raw(path.read_bytes(), path.name)
        document = BPXDocument.from_raw(raw, filename=path.name, fmt=fmt)
        identity = document.identity
        return cls(
            raw=raw,
            path=path,
            filename=path.name,
            model=identity.model or None,
            error_count=document.error_count,
            warning_count=document.warning_count,
            section_count=document.section_count,
            parameter_count=document.parameter_count,
            mtime=path.stat().st_mtime,
        )

    @classmethod
    def from_library(cls, set_id: str) -> "ReferenceSnapshot":
        """Snapshot a bundled reference-library set.

        The raw dict comes through :mod:`core.reference_library` (the
        anti-corruption adapter -- never a direct asset read), and the
        derivation below is byte-for-byte the one :meth:`load` applies to a
        file, so a bundled set is judged identically to any other reference.

        Raises ``KeyError`` for an unknown id, exactly as
        ``core.reference_library.load_reference_raw`` does.
        """
        by_id = {s.id: s for s in reference_library.list_reference_sets()}
        if set_id not in by_id:
            raise KeyError(f"Unknown reference set id: {set_id!r}")
        ref_set = by_id[set_id]
        raw = reference_library.load_reference_raw(set_id)
        document = BPXDocument.from_raw(raw, filename=ref_set.short_title, fmt="json")
        identity = document.identity
        return cls(
            raw=raw,
            path=None,
            filename=ref_set.short_title,
            model=identity.model or None,
            error_count=document.error_count,
            warning_count=document.warning_count,
            section_count=document.section_count,
            parameter_count=document.parameter_count,
            mtime=None,
            set_id=set_id,
        )
