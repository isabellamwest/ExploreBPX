"""Unified parameter-metadata provider (frontend-agnostic, Qt-free).

Combines the authoritative, schema-derived :class:`~core.bpx_gateway.FieldMeta`
with the technical-descriptions dataset (:mod:`core.parameter_descriptions`,
transcribed from the Faraday Institution's *BPX Parameter technical
descriptions* document). This module invents no scientific content: the quick
facts (physical meaning, units, accepted types) derive from ``FieldMeta``;
the symbol, ontology link and long-form documentation come verbatim from the
dataset file.

Resolution is keyed by the parameter's *path*, not its alias alone: the same
alias carries different descriptions in different sections (``Thickness [m]``
under an electrode vs the separator), and only the path can tell them apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import parameter_descriptions
from .bpx_gateway import FieldMeta
from .parameter_types import extract_unit


@dataclass(frozen=True)
class ParameterMetadata:
    """Rich parameter documentation for the Inspector's info surfaces.

    Every field is optional; consumers render only what is populated.
    ``physical_meaning``, ``units`` and ``accepted_types`` are the quick-glance
    facts (the ( i ) popover). ``symbol`` is LaTeX source. ``documentation`` is
    the ordered (heading, prose) sections for the Documentation tab, rendered
    verbatim in dataset order so the dataset file controls its own structure.
    """

    physical_meaning: str | None = None
    units: str | None = None
    accepted_types: str | None = None
    symbol: str | None = None
    specification_link: str | None = None
    documentation: tuple[tuple[str, str], ...] = ()
    source: str | None = None
    #: True for a parameter the BPX standard does not define -- one with
    #: neither schema ``FieldMeta`` nor a technical-descriptions entry (a
    #: user-authored custom parameter, e.g. inside ``User-defined``). Lets the
    #: info surfaces label it "custom" instead of showing an empty glance.
    is_custom: bool = False


def resolve_parameter_metadata(
    path: tuple[str, ...], meta: FieldMeta | None
) -> ParameterMetadata:
    """Resolve the unified metadata for the parameter at *path*.

    ``FieldMeta`` supplies the schema-derived facts; the descriptions dataset
    supplies symbol, link and documentation. Either source may be absent -
    a user-defined parameter has neither, and yields an all-empty result.
    """
    alias = path[-1] if path else ""
    description = parameter_descriptions.lookup(tuple(path))
    return ParameterMetadata(
        physical_meaning=meta.description if meta and meta.description else None,
        units=extract_unit(alias) or None,
        accepted_types=_accepted_types(meta),
        symbol=description.symbol if description else None,
        specification_link=description.battinfo if description else None,
        documentation=description.content if description else (),
        source=description.source if description else None,
        is_custom=meta is None and description is None,
    )


def _accepted_types(meta: FieldMeta | None) -> str | None:
    """Describe the field's declared kind, from ``FieldMeta``'s own flags."""
    if meta is None:
        return None
    types: list[str] = []
    if meta.is_enum:
        values = ", ".join(meta.enum_values)
        types.append(f"one of: {values}" if values else "enumerated value")
    if meta.is_integer:
        types.append("integer")
    if meta.is_text:
        types.append("text")
    if meta.allows_function:
        types.append("number, function or table")
    return "; ".join(types) if types else None
