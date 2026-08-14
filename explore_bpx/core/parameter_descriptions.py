"""Technical parameter descriptions, loaded from a replaceable dataset file.

The dataset (``explore_bpx/data/parameter_descriptions.yaml``) is a transcription of
the Faraday Institution's *BPX Parameter technical descriptions* document. It
is deliberately a plain data file, not code: when the standard's documentation
is revised, replacing the file updates the app with no code change.

Structure of an entry::

    - sections: [Negative electrode, Positive electrode]
      alias: "Particle radius [m]"
      symbol: "R_{k,m}"                # LaTeX, rendered by the UI
      battinfo: "https://w3id.org/..." # ontology link, optional
      content:                         # ordered heading -> prose
        Description: ...
        Physical correspondence: ...

Keying is **section-scoped**, not alias-only: the same alias means different
things in different sections (``Thickness [m]`` has separate entries for the
electrodes and the separator; ``Conductivity [S.m-1]`` for the electrolyte and
the electrodes). An entry matches a parameter when the leaf alias equals the
entry's alias and any of the entry's section names appears in the parameter's
path -- which also covers blended-electrode particles, whose paths nest as
``.../Positive electrode/Particle/Primary/<alias>``.

``content`` is an *ordered mapping* rendered verbatim by the Documentation
tab, headings included. A future dataset revision can therefore add, remove or
rename headings freely -- the UI renders whatever the file provides.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "parameter_descriptions.yaml"


@dataclass(frozen=True)
class ParameterDescription:
    """One parameter's technical description, as authored in the dataset."""

    alias: str
    sections: tuple[str, ...]
    symbol: str | None = None  # LaTeX source, no surrounding $
    battinfo: str | None = None  # ontology URL
    content: tuple[tuple[str, str], ...] = ()  # ordered (heading, prose)
    source: str | None = None  # dataset provenance label


@dataclass(frozen=True)
class _Dataset:
    source: str | None
    entries: tuple[ParameterDescription, ...]


def lookup(path: tuple[str, ...]) -> ParameterDescription | None:
    """Return the description for the parameter at *path*, if one exists.

    Matches the leaf alias exactly, scoped by section membership anywhere in
    the path. A ``User-defined`` parameter that happens to reuse a standard
    alias does not match, because no standard section appears in its path.
    """
    if not path:
        return None
    alias = path[-1]
    ancestors = set(path[:-1])
    for entry in _load().entries:
        if entry.alias == alias and ancestors.intersection(entry.sections):
            return entry
    return None


def dataset_source() -> str | None:
    """Provenance label of the loaded dataset (``None`` when absent)."""
    return _load().source


@lru_cache(maxsize=1)
def _load() -> _Dataset:
    """Parse the dataset file once; an absent or empty file is not an error.

    The app must run without the dataset -- descriptions are documentation,
    not schema -- so a missing file yields an empty dataset rather than a
    crash. A *malformed* file, by contrast, raises: silently dropping every
    description would read as "this build lost the docs" with no cause shown.
    """
    if not _DATASET_PATH.exists():
        return _Dataset(source=None, entries=())
    raw = yaml.safe_load(_DATASET_PATH.read_text(encoding="utf-8"))
    if raw is None:
        return _Dataset(source=None, entries=())
    source = _compose_source(raw)
    entries = tuple(_parse_entry(item, source) for item in raw.get("entries", ()))
    return _Dataset(source=source, entries=entries)


def _compose_source(raw: dict) -> str | None:
    """Join the file's ``source`` and ``version`` into one provenance label."""
    parts = [str(raw[key]) for key in ("source", "version") if raw.get(key)]
    return ", ".join(parts) if parts else None


def _parse_entry(item: dict, source: str | None) -> ParameterDescription:
    content = item.get("content") or {}
    return ParameterDescription(
        alias=str(item["alias"]),
        sections=tuple(str(s) for s in item["sections"]),
        symbol=item.get("symbol") or None,
        battinfo=item.get("battinfo") or None,
        content=tuple((str(heading), str(text).strip()) for heading, text in content.items()),
        source=source,
    )
