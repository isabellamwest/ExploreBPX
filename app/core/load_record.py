"""The record of how a document actually came off its source (frontend-agnostic).

Transparency track Phase 3 (PLAN-transparency.md): the load-time facts a
person needs to trust what the app shows them -- the format the loader
actually used, whether the source is a legacy BPX v0.x object that ``bpx``
only judges after converting, how far checking reached on the loaded
content, whether the source text carries YAML comments a save would destroy
(decision D4), and what the file on disk looked like (decision D5).

Every fact is about the moment of loading, so a record never mutates with
edits -- the live answer to "how far has checking reached *now*" is
:attr:`core.document.BPXDocument.validation_reach`, re-derived on every
rebuild; :attr:`LoadRecord.checked` is that answer for the content as
loaded. Phase 4 puts these facts on screen (the file record's *Read as* /
*Checked* rows and the diagnostics stream's pinned **This file** group);
this module deliberately knows nothing about how they are shown.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from . import bpx_gateway
from .bpx_gateway import CheckReach
from .document import BPXDocument


def _yaml_has_comments(text: str) -> bool:
    """Whether YAML source *text* contains at least one comment.

    Judged with the yaml scanner rather than a hand-rolled quote/whitespace
    rule: the scanner emits tokens spanning every construct *except*
    comments (which it skips silently), so a ``#`` outside every token span
    is a comment marker, while a ``#`` inside a scalar
    (``https://doi.org/x#y``, ``"see # note"``, a block scalar's body) is
    covered by its token's span and correctly ignored. Only called for text
    that already parsed (a record is captured after a successful load), so
    scanning cannot fail.
    """
    spans = [
        (token.start_mark.index, token.end_mark.index)
        for token in yaml.scan(text, Loader=yaml.SafeLoader)
    ]
    position = text.find("#")
    while position != -1:
        if not any(start <= position < end for start, end in spans):
            return True
        position = text.find("#", position + 1)
    return False


@dataclass(frozen=True)
class LoadRecord:
    """The facts about one load of a document, captured at that moment."""

    #: The format the loader actually read, ``"json"`` or ``"yaml"`` --
    #: carried from the load's own decision
    #: (:func:`core.bpx_gateway.format_for_filename`), never re-derived
    #: (transparency track finding 5).
    fmt: str
    #: True when the source is detectably a legacy BPX v0.x object, which
    #: ``bpx`` judges only after converting a copy (finding 1) -- the fact
    #: decision D3's open prompt is built on.
    is_legacy: bool
    #: How far ``bpx``'s staged checking reached on the content as loaded
    #: (finding 4). The live per-edit answer is the document's own
    #: ``validation_reach``; this is the load-time snapshot.
    checked: CheckReach
    #: True when the YAML source text contains at least one comment, which
    #: a save through ``yaml.safe_dump`` would silently destroy (finding 2,
    #: decision D4). Always False for JSON, which has no comments.
    has_yaml_comments: bool
    #: Disk facts at load time (decision D5), for the file record and the
    #: stale-on-disk check. ``None`` when no file backs the content.
    size_bytes: int | None = None
    mtime: float | None = None

    @classmethod
    def capture(
        cls,
        data: bytes | str,
        document: BPXDocument,
        path: Path | None = None,
    ) -> "LoadRecord":
        """Capture the record for *document*, freshly loaded from *data*.

        *data* is the source content the document was built from (the
        YAML-comment fact needs the original text; the parsed dict cannot
        answer it) and *path* the backing file, if any -- ``stat``-ed here,
        as close to the read as the caller allows. Every other fact is taken
        from *document* itself -- its recorded format, its raw dict, its
        reach -- never re-derived from the filename or re-validated, so the
        record states what the load did rather than what a second look
        would do. Raises ``OSError`` if *path* cannot be ``stat``-ed, the
        same contract as reading it.
        """
        size_bytes = mtime = None
        if path is not None:
            stat = path.stat()
            size_bytes, mtime = stat.st_size, stat.st_mtime
        return cls(
            fmt=document.fmt,
            is_legacy=bpx_gateway.is_legacy(document.raw),
            checked=document.validation_reach,
            has_yaml_comments=(
                document.fmt == "yaml"
                and _yaml_has_comments(bpx_gateway.decode_source(data))
            ),
            size_bytes=size_bytes,
            mtime=mtime,
        )
