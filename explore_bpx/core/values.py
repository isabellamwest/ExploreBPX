"""The app's lenient text <-> raw-value convention, in one place.

Every free-text editing surface in the app shares one rule: text that parses as
a plain number becomes an ``int`` or ``float``; anything else is passed through
as the raw string; empty text is the honest "no value", ``None``.

That rule is deliberately lenient. A card never decides whether a value is
*legal* -- it hands raw input to the same commit path every other card uses and
the BPX validator remains the source of truth. Parsing numbers rather than
storing every field as a string is what lets a committed value reclassify into
its proper editor on the next document rebuild.

``ScalarCard``, ``FunctionCard`` and ``RawCard`` each carried a byte-identical
copy of this pair; ``NumericGrid`` needs it per cell. Keeping one copy is what
stops the grid quietly disagreeing with the line editors about what ``5`` means.

``values_equal`` lives here for the same reason: deciding *when two raw values
are the same* is part of that convention, and both a card's dirty check and a
grid cell's no-op check must answer it identically.
"""

from __future__ import annotations

import math


def format_value(value: object) -> str:
    """Render a raw value for display in a text input or grid cell."""
    return "" if value is None else str(value)


def parse_value(text: str) -> object:
    """Parse typed *text* into a raw value: ``int``, ``float``, ``str`` or ``None``.

    Empty (or whitespace-only) text is ``None`` -- the same honest "no value"
    that ``AddParameter`` writes -- never ``0`` and never ``""``.

    An integral number keeps its ``int`` type unless the text itself carries a
    decimal point, so typing ``5`` over a stored ``5`` is a no-op while typing
    ``5.0`` is a real, type-changing edit (see :func:`values_equal`).

    Unparseable text is returned verbatim, not rejected: it may be a function
    expression, or simply wrong, and either way the validator judges it.
    """
    stripped = text.strip()
    if not stripped:
        return None
    try:
        number = float(stripped)
    except ValueError:
        return stripped
    return int(number) if number.is_integer() and "." not in stripped else number


def is_grid_cell(value: object) -> bool:
    """Whether a stored item can round-trip through a grid cell.

    ``None`` qualifies: it is a blank cell, which reads back as ``None``. It has
    to, because a grid *produces* blank cells -- adding a row writes one -- and
    an editor that could not re-render its own output would turn itself
    read-only the moment the user added a row.

    ``bool`` does not, even though it is an ``int`` subclass. A grid renders
    ``True`` as the text ``"True"``, which reads back as the *string*
    ``"True"``, so committing an untouched neighbouring cell would silently
    rewrite a stored ``true``. Such a value is shown read-only or raw rather
    than corrupted.
    """
    if value is None:
        return True
    return isinstance(value, (int, float, str)) and not isinstance(value, bool)


def values_equal(a: object, b: object) -> bool:
    """Type-aware equality for deciding whether a draft really changed.

    Python's bare ``==`` considers ``5 == 5.0`` and ``True == 1`` to be True,
    but their JSON representations differ (``5`` vs ``5.0``, ``true`` vs ``1``).
    Using a bare ``==`` would therefore treat a real, kind-changing edit --
    typing ``5.0`` over a stored ``5`` -- as a no-op and silently skip the
    commit. Equality here requires the runtime types to match exactly as well as
    the values comparing equal.

    NaN needs its own clause: ``parse_value`` deliberately admits ``"nan"`` as a
    float, but ``nan == nan`` is False, so without it retyping an identical NaN
    would read as a real edit and pollute the undo history with no-op commits.
    """
    if type(a) is not type(b):
        return False
    if isinstance(a, float) and math.isnan(a):
        return math.isnan(b)  # type: ignore[arg-type]
    return a == b
