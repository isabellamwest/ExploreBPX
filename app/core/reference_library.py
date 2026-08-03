"""Bundled reference documents: PyBaMM-derived BPX parameter sets.

An anti-corruption adapter in the same spirit as :mod:`core.example_library`,
but for a different capability: where the example library exposes only the
``Validation`` runs of bundled sample cells (addable to a run-comparison),
this module exposes *whole documents* -- well-known published parameter sets
a user can pull up as a read-only reference for Parameterisation comparison
and plotting. The two stay separate because a PyBaMM-derived set carries no
``Validation`` section at all (PyBaMM parameter sets hold no cycling data),
so it has nothing to offer the run-comparison dialog; see
``docs/future.md``'s "Bundled PyBaMM parameter sets" entry for the
accepted constraints.

The bundled files are generated offline by
``scripts/generate_reference_library.py`` (the application never imports
PyBaMM) and validated against the same ``bpx`` version the app pins; see
``app/data/example_documents/pybamm/NOTICE.md`` for provenance, licence and
the conversion caveats each file's own Description restates.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from . import bpx_gateway

_ASSETS = Path(__file__).resolve().parent.parent / "data" / "example_documents" / "pybamm"

#: A short, curated picker label per bundled document stem (the files' own
#: ``Header.Title`` values are full sentences). Presentation metadata for our
#: own catalog, same convention as ``example_library._SHORT_TITLES``; an
#: uncurated future file falls back to its full title.
_SHORT_TITLES: dict[str, str] = {
    "chen2020": "Chen2020 (LG M50 21700)",
    "prada2013": "Prada2013 (A123 26650 LFP)",
    "ai2020": "Ai2020 (Enertech pouch)",
    "mohtat2020": "Mohtat2020 (NMC532 pouch)",
}

#: Curated picker order -- Chen2020 is the flagship reference (the most
#: widely used set); an uncurated future file sorts after these,
#: alphabetically.
_STEM_ORDER: tuple[str, ...] = ("chen2020", "prada2013", "ai2020", "mohtat2020")

#: Origin and licence of the bundled library, stated wherever a set is
#: offered. ``NOTICE.md`` is the full record, but it ships as a repo file a
#: packaged user cannot open, so the two facts it alone carried -- that these
#: are derived artifacts, and whose licence they arrive under -- are said in
#: the app instead. Lives here rather than in the dialog because it is
#: provenance, not presentation; the conversion caveats and the PyBaMM
#: version stay in each file's own ``Header.Description``.
PROVENANCE = (
    "Derived offline from PyBaMM's published parameter sets. PyBaMM is "
    "BSD 3-Clause licensed; the parameter values originate in the cited "
    "publication."
)


def _stem_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem
    return (
        _STEM_ORDER.index(stem) if stem in _STEM_ORDER else len(_STEM_ORDER),
        stem,
    )


@dataclass(frozen=True)
class ReferenceSet:
    """Picker metadata for one bundled reference document."""

    id: str  # "pybamm/chen2020"
    title: str  # the file's own Header.Title
    short_title: str  # curated, list-heading-length -- see ``_SHORT_TITLES``
    model: str  # the file's own Header.Model, e.g. "DFN"
    description: str  # the file's own Header.Description (conversion caveats)
    references: str  # the file's own Header.References (the citation; "" if absent)


@lru_cache(maxsize=None)
def _load_raw(stem: str) -> dict:
    path = _ASSETS / f"{stem}.json"
    raw, _fmt = bpx_gateway.load_raw(path.read_bytes(), path.name)
    return raw


def list_reference_sets() -> tuple[ReferenceSet, ...]:
    """Every bundled reference document, in curated order."""
    sets: list[ReferenceSet] = []
    for path in sorted(_ASSETS.glob("*.json"), key=_stem_sort_key):
        raw = _load_raw(path.stem)
        header = raw.get("Header") if isinstance(raw.get("Header"), dict) else {}
        title = str(header.get("Title") or path.stem)
        sets.append(
            ReferenceSet(
                id=f"pybamm/{path.stem}",
                title=title,
                short_title=_SHORT_TITLES.get(path.stem, title),
                model=str(header.get("Model") or ""),
                description=str(header.get("Description") or ""),
                references=str(header.get("References") or ""),
            )
        )
    return tuple(sets)


def load_reference_raw(set_id: str) -> dict:
    """The raw BPX dict of one :class:`ReferenceSet` id.

    Returned as a deep copy: the cached original must stay pristine no matter
    what a consumer (a future comparison, a document rebuild) does with the
    result. Raises ``KeyError`` for an unknown id.
    """
    source, _, stem = set_id.partition("/")
    if source != "pybamm" or not (_ASSETS / f"{stem}.json").is_file():
        raise KeyError(f"Unknown reference set id: {set_id!r}")
    return copy.deepcopy(_load_raw(stem))
