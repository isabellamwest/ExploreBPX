"""Reference snapshot: a frozen, read-only BPX file docked beside the main
document.

A ``ReferenceSnapshot`` is loaded once (raw dict, model identity, section/
parameter counts, a one-shot validation summary) and never mutates
afterwards -- no session, no undo, no dirty state, no file watching. See
``PLAN-multi-file.md`` milestone M1.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from core.bpx_gateway import load_raw
from core.document import BPXDocument


@dataclass(frozen=True)
class ReferenceSnapshot:
    """An immutable, read-only reference document loaded once at open time.

    ``model``/counts/validity are derived through :class:`core.document.
    BPXDocument` -- the same helper the main document's own identity and
    Workspace tile counts come from -- so a reference is judged identically
    to a main document, never by ad hoc parsing here. ``mtime`` is captured
    for a later milestone (stale-on-disk detection) and otherwise unused.
    """

    raw: dict
    path: Path
    filename: str
    model: str | None
    error_count: int
    warning_count: int
    section_count: int
    parameter_count: int
    mtime: float

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
