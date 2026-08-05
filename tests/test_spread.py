"""Unit tests for ``core.spread`` -- the spread scale's pure geometry.

No Qt anywhere: these run without a QApplication and prove the axis rules
(bounds, padding, log/linear choice, coincident grouping, hidden states)
independently of any widget.
"""

import math

import pytest

from app.core.spread import build_spread


# ── hidden / visible ────────────────────────────────────────────────────────


def test_hidden_with_no_values():
    assert build_spread(None, []).visible is False


def test_hidden_with_main_only():
    assert build_spread(2.0, []).visible is False


def test_hidden_when_all_values_coincide():
    scale = build_spread(2.0, [2.0, 2.0, 2.0])
    assert scale.visible is False
    assert scale.ticks == ()


def test_hidden_with_empty_main_and_one_distinct_reference():
    assert build_spread(None, [5.0, 5.0]).visible is False


def test_visible_picker_with_empty_main_and_two_distinct_references():
    scale = build_spread(None, [1.0, 3.0])
    assert scale.visible is True
    assert scale.main_position is None
    assert len(scale.ticks) == 2


def test_visible_when_one_reference_differs_from_main():
    assert build_spread(2.0, [2.0, 3.0]).visible is True


# ── linear axis ─────────────────────────────────────────────────────────────


def test_linear_bounds_pad_beyond_extremes():
    scale = build_spread(2.0, [1.0, 3.0])
    assert scale.log is False
    assert scale.axis_lo < 1.0
    assert scale.axis_hi > 3.0


def test_positions_ascend_with_value_and_stay_inside_the_axis():
    scale = build_spread(2.0, [1.0, 3.0])
    lo, hi = scale.ticks[0], scale.ticks[-1]
    assert lo.value == 1.0 and hi.value == 3.0
    assert 0.0 < lo.position < scale.main_position < hi.position < 1.0


def test_main_outside_the_reference_span_extends_the_axis():
    scale = build_spread(10.0, [1.0, 2.0])
    assert scale.axis_hi > 10.0
    assert scale.main_position > max(t.position for t in scale.ticks)
    assert scale.main_position < 1.0


def test_main_coinciding_with_one_reference_sits_on_its_tick():
    scale = build_spread(2.0, [2.0, 3.0])
    tick = next(t for t in scale.ticks if t.value == 2.0)
    assert scale.main_position == pytest.approx(tick.position)


# ── coincident references ───────────────────────────────────────────────────


def test_coincident_references_share_one_tick_in_pin_order():
    scale = build_spread(None, [2e-5, 2e-5, 3e-5])
    assert len(scale.ticks) == 2
    shared = next(t for t in scale.ticks if t.value == 2e-5)
    assert shared.indices == (0, 1)


# ── log / linear choice ─────────────────────────────────────────────────────


def test_two_decades_exactly_stays_linear():
    assert build_spread(None, [1.0, 100.0]).log is False


def test_beyond_two_decades_switches_to_log():
    assert build_spread(None, [1.0, 1001.0]).log is True


def test_mixed_signs_never_log():
    assert build_spread(None, [-1.0, 1e5]).log is False


def test_zero_never_log():
    assert build_spread(None, [0.0, 1e5]).log is False


def test_log_axis_bounds_bracket_the_values():
    scale = build_spread(None, [1e-15, 5e-12])
    assert scale.log is True
    assert 0.0 < scale.axis_lo < 1e-15
    assert scale.axis_hi > 5e-12
    assert [t.value for t in scale.ticks] == [1e-15, 5e-12]


def test_all_negative_log_keeps_numeric_order_and_signed_bounds():
    scale = build_spread(None, [-1e-10, -1e-15])
    assert scale.log is True
    more_negative = next(t for t in scale.ticks if t.value == -1e-10)
    less_negative = next(t for t in scale.ticks if t.value == -1e-15)
    assert more_negative.position < less_negative.position
    assert scale.axis_lo < -1e-10
    assert -1e-15 < scale.axis_hi < 0.0


# ── non-finite input ────────────────────────────────────────────────────────


def test_nan_main_counts_as_empty():
    scale = build_spread(float("nan"), [1.0, 2.0])
    assert scale.visible is True
    assert scale.main_position is None


def test_non_finite_references_are_ignored():
    scale = build_spread(1.0, [math.inf, 2.0])
    assert scale.visible is True
    assert [t.value for t in scale.ticks] == [2.0]
