"""Bundled reference BPX documents, sliced to their Validation runs.

An anti-corruption adapter in the same spirit as :mod:`core.bpx_gateway`: it
knows where bundled example bytes live on disk and hands them to the existing
JSON-decoding path, never inventing its own parsing. Only the ``Validation``
section is exposed -- see ``app/data/example_documents/bpx_official/NOTICE.md``
for why the rest of these documents is never surfaced (both bundled files fail
whole-document validation under the current ``bpx`` package; this module does
not touch, hide, or fix that, it simply never asks the question).

A second source (e.g. a future PyBaMM-derived literature library) is another
entry in ``_SOURCES`` pointing at its own directory -- nothing else here
changes.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import bpx_gateway

_ASSETS = Path(__file__).resolve().parent.parent / "data" / "example_documents"


@dataclass(frozen=True)
class _Source:
    id: str
    label: str
    directory: Path


_SOURCES: tuple[_Source, ...] = (
    _Source("bpx_official", "Official BPX examples", _ASSETS / "bpx_official"),
)

#: A short, curated picker label per bundled document stem -- the files'
#: own ``Header.Title`` values are full sentences ("Parameterisation example
#: of an NMC111|graphite 12.5 Ah pouch cell"), fine for a document but too
#: long to read as a list heading. This is presentation metadata for our own
#: hand-picked catalog, not a restatement of anything ``bpx`` produces, so it
#: lives here rather than being derived from spec data. Falls back to the
#: full title for a future bundled file this hasn't been curated for yet.
_SHORT_TITLES: dict[str, str] = {
    "nmc_pouch_cell_BPX": "NMC pouch cell",
    "nmc_pouch_cell_BPX_SPM": "NMC pouch cell (SPM)",
}


@dataclass(frozen=True)
class ExampleRun:
    """One addable Validation run from a bundled example document."""

    id: str  # "bpx_official/nmc_pouch_cell_BPX::C/20 discharge"
    document_id: str  # "bpx_official/nmc_pouch_cell_BPX"
    document_title: str  # the file's own Header.Title
    short_title: str  # a curated, list-heading-length label -- see ``_SHORT_TITLES``
    model: str  # the file's own Header.Model, e.g. "DFN" or "SPM"
    run_name: str  # "C/20 discharge"
    point_count: int
    has_temperature: bool


@lru_cache(maxsize=None)
def _load_document_raw(source_id: str, stem: str) -> dict:
    source = next(s for s in _SOURCES if s.id == source_id)
    path = source.directory / f"{stem}.json"
    raw, _fmt = bpx_gateway.load_raw(path.read_bytes(), path.name)
    return raw


def list_example_runs() -> tuple[ExampleRun, ...]:
    """Every addable run across every bundled example document."""
    runs: list[ExampleRun] = []
    for source in _SOURCES:
        for path in sorted(source.directory.glob("*.json")):
            stem = path.stem
            document_id = f"{source.id}/{stem}"
            raw = _load_document_raw(source.id, stem)
            header = raw.get("Header") or {}
            validation = raw.get("Validation") or {}
            for run_name, run in validation.items():
                runs.append(
                    ExampleRun(
                        id=f"{document_id}::{run_name}",
                        document_id=document_id,
                        document_title=str(header.get("Title") or stem),
                        short_title=_SHORT_TITLES.get(stem, str(header.get("Title") or stem)),
                        model=str(header.get("Model") or ""),
                        run_name=run_name,
                        point_count=len(run.get("Time [s]") or []),
                        has_temperature="Temperature [K]" in run,
                    )
                )
    return tuple(runs)


def load_example_run(run_id: str) -> dict[str, list]:
    """The raw array dict (``"Time [s]"`` etc.) for one :class:`ExampleRun` id.

    Same shape as a normal document's ``raw["Validation"][run_name]`` -- the
    caller reads it exactly as it would its own run.
    """
    document_id, run_name = run_id.split("::", 1)
    source_id, stem = document_id.split("/", 1)
    raw = _load_document_raw(source_id, stem)
    return raw["Validation"][run_name]
