"""Geometry for the scalar spread scale: where the main document's value and
every pinned reference's stated value sit along one axis.

Pure arithmetic over plain floats -- no Qt, no badge/colour/identity concepts,
no knowledge of where the values came from. The UI decides *whether* a
parameter gets a scale (numeric scalar/integer kinds only) and paints what
:func:`build_spread` returns; nothing here is ever computed from an assumed
physical range, only from the values actually present.

2026-08-12: a conscious, narrow supersession of the paragraph above. Two
renders that differed only in a centred "log scale"/"linear scale" caption
read as structurally identical, so the axis gained real, labelled divisions
-- round-number steps on a linear axis, decade marks on a log one
(:class:`SpreadDivision`). A division's value is chosen to make the *scale*
legible and is deliberately not claimed to be one any file states, unlike
every :class:`SpreadTick` and the main marker, which still are and only ever
will be. Divisions are computed here in the same pure-arithmetic style, so
the app still never invents a number in the UI layer -- it just no longer
draws the axis from the stated set alone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable, Sequence

#: Fraction of the (transformed) span added as padding beyond the outermost
#: values, so no mark sits flush against an axis end.
PADDING = 0.04

#: A log axis is only worth its reading cost once values span more than this
#: many decades; at or below it, linear keeps honest visual distances.
LOG_DECADES = 2.0

#: How many division marks the axis aims to show: enough to read the scale
#: at a glance, few enough not to crowd a narrow strip. Both the linear
#: nice-step search and the log decade stride target this band.
MIN_DIVISIONS = 3
MAX_DIVISIONS = 5

#: Linear division steps only ever take one of these shapes (times 10**k) --
#: the shapes any "nice numbers" axis in general use picks from, so a step
#: reads as a natural round number rather than an arbitrary fraction.
_NICE_STEPS = (1.0, 2.0, 2.5, 5.0)
#: Roughly how many linear divisions the initial guess targets before the
#: search in :func:`_linear_step` walks it into :data:`MIN_DIVISIONS` ..
#: :data:`MAX_DIVISIONS`.
_DIVISION_TARGET = 4
#: Ladder rungs :func:`_linear_step` will try before giving up and using
#: whichever rung it last reached -- always enough in practice (checked
#: against spans from a hundredth of a unit to a trillion-fold one).
_MAX_STEP_SEARCH = 16
#: Tolerance, as a fraction of the quantity being compared, for boundary
#: floating-point noise in the division searches below (a value computed
#: as exactly a multiple of the step still needs to pass a ``<=`` check
#: against a bound computed a different way).
_EPS = 1e-9


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
class SpreadDivision:
    """One labelled scale mark on the axis -- not a stated value.

    Chosen purely to make the axis readable: round linear steps, or decade
    marks on a log axis (see the module docstring's 2026-08-12 note). Unlike
    :class:`SpreadTick` and the main marker, a division's ``value`` is not
    claimed to be one any file states.
    """

    #: A round number the axis chose, not necessarily one any file states.
    value: float
    #: Position along the axis in [0, 1], via the same transform as ticks.
    position: float
    #: Compact rendering of ``value`` (Python's ``%g``), e.g. "0.1", "1e-14".
    label: str


@dataclass(frozen=True)
class SpreadScale:
    """Everything the UI needs to paint one spread scale.

    ``visible`` is False when the axis would carry no information: fewer than
    two distinct values across main and references (covers all-coincident,
    a lone reference against an empty main value, and the empty cases).
    A hidden scale carries no ticks, no divisions and zeroed bounds --
    callers must check ``visible`` first.
    """

    visible: bool
    #: True for a log axis (the UI labels the choice either way, so the
    #: switch is never silent).
    log: bool
    #: The lowest and highest values actually *stated*, by the main document
    #: or any reference. Until 2026-08-12 these were literally what the axis
    #: ends were labelled with; that labelling is now done by ``divisions``
    #: instead, so these two exist for a caller that still wants the true
    #: extremes -- a tooltip, say -- not for painting. The padding that
    #: keeps the outermost marks off the edges lives inside ``position`` and
    #: still never surfaces as a number on these two fields.
    value_lo: float
    value_hi: float
    ticks: tuple[SpreadTick, ...]
    #: The axis's own scale marks, in position order. See
    #: :class:`SpreadDivision`.
    divisions: tuple[SpreadDivision, ...]
    #: The main document's marker position in [0, 1], or None when the main
    #: value is empty -- the scale then reads as a picker over references.
    main_position: float | None


_HIDDEN = SpreadScale(False, False, 0.0, 0.0, (), (), None)


def build_spread(main: float | None, refs: Sequence[float]) -> SpreadScale:
    """Lay out ``main`` and per-reference values (pin order) on one axis.

    Non-finite entries are ignored (a NaN main counts as empty). Log is
    chosen only when the union spans more than :data:`LOG_DECADES` decades
    *and* every value is nonzero with one shared sign -- mixed signs or a
    zero always keep the axis linear. Divisions (see :class:`SpreadDivision`)
    are computed once that choice is made, from the same padded transformed
    range the ticks are positioned in.
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

    if use_log:
        # One-signed is already guaranteed by ``use_log`` -- checking one
        # value's sign is enough to know every value's.
        divisions = _log_divisions(t_lo, t_hi, values[0] < 0, position)
    else:
        divisions = _linear_divisions(t_lo, t_hi, position)

    return SpreadScale(
        True,
        use_log,
        value_lo,
        value_hi,
        tuple(ticks),
        divisions,
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


# ── divisions ────────────────────────────────────────────────────────────


def _linear_divisions(
    lo: float, hi: float, position: Callable[[float], float]
) -> tuple[SpreadDivision, ...]:
    """Nice-step divisions across ``[lo, hi]`` (the padded, linear-space
    range -- identical to ``value_lo``/``value_hi`` padded, since the
    linear transform is the identity)."""
    step = _linear_step(lo, hi)
    return tuple(
        SpreadDivision(value, position(value), _division_label(value))
        for value in _multiples_within(lo, hi, step)
    )


def _linear_step(lo: float, hi: float) -> float:
    """The 1/2/2.5/5 x 10**k step that lands :data:`MIN_DIVISIONS` to
    :data:`MAX_DIVISIONS` multiples inside ``[lo, hi]``.

    Starts from the rung that would give roughly :data:`_DIVISION_TARGET`
    divisions, then walks the nice-step ladder up or down until the actual
    count -- which depends on where ``lo``/``hi`` land relative to a
    multiple, not only on the step size -- reaches the wanted band.
    """
    raw_step = (hi - lo) / _DIVISION_TARGET
    rung = _first_rung_at_least(raw_step)
    for _ in range(_MAX_STEP_SEARCH):
        step = _nice_step(rung)
        count = len(_multiples_within(lo, hi, step))
        if count > MAX_DIVISIONS:
            rung += 1
        elif count < MIN_DIVISIONS:
            rung -= 1
        else:
            return step
    return _nice_step(rung)


def _nice_step(rung: int) -> float:
    """The step at ``rung`` in the infinite ..., 0.5, 1, 2, 2.5, 5, 10, ...
    ladder built from :data:`_NICE_STEPS`.

    ``rung`` may be negative (sub-1 magnitudes) or run past the last shape
    in a decade; :func:`divmod` folds either back onto one of the four
    shapes at some power of ten, so the sequence is strictly increasing
    with no special-casing at a decade boundary.
    """
    decade, slot = divmod(rung, len(_NICE_STEPS))
    return _NICE_STEPS[slot] * (10.0**decade)


def _first_rung_at_least(raw_step: float) -> int:
    """The lowest rung (see :func:`_nice_step`) whose step is >= *raw_step*
    (*raw_step* > 0)."""
    exponent = math.floor(math.log10(raw_step))
    base = exponent * len(_NICE_STEPS)
    for offset in range(len(_NICE_STEPS) + 1):  # +1 reaches the next decade
        rung = base + offset
        if _nice_step(rung) >= raw_step * (1 - _EPS):
            return rung
    return base + len(_NICE_STEPS)  # pragma: no cover -- offset above always satisfies


def _multiples_within(lo: float, hi: float, step: float) -> list[float]:
    """Every multiple of *step* in ``[lo, hi]``, ascending.

    Each value is ``n * step`` for an integer ``n`` computed once, rather
    than a running total stepped in a loop -- the latter accumulates
    floating-point error over a long walk, which "%g" is not always enough
    to hide.
    """
    tolerance = step * _EPS
    n = math.ceil(lo / step - _EPS)
    values = []
    while n * step <= hi + tolerance:
        values.append(n * step)
        n += 1
    return values


def _log_divisions(
    t_lo: float, t_hi: float, negative: bool, position: Callable[[float], float]
) -> tuple[SpreadDivision, ...]:
    """Decade marks across the padded transformed range ``[t_lo, t_hi]``.

    *negative* is whether every underlying value is negative (already known
    from the same one-signed check that chose the log axis at all): the
    marks are then ``-(10**n)`` -- the true negative values, per the
    module's existing negative-log transform -- rather than positive
    decades that no value here could be. Strided down to at most
    :data:`MAX_DIVISIONS` when more decades than that are in view.
    """
    tolerance = (t_hi - t_lo) * _EPS
    # transform(10**n) == n; transform(-(10**n)) == -n (see
    # ``_log_transform``), so a negative axis's decade exponents are the
    # negation of the positive-axis range over the same transformed bounds.
    n_lo, n_hi = (-t_hi, -t_lo) if negative else (t_lo, t_hi)
    exponents = list(range(math.ceil(n_lo - tolerance), math.floor(n_hi + tolerance) + 1))
    if len(exponents) > MAX_DIVISIONS:
        stride = math.ceil(len(exponents) / MAX_DIVISIONS)
        exponents = exponents[::stride]

    divisions = []
    for exponent in exponents:
        value = -(10.0**exponent) if negative else 10.0**exponent
        divisions.append(SpreadDivision(value, position(value), _division_label(value)))
    # Ascending exponent is ascending *value* when positive but descending
    # position when negative (-1e-15 sits right of -1e-11, the way -15 sits
    # right of -1 on a number line) -- sort on position explicitly, the same
    # invariant ``build_spread`` already sorts ``ticks`` on, rather than
    # leaning on an iteration order that only happens to match it once.
    divisions.sort(key=lambda division: division.position)
    return tuple(divisions)


def _division_label(value: float) -> str:
    """Compact rendering of a division's value.

    Python's ``%g``, e.g. "0.1", "1", "10", "1e-14" -- never
    ``core.values.format_value``'s full-precision ``str()``, which the
    ledger rows above already use for the values this label is not
    claiming to restate.
    """
    return f"{value:g}"


