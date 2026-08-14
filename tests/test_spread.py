"""Unit tests for ``core.spread`` -- the spread scale's pure geometry.

No Qt anywhere: these run without a QApplication and prove the axis rules
(bounds, padding, log/linear choice, coincident grouping, hidden states)
independently of any widget.
"""

import math

import pytest

from app.core.spread import MAX_DIVISIONS, MIN_DIVISIONS, build_spread, numeric

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


def test_linear_padding_keeps_the_extremes_off_the_axis_ends():
    scale = build_spread(2.0, [1.0, 3.0])
    assert scale.log is False
    assert 0.0 < scale.ticks[0].position < scale.ticks[-1].position < 1.0


def test_end_labels_are_the_stated_extremes_not_the_padded_bounds():
    scale = build_spread(2.0, [1.0, 3.0])
    assert (scale.value_lo, scale.value_hi) == (1.0, 3.0)


def test_a_main_value_outside_the_references_becomes_an_end_label():
    scale = build_spread(10.0, [1.0, 2.0])
    assert (scale.value_lo, scale.value_hi) == (1.0, 10.0)


def test_positions_ascend_with_value_and_stay_inside_the_axis():
    scale = build_spread(2.0, [1.0, 3.0])
    lo, hi = scale.ticks[0], scale.ticks[-1]
    assert lo.value == 1.0
    assert hi.value == 3.0
    assert 0.0 < lo.position < scale.main_position < hi.position < 1.0


def test_main_outside_the_reference_span_extends_the_axis():
    scale = build_spread(10.0, [1.0, 2.0])
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


def test_log_axis_orders_the_values_and_labels_the_stated_extremes():
    scale = build_spread(None, [1e-15, 5e-12])
    assert scale.log is True
    assert [t.value for t in scale.ticks] == [1e-15, 5e-12]
    assert (scale.value_lo, scale.value_hi) == (1e-15, 5e-12)
    assert 0.0 < scale.ticks[0].position < scale.ticks[-1].position < 1.0


def test_all_negative_log_keeps_numeric_order():
    scale = build_spread(None, [-1e-10, -1e-15])
    assert scale.log is True
    more_negative = next(t for t in scale.ticks if t.value == -1e-10)
    less_negative = next(t for t in scale.ticks if t.value == -1e-15)
    assert more_negative.position < less_negative.position
    assert (scale.value_lo, scale.value_hi) == (-1e-10, -1e-15)


# ── non-finite input ────────────────────────────────────────────────────────


def test_nan_main_counts_as_empty():
    scale = build_spread(float("nan"), [1.0, 2.0])
    assert scale.visible is True
    assert scale.main_position is None


def test_non_finite_references_are_ignored():
    scale = build_spread(1.0, [math.inf, 2.0])
    assert scale.visible is True
    assert [t.value for t in scale.ticks] == [2.0]


# ── divisions: linear ───────────────────────────────────────────────────────


def test_hidden_scale_carries_no_divisions():
    assert build_spread(None, []).divisions == ()


def test_linear_divisions_are_nice_steps_inside_the_padded_range():
    """This module's actual contract for 5.0..12.5: a 2.5 step landing on
    5/7.5/10/12.5, not the 6/8/10/12 a step of 2 would also have satisfied."""
    scale = build_spread(None, [5.0, 12.5])
    assert scale.log is False
    assert [d.value for d in scale.divisions] == [5.0, 7.5, 10.0, 12.5]
    assert [d.label for d in scale.divisions] == ["5", "7.5", "10", "12.5"]


def test_linear_divisions_cross_zero_with_a_division_at_it():
    scale = build_spread(None, [-5.0, 5.0])
    assert [d.value for d in scale.divisions] == [-5.0, 0.0, 5.0]
    assert [d.label for d in scale.divisions] == ["-5", "0", "5"]


@pytest.mark.parametrize(
    ("lo", "hi"),
    [
        (5.0, 5.1),  # a tiny span
        (5.0, 12.5),
        (-5.0, 5.0),
        (-1e6, 1e6),  # huge but mixed-signed, so never log
        (5.0, 7.0),  # the capacity-card shape
        (0.001, 0.09),
    ],
)
def test_linear_division_count_stays_in_the_target_band(lo, hi):
    scale = build_spread(None, [lo, hi])
    assert scale.log is False
    assert MIN_DIVISIONS <= len(scale.divisions) <= MAX_DIVISIONS


def test_linear_divisions_ascend_and_stay_on_axis():
    scale = build_spread(None, [5.0, 12.5])
    positions = [d.position for d in scale.divisions]
    assert positions == sorted(positions)
    assert positions[0] > 0.0
    assert positions[-1] < 1.0


def test_two_decades_exactly_gets_linear_divisions_not_decade_marks():
    """``test_two_decades_exactly_stays_linear`` covers the axis-kind
    choice; this covers what that choice does to the divisions -- nice
    steps (0/50/100), not decade marks (1/10/100), since the axis stayed
    linear."""
    scale = build_spread(None, [1.0, 100.0])
    assert scale.log is False
    assert [d.value for d in scale.divisions] == [0.0, 50.0, 100.0]


# ── divisions: log ──────────────────────────────────────────────────────────


def test_log_divisions_are_decade_marks():
    scale = build_spread(None, [0.18, 100.0])
    assert scale.log is True
    assert [d.value for d in scale.divisions] == [1.0, 10.0, 100.0]
    assert [d.label for d in scale.divisions] == ["1", "10", "100"]


def test_log_division_labels_stay_compact_at_tiny_magnitudes():
    """The module docstring's own example label ("1e-14") is a real division
    here, not just an illustration."""
    scale = build_spread(None, [1e-15, 5e-12])
    assert scale.log is True
    assert [d.label for d in scale.divisions] == ["1e-15", "1e-14", "1e-13", "1e-12"]


def test_log_divisions_stride_past_five_decades():
    """1..1e7 is 7 decades: strided to every 2nd, landing on 4 marks rather
    than the 8 unstrided decades would give."""
    scale = build_spread(None, [1.0, 1e7])
    assert scale.log is True
    assert len(scale.divisions) <= MAX_DIVISIONS
    assert [d.value for d in scale.divisions] == [1.0, 100.0, 10000.0, 1000000.0]
    assert [d.label for d in scale.divisions] == ["1", "100", "10000", "1e+06"]


def test_log_divisions_on_an_all_negative_axis_use_the_true_negative_values():
    scale = build_spread(None, [-1e-10, -1e-15])
    assert scale.log is True
    assert [d.value for d in scale.divisions] == [-1e-11, -1e-13, -1e-15]
    assert [d.label for d in scale.divisions] == ["-1e-11", "-1e-13", "-1e-15"]
    positions = [d.position for d in scale.divisions]
    assert positions == sorted(positions)


def test_log_division_count_never_exceeds_the_maximum():
    scale = build_spread(None, [1e-15, 1e5])  # 20 decades
    assert scale.log is True
    assert len(scale.divisions) <= MAX_DIVISIONS


# ── numeric() ───────────────────────────────────────────────────────────────


@pytest.mark.parametrize("value", [2, 2.5, -3])
def test_numeric_accepts_plain_numbers(value):
    assert numeric(value) == float(value)


@pytest.mark.parametrize("value", [None, "2.5", True, False, [1.0], float("nan")])
def test_numeric_rejects_everything_else(value):
    assert numeric(value) is None
