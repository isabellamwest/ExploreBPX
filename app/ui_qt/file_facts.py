"""The diagnostics stream's file-facts group (transparency track Phase 4,
S1): the structural load-time facts a person needs before trusting the
diagnostics beneath -- a legacy v0.x conversion, an aborted checking run, or
YAML comments a save would destroy.

Every underlying fact already lives on ``core.load_record.LoadRecord`` and
``core.document.BPXDocument.validation_reach`` (Phase 3) -- this module only
chooses the diagnostics stream's own words for them, exactly as
``ui_qt.workspace_panel``'s own record rows already do for the Workspace
surface. Pure and Qt-free so :mod:`ui_qt.diagnostics_panel` and its tests can
import it without touching a widget.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.bpx_gateway import BPX_VERSION, CheckReach
from core.load_record import LoadRecord


@dataclass(frozen=True)
class FileFact:
    """One file-facts row's two-line content: a bold headline, a muted
    detail sentence underneath."""

    headline: str
    sub: str


def file_facts(
    filename: str,
    record: LoadRecord | None,
    reach: CheckReach,
    bpx_version: str,
) -> tuple[FileFact, ...]:
    """The file-facts group's rows for one document, in the signed order
    (legacy, checking reach, YAML comments) -- empty for the everyday clean
    file, which is why the group itself renders nothing (S1).

    *filename* is the display name the row copy names directly -- never
    "This file" (banned everywhere, labels and prose alike). *record* is the
    session's ``LoadRecord`` (``None`` for a New scaffold, which has no load
    to record). *reach* is always the document's *live* ``validation_reach``
    -- checked even with *record* ``None``, so a fresh scaffold (which
    ``bpx`` aborts at Parameterisation) still shows the reach fact; only the
    legacy/comments facts require a real load. *bpx_version* is the file's
    own declared ``Header.BPX`` (``document.identity.bpx_version``), used
    only in the legacy sub-line -- the installed ``bpx``'s own version,
    named in the legacy headline, is :data:`core.bpx_gateway.BPX_VERSION`
    and needs no caller input.
    """
    facts: list[FileFact] = []

    if record is not None and record.is_legacy:
        version = f"BPX {bpx_version}" if bpx_version else "a BPX 0.x file"
        facts.append(
            FileFact(
                f"Checked as a BPX {BPX_VERSION} conversion",
                f"{filename} is {version} \u00b7 the editor shows the file as it is on disk",
            )
        )

    if reach is CheckReach.HEADER:
        facts.append(FileFact("Checking stopped at Header", "Nothing below it was checked"))
    elif reach is CheckReach.PARAMETERISATION:
        facts.append(
            FileFact("Checking stopped at Parameterisation", "State and Validation were not checked")
        )
    elif reach is CheckReach.NOT_RUN:
        facts.append(FileFact("Checking did not run", "bpx stopped before judging anything"))
    # CheckReach.COMPLETE: no fact -- checking ran the whole way, there is
    # nothing here to say.

    if record is not None and record.has_yaml_comments:
        facts.append(FileFact("Comments will not survive saving", "Saving rewrites the whole file"))

    return tuple(facts)
