"""Unified parameter-metadata provider (frontend-agnostic, Qt-free).

Combines the authoritative, schema-derived :class:`~core.bpx_gateway.FieldMeta`
with an explicit, currently empty educational-metadata seam. This module
invents no scientific or physical content: three of the eight
``ParameterMetadata`` categories (physical meaning, units, accepted types) are
derived from ``FieldMeta``; the remaining five (functional dependence, model
availability, measurement methods, specification links, symbols) are wired to
:func:`educational_metadata`, which returns ``None`` until a real educational
dataset exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from .bpx_gateway import FieldMeta
from .parameter_types import extract_unit


@dataclass(frozen=True)
class ParameterMetadata:
    """Rich parameter documentation, one optional field per AC category.

    Every field is optional. Consumers (the info popover) render only the
    populated fields; an unpopulated category is simply absent.
    """

    physical_meaning: str | None = None
    units: str | None = None
    accepted_types: str | None = None
    functional_dependence: str | None = None
    model_availability: str | None = None
    measurement_methods: str | None = None
    specification_links: str | None = None
    symbols: str | None = None


def educational_metadata(alias: str) -> ParameterMetadata | None:
    """Explicit seam for a future educational-metadata source.

    No educational dataset exists yet, so this always returns ``None``. This
    is the one function a future educational source needs to change;
    :func:`resolve_parameter_metadata` already merges whatever it returns.
    """
    return None


def resolve_parameter_metadata(alias: str, meta: FieldMeta | None) -> ParameterMetadata:
    """Resolve the unified metadata for *alias* from ``FieldMeta`` alone.

    ``physical_meaning``, ``units`` and ``accepted_types`` come from *meta*;
    the remaining five categories come from :func:`educational_metadata`,
    which is empty today.
    """
    educational = educational_metadata(alias)
    return ParameterMetadata(
        physical_meaning=meta.description if meta and meta.description else None,
        units=extract_unit(alias) or None,
        accepted_types=_accepted_types(meta),
        functional_dependence=educational.functional_dependence if educational else None,
        model_availability=educational.model_availability if educational else None,
        measurement_methods=educational.measurement_methods if educational else None,
        specification_links=educational.specification_links if educational else None,
        symbols=educational.symbols if educational else None,
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
