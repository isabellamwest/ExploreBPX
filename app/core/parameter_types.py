"""Parameter type classification (frontend-agnostic).

BPX parameters fall into a small set of *kinds* regardless of which battery
section they appear in. Classifying by kind (rather than by section) lets the
UI reuse one renderer per kind.

Classification is **declared-type first, universally**: when schema metadata
is available the declared field type alone fixes the kind, and the stored
value's runtime type never changes the result. This ensures that an invalid
stored value (e.g. a string committed to a float field) never causes the
application to switch to a different editor or become read-only.

A field the schema declares as a *union* of representations
(``FloatFunctionTable``, ``FloatInt | dict[str, FloatInt]``) is one kind, not
several: the kind identifies the declared union (``FUNCTION``, ``MAP``), and
the stored value's shape is a card-level concern (which mode/representation
to render), never a classification concern. The earlier exception -- where a
numeric value in an ``allows_function`` field classified as ``SCALAR`` -- is
removed: it made the field's other legal representations unreachable from the
UI.

Kind is declared; mode is chosen. Value shape classifies in exactly one place:
when ``meta`` is ``None``, i.e. metadata is genuinely absent. This is a valid,
first-class state with two legitimate sources: genuinely unknown aliases read
from external files, and user-authored custom parameters (an ordinary
raw-dict entry whose metadata is absent because nothing is synthesised or
persisted for it). The BPX validator remains the source of truth for whether
such a parameter is legal. Only in this fallback does an undeclared dict/list's
topology classify it (``TABLE``/``SECTION``/``SERIES``), because no schema
field describes it.
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
    TEXT = "text"
    BOOLEAN = "boolean"
    ENUM = "enum"
    FUNCTION = "function"
    MAP = "map"
    SERIES = "series"
    TABLE = "table"
    UNKNOWN = "unknown"


_ICONS = {
    ParameterKind.SECTION: "📁",
    ParameterKind.SCALAR: "🔢",
    ParameterKind.INTEGER: "#️⃣",
    ParameterKind.TEXT: "📝",
    ParameterKind.BOOLEAN: "☑️",
    ParameterKind.ENUM: "🔽",
    ParameterKind.FUNCTION: "📈",
    ParameterKind.MAP: "🗂️",
    ParameterKind.SERIES: "📶",
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

    ``meta`` is the schema metadata for the value's alias, if known. When
    metadata is available the *declared* field type alone fixes the kind; the
    stored value's runtime type never changes the result -- not even for
    union-typed fields (``allows_function``/``allows_map``), whose stored
    value's shape only picks a card-level *mode*, not the kind. Value shape
    classifies only when ``meta`` is genuinely absent (see the module
    docstring).
    """
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
            return ParameterKind.TEXT
        if meta.is_series:
            return ParameterKind.SERIES
        if meta.allows_map:
            return ParameterKind.MAP
        if meta.allows_function:
            # The declared union (number | function-expression | table) is one
            # kind; the stored value's shape only selects the card's initial
            # mode, never the kind itself.
            return ParameterKind.FUNCTION
        # Remaining known fields are plain numerics (float): no enum, no
        # integer/text/series/map/function flag.  Always scalar.
        return ParameterKind.SCALAR

    # --- No-metadata fallback. --------------------------------------------
    # Only reached for parameters whose alias does not appear in the schema
    # index. Two legitimate sources: parameters read from external files that
    # Explore_BPX did not author, and user-authored custom parameters, whose
    # metadata is genuinely absent by design (nothing is synthesised or
    # persisted for them). Value shape is the only information available, and
    # this is the one place an undeclared dict/list's topology classifies it.
    if isinstance(value, bool):
        # Checked before int/float: bool is a subclass of int in Python.
        return ParameterKind.BOOLEAN
    if isinstance(value, (int, float)):
        return ParameterKind.SCALAR
    if isinstance(value, str):
        return ParameterKind.TEXT
    if isinstance(value, dict):
        return ParameterKind.TABLE if looks_like_table(value) else ParameterKind.SECTION
    if isinstance(value, list):
        return ParameterKind.SERIES
    return ParameterKind.UNKNOWN
