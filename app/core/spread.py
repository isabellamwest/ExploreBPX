"""Geometry for the scalar spread scale: where the main document's value and
every pinned reference's stated value sit along one axis.

Pure arithmetic over plain floats -- no Qt, no badge/colour/identity concepts,
no knowledge of where the values came from. The UI decides *whether* a
parameter gets a scale (numeric scalar/integer kinds only) and paints what
:func:`build_spread` returns; nothing here is ever computed from an assumed
physical range, only from the values actually present.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

#: Fraction of the (transformed) span added as padding beyond the outermost
#: values, so no mark sits flush against an axis end.
PADDING = 0.04

#: A log axis is only worth its reading cost once values span more than this
#: many decades; at or below it, linear keeps honest visual distances.
LOG_DECADES = 2.0


@dataclass(frozen=True)
class SpreadTick:
    """One tick: a value stated by one or more references.

    References sharing an identical value share a tick (the UI stacks their
    identity dots); the main document's value never merges into a tick -- it
    is a separate marker (``SpreadScale.main_position``).
    """

    #: The stated value.
    value: float
    #: Position along the axis in [0, 1] (0 = padded low end).
    position: float
    #: Pin-order indices, into the caller's reference-value list, of every
    #: reference stating this value.
    indices: tuple[int, ...]


@dataclass(frozen=True)
class SpreadScale:
    """Everything the UI needs to paint one spread scale.

    ``visible`` is False when the axis would carry no information: fewer than
    two distinct values across main and references (covers all-coincident,
    a lone reference against an empty main value, and the empty cases).
    A hidden scale carries no ticks and zeroed bounds -- callers must check
    ``visible`` first.
    """

    visible: bool
    #: True for a log axis (the UI labels the choice either way, so the
    #: switch is never silent).
    log: bool
    #: The lowest and highest values actually *stated*, by the main document
    #: or any reference -- what the axis ends are labelled with. The padding
    #: that keeps the outermost marks off the edges lives inside
    #: ``position`` and deliberately never surfaces as a number: an axis end
    #: reading a value no file states would be the app inventing data.
    value_lo: float
    value_hi: float
    ticks: tuple[SpreadTick, ...]
    #: The main document's marker position in [0, 1], or None when the main
    #: value is empty -- the scale then reads as a picker over references.
    main_position: float | None


_HIDDEN = SpreadScale(False, False, 0.0, 0.0, (), None)


def build_spread(main: float | None, refs: Sequence[float]) -> SpreadScale:
    """Lay out ``main`` and per-reference values (pin order) on one axis.

    Non-finite entries are ignored (a NaN main counts as empty). Log is
    chosen only when the union spans more than :data:`LOG_DECADES` decades
    *and* every value is nonzero with one shared sign -- mixed signs or a
    zero always keep the axis linear.
    """
    if main is not None and not math.isfinite(main):
        main = None
    indexed = [(i, v) for i, v in enumerate(refs) if math.isfinite(v)]

    values = [v for _, v in indexed]
    if main is not None:
        values.append(main)
    if len(set(values)) < 2:
        return _HIDDEN

    use_log = _spans_decades(values) and _one_signed(values)
    transform = _log_transform if use_log else (lambda v: v)

    ts = [transform(v) for v in values]
    t_lo, t_hi = min(ts), max(ts)
    pad = (t_hi - t_lo) * PADDING
    t_lo, t_hi = t_lo - pad, t_hi + pad
    span = t_hi - t_lo
    value_lo, value_hi = min(values), max(values)

    def position(v: float) -> float:
        return (transform(v) - t_lo) / span

    ticks: list[SpreadTick] = []
    for index, value in indexed:
        for at, tick in enumerate(ticks):
            if value == tick.value:
                ticks[at] = SpreadTick(tick.value, tick.position, tick.indices + (index,))
                break
        else:
            ticks.append(SpreadTick(value, position(value), (index,)))
    ticks.sort(key=lambda tick: tick.position)

    return SpreadScale(
        True,
        use_log,
        value_lo,
        value_hi,
        tuple(ticks),
        None if main is None else position(main),
    )


def numeric(value: object) -> float | None:
    """*value* as a plain float, or ``None`` when it is not a finite number.

    The one gate between a stored raw value and this module's arithmetic, so
    a card never sniffs types of its own. ``bool`` is excluded despite being
    an ``int`` subclass (the same call ``core.values.is_grid_cell`` makes):
    plotting ``True`` at 1.0 would state a number no file contains.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _spans_decades(values: list[float]) -> bool:
    magnitudes = [abs(v) for v in values if v != 0]
    if not magnitudes:
        return False
    return math.log10(max(magnitudes) / min(magnitudes)) > LOG_DECADES


def _one_signed(values: list[float]) -> bool:
    return all(v > 0 for v in values) or all(v < 0 for v in values)


def _log_transform(v: float) -> float:
    # Monotone in v for either shared sign: positives map to log10(v),
    # negatives to -log10(-v), so numeric order survives the transform.
    return math.log10(v) if v > 0 else -math.log10(-v)


