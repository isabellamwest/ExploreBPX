"""Parameter type classification (frontend-agnostic).

BPX parameters fall into a small set of *kinds* regardless of which battery
section they appear in. Classifying by kind (rather than by section) lets the
UI reuse one renderer per kind.

Classification is **declared-type first**: when schema metadata is available
the declared field type is authoritative and the current stored value's runtime
type is irrelevant.  This ensures that an invalid stored value (e.g. a string
committed to a float field) never causes the application to switch to a
different editor or become read-only.  Value shape is only used for:

* Structural kinds (``dict``/``list``) whose topology is always shape-driven.
* ``allows_function`` fields, where a numeric value and a function-expression
  string are both *valid* stored types and value shape selects the editor.
* Parameters with no schema metadata (genuinely unknown aliases read from
  external files).
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

    ``meta`` is the schema metadata for the value's alias, if known.  When
    metadata is available the *declared* field type is authoritative; the
    current stored value's runtime type does not affect the result (except for
    ``allows_function`` fields, where both a number and a function-expression
    string are valid and the stored value type selects the editor).
    """
    # --- Structural kinds are always shape-driven. -------------------------
    # Dicts and lists define document topology, not parameter values, so they
    # are classified by shape regardless of any schema declaration.
    if isinstance(value, dict):
        return ParameterKind.TABLE if looks_like_table(value) else ParameterKind.SECTION
    if isinstance(value, list):
        # Experiment arrays (Validation section) are tabular data.
        return ParameterKind.TABLE

    # --- Metadata-authoritative path. -------------------------------------
    # When the schema declares a field type, that declaration is the source of
    # truth for editor selection.  An invalid stored value (e.g. a string in a
    # float field) must not cause the editor to switch or become read-only.
    if meta is not None:
        if meta.is_enum:
            return ParameterKind.ENUM
        if meta.is_integer:
            return ParameterKind.INTEGER
        if meta.is_text:
            return ParameterKind.SCALAR
        if meta.allows_function:
            # This field legitimately stores EITHER a constant numeric value OR
            # a function/table expression string.  Both are valid, so we use
            # the stored value's shape to pick the editor.
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                return ParameterKind.SCALAR
            return ParameterKind.FUNCTION
        # Remaining known fields are plain numerics (float): no enum, no
        # integer flag, no text flag, no function alternative.  Always scalar.
        return ParameterKind.SCALAR

    # --- No-metadata fallback. --------------------------------------------
    # Only reached for parameters whose alias does not appear in the schema
    # index — i.e. parameters read from external files that Explore_BPX did
    # not author.  Value shape is the only information available.
    if isinstance(value, bool):
        return ParameterKind.SCALAR
    if isinstance(value, (int, float)):
        return ParameterKind.SCALAR
    if isinstance(value, str):
        # BPX treats unknown string values as function expressions.
        return ParameterKind.FUNCTION
    return ParameterKind.UNKNOWN
