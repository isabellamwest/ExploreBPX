"""Reference Validation runs: bundled sample cells + user-chosen BPX files.

An anti-corruption adapter in the same spirit as :mod:`core.bpx_gateway`: it
knows where bundled sample bytes live on disk, hands any bytes (bundled or a
user-picked file) to the existing JSON/YAML-decoding path, and never invents
its own parsing. Only the ``Validation`` section is ever exposed -- the rest
of a reference document is not this feature's business, so it is never
surfaced or judged here (see ``app/data/example_documents/about_energy/
NOTICE.md`` for the bundled files' provenance and licence).

The bundled source is About:Energy's public parameterisations (an NMC pouch
cell and an LFP 18650 cell), whose Validation runs were rebuilt from their
full-resolution validation datasets by ``scripts/build_example_library.py``.
A future second source is another entry in ``_SOURCES`` pointing at its own
directory -- nothing else here changes.
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
    _Source("about_energy", "Sample data", _ASSETS / "about_energy"),
)

#: One honest sentence of provenance for the bundled samples, shown wherever
#: they are offered (mirrors ``core.reference_library.PROVENANCE`` for the
#: pinnable parameter sets). The facts restate ``about_energy/NOTICE.md``:
#: source, licence, and the one modification that matters to a reader of the
#: preview (runs rebuilt from the upstream validation data, downsampled).
PROVENANCE = (
    "Sample runs from About:Energy's public BPX parameterisations "
    "(aboutenergy.io), CC BY-SA 4.0. Validation runs rebuilt from their "
    "full-resolution validation data, downsampled to at most 1000 points; "
    "parameter values unmodified."
)

#: A short, curated picker label per bundled document stem -- the files'
#: own ``Header.Title`` values are full sentences ("Parameterisation example
#: of an NMC111|graphite 12.5 Ah pouch cell"), fine for a document but too
#: long to read as a list heading. This is presentation metadata for our own
#: hand-picked catalog, not a restatement of anything ``bpx`` produces, so it
#: lives here rather than being derived from spec data. Falls back to the
#: full title for a future bundled file this hasn't been curated for yet.
_SHORT_TITLES: dict[str, str] = {
    "nmc_pouch_cell": "NMC pouch cell",
    "lfp_18650_cell": "LFP 18650 cell",
}

#: Curated picker order for the bundled documents (the NMC pouch cell is the
#: flagship sample) -- an uncurated future file sorts after these,
#: alphabetically.
_STEM_ORDER: tuple[str, ...] = ("nmc_pouch_cell", "lfp_18650_cell")


def _stem_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    return (
        _STEM_ORDER.index(stem) if stem in _STEM_ORDER else len(_STEM_ORDER),
        stem,
    )


@dataclass(frozen=True)
class ExampleRun:
    """One addable Validation run from a reference document (bundled sample
    or user-chosen file)."""

    id: str  # "about_energy/nmc_pouch_cell::C/20 discharge", "file:1::1C"
    document_id: str  # "about_energy/nmc_pouch_cell", or the caller's file id
    document_title: str  # the file's own Header.Title
    short_title: str  # a curated, list-heading-length label -- see ``_SHORT_TITLES``
    model: str  # the file's own Header.Model, e.g. "DFN" or "SPM"
    run_name: str  # "C/20 discharge"
    point_count: int
    has_temperature: bool


@dataclass(frozen=True)
class ReferenceDocument:
    """The Validation slice of one user-chosen BPX file (see
    :func:`load_reference_document`): picker metadata plus each run's raw
    array dict, held directly since a user file -- unlike a bundled sample --
    has no stable on-disk identity to re-read from later."""

    label: str  # picker group heading: the filename stem
    title: str  # the file's own Header.Title, or the filename
    model: str
    runs: tuple[ExampleRun, ...]
    data: dict[str, dict]  # run_name -> raw array dict


def _runs_from_raw(
    raw: dict, document_id: str, title: str, short_title: str
) -> tuple[ExampleRun, ...]:
    """Every Validation run in *raw*, as picker metadata. Reads the raw dict
    exactly as the tree does -- a missing/odd ``Validation`` value degrades
    to no runs, never an error (the validator, not this module, judges it)."""
    header = raw.get("Header") if isinstance(raw.get("Header"), dict) else {}
    validation = raw.get("Validation") if isinstance(raw.get("Validation"), dict) else {}
    runs: list[ExampleRun] = []
    for run_name, run in validation.items():
        if not isinstance(run, dict):
            continue
        runs.append(
            ExampleRun(
                id=f"{document_id}::{run_name}",
                document_id=document_id,
                document_title=title,
                short_title=short_title,
                model=str(header.get("Model") or ""),
                run_name=str(run_name),
                point_count=len(run.get("Time [s]") or []),
                has_temperature="Temperature [K]" in run,
            )
        )
    return tuple(runs)


@lru_cache(maxsize=None)
def _load_document_raw(source_id: str, stem: str) -> dict:
    source = next(s for s in _SOURCES if s.id == source_id)
    path = source.directory / f"{stem}.json"
    raw, _fmt = bpx_gateway.load_raw(path.read_bytes(), path.name)
    return raw


def list_example_runs() -> tuple[ExampleRun, ...]:
    """Every addable run across every bundled sample document."""
    runs: list[ExampleRun] = []
    for source in _SOURCES:
        for path in sorted(source.directory.glob("*.json"), key=_stem_sort_key):
            stem = path.stem
            raw = _load_document_raw(source.id, stem)
            header = raw.get("Header") or {}
            title = str(header.get("Title") or stem)
            runs.extend(
                _runs_from_raw(
                    raw,
                    document_id=f"{source.id}/{stem}",
                    title=title,
                    short_title=_SHORT_TITLES.get(stem, title),
                )
            )
    return tuple(runs)


def load_example_run(run_id: str) -> dict[str, list]:
    """The raw array dict (``"Time [s]"`` etc.) for one bundled
    :class:`ExampleRun` id.

    Same shape as a normal document's ``raw["Validation"][run_name]`` -- the
    caller reads it exactly as it would its own run.
    """
    document_id, run_name = run_id.split("::", 1)
    source_id, stem = document_id.split("/", 1)
    raw = _load_document_raw(source_id, stem)
    return raw["Validation"][run_name]


def load_reference_document(
    data: bytes, filename: str, document_id: str
) -> ReferenceDocument:
    """The Validation slice of a user-chosen BPX file.

    *document_id* is the caller's own unique handle for this open (e.g.
    ``"file:3"``) -- baked into each run's ``ExampleRun.id`` so the same
    file opened twice never collides. Decoding failures propagate as
    :class:`bpx_gateway.LoadError` verbatim; a file with no ``Validation``
    section simply yields zero runs (the caller decides how to say so).
    """
    raw, _fmt = bpx_gateway.load_raw(data, filename)
    header = raw.get("Header") if isinstance(raw.get("Header"), dict) else {}
    stem = Path(filename).stem
    title = str(header.get("Title") or filename)
    runs = _runs_from_raw(raw, document_id=document_id, title=title, short_title=stem)
    validation = raw.get("Validation") if isinstance(raw.get("Validation"), dict) else {}
    return ReferenceDocument(
        label=stem,
        title=title,
        model=str(header.get("Model") or ""),
        runs=runs,
        data={run.run_name: validation[run.run_name] for run in runs},
    )
