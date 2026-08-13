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
from core.completion import partitioned_counts
from core.document import BPXDocument
from core.load_record import LoadRecord


@dataclass(frozen=True)
class ReferenceSnapshot:
    """An immutable, read-only reference document loaded once at open time.

    ``model`` is derived through :class:`core.document.BPXDocument` -- the
    same helper the main document's own identity comes from.
    ``error_count``/``warning_count`` go one step further, through
    :func:`core.completion.partitioned_counts` (completion-task absorption
    then union-pair merging) rather than ``BPXDocument.error_count``/
    ``warning_count`` directly -- those raw properties count pre-absorption
    diagnostics and would let a missing-required-field file read as an
    "error" here while the very same file, opened as the main document,
    reads as an outstanding task. So a reference is judged identically to a
    main document, never by ad hoc parsing here.

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
    #: The file's declared BPX version, for the Workspace row's expanded
    #: record. ``None`` when the Header declares none -- shown as "-" rather
    #: than guessed.
    bpx_version: str | None = None
    #: The citation shown in the record's Citation row: a bundled set's
    #: curated catalog ``references`` field, or a file reference's own
    #: ``Header.References`` (decision D1: the spec field surfaces as
    #: *Citation*). Empty when neither exists -- the row states the absence.
    citation: str = ""
    #: The file's ``Header.Title`` and ``Header.Description``, for the
    #: record's Title/Description rows (``filename`` stays the row-head
    #: label; Title is the document's own name for itself).
    title: str = ""
    description: str = ""
    #: The load-time facts (``core.load_record.LoadRecord``) -- format read,
    #: legacy detection, how far checking reached, comments, disk facts --
    #: captured by the same rule as the main document's, so the two records
    #: can never state the same fact differently. ``None`` never occurs for
    #: a loaded snapshot; the default only keeps old call sites valid.
    record: LoadRecord | None = None

    @classmethod
    def load(cls, path: Path) -> "ReferenceSnapshot":
        """Load a reference snapshot from *path*.

        Raises :class:`core.bpx_gateway.LoadError` for undecodable content
        and ``OSError`` if the file cannot be read -- the same failure modes
        as ``AppState.open``.
        """
        data = path.read_bytes()
        raw, fmt = load_raw(data, path.name)
        document = BPXDocument.from_raw(raw, filename=path.name, fmt=fmt)
        identity = document.identity
        error_count, warning_count = partitioned_counts(document)
        return cls(
            raw=raw,
            path=path,
            filename=path.name,
            model=identity.model or None,
            error_count=error_count,
            warning_count=warning_count,
            section_count=document.section_count,
            parameter_count=document.parameter_count,
            mtime=path.stat().st_mtime,
            bpx_version=identity.bpx_version or None,
            citation=identity.references,
            title=identity.title,
            description=identity.description,
            record=LoadRecord.capture(data, document, path=path),
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
        error_count, warning_count = partitioned_counts(document)
        return cls(
            raw=raw,
            path=None,
            filename=ref_set.short_title,
            model=identity.model or None,
            error_count=error_count,
            warning_count=warning_count,
            section_count=document.section_count,
            parameter_count=document.parameter_count,
            mtime=None,
            set_id=set_id,
            bpx_version=identity.bpx_version or None,
            citation=ref_set.references,
            title=identity.title,
            description=identity.description,
            # A bundled set has no source bytes and no disk facts; empty
            # source is honest here -- the document's fmt is "json", so the
            # comment fact is False by construction and everything else in
            # the record comes from the document itself.
            record=LoadRecord.capture(b"", document),
        )
