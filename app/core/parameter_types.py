"""Parameter type classification (frontend-agnostic).

BPX parameters fall into a small set of *kinds* regardless of which battery
section they appear in. Classifying by kind (rather than by section) lets the
UI reuse one renderer per kind. Classification is value-shape first, with
schema metadata used to refine ambiguous cases (e.g. a string that is a
``Function`` vs. plain header text).
"""

from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .bpx_gateway import FieldMeta

_UNIT_RE = re.compile(r"\[([^\]]+)\]\s*$")


class ParameterKind(str, Enum):
    """The kind of a BPX node, used to choose a UI renderer."""

    SECTION = "section"
    SCALAR = "scalar"
    INTEGER = "integer"
    ENUM = "enum"
    FUNCTION = "function"
    TABLE = "table"
    UNKNOWN = "unknown"


_ICONS = {
    ParameterKind.SECTION: "📁",
    ParameterKind.SCALAR: "🔢",
    ParameterKind.INTEGER: "#️⃣",
    ParameterKind.ENUM: "🔽",
    ParameterKind.FUNCTION: "📈",
    ParameterKind.TABLE: "📊",
    ParameterKind.UNKNOWN: "❔",
}


def icon_for(kind: ParameterKind) -> str:
    return _ICONS.get(kind, "❔")


def extract_unit(label: str) -> str:
    """Return the unit embedded in an alias, e.g. ``"... [K]"`` -> ``"K"``."""
    match = _UNIT_RE.search(label or "")
    return match.group(1) if match else ""


def looks_like_table(value: object) -> bool:
    """True if ``value`` is an interpolated table (``{"x": [...], "y": [...]}``)."""
    return (
        isinstance(value, dict)
        and "x" in value
        and "y" in value
        and isinstance(value.get("x"), list)
        and isinstance(value.get("y"), list)
    )


def classify(value: object, meta: "FieldMeta | None" = None) -> ParameterKind:
    """Classify a BPX value into a :class:`ParameterKind`.

    ``meta`` is the schema metadata for the value's alias, if known.
    """
    if meta is not None and meta.is_enum:
        return ParameterKind.ENUM

    if isinstance(value, dict):
        return ParameterKind.TABLE if looks_like_table(value) else ParameterKind.SECTION

    if isinstance(value, str):
        if meta is not None and meta.is_text and not meta.allows_function:
            return ParameterKind.SCALAR
        # Known function field, or unknown alias (User-defined strings are
        # treated as functions by BPX).
        return ParameterKind.FUNCTION

    if isinstance(value, bool):
        return ParameterKind.SCALAR

    if isinstance(value, (int, float)):
        if meta is not None and meta.is_integer:
            return ParameterKind.INTEGER
        return ParameterKind.SCALAR

    if isinstance(value, list):
        # Experiment arrays (Validation section) are tabular data.
        return ParameterKind.TABLE

    return ParameterKind.UNKNOWN
