"""Tests for ``bpx_gateway.sample_function``: the Inspector's chart-preview
seam for a ``Function`` expression. ExploreBPX never evaluates an
expression itself -- these tests pin that parsing stays ``bpx.Function``'s
own (``validate`` then ``to_python_function``) and that this seam only
chooses sample positions and reports the outcome honestly.
"""

from __future__ import annotations

import bpx
import pytest

from explore_bpx.core import bpx_gateway
from explore_bpx.core.bpx_gateway import FunctionSamples


def test_sample_function_evaluates_exp_and_tanh_over_the_default_count():
    result = bpx_gateway.sample_function("exp(-x) + tanh(x)", 0.0, 1.0)
    assert isinstance(result, FunctionSamples)
    assert result.error is None
    assert len(result.points) == 200
    assert result.points[0][0] == pytest.approx(0.0)
    assert result.points[0][1] == pytest.approx(1.0)  # exp(0) + tanh(0)
    assert result.points[-1][0] == pytest.approx(1.0)


def test_sample_function_hits_the_domain_endpoints_exactly():
    result = bpx_gateway.sample_function("2*x", 0.0, 10.0, samples=11)
    assert result.points[0] == (0.0, 0.0)
    assert result.points[-1] == (10.0, 20.0)


def test_sample_function_invalid_expression_reports_bpx_message_verbatim():
    with pytest.raises(ValueError, match="Invalid Function") as excinfo:
        bpx.Function.validate("2x")

    result = bpx_gateway.sample_function("2x", 0.0, 1.0)

    assert result.points == ()
    assert result.error.startswith("Invalid Function")
    assert result.error == str(excinfo.value)  # bpx's own wording, not a rewrite


def test_sample_function_drops_a_single_bad_point_but_keeps_the_rest():
    """ "1/x" over [-2, 2] with 5 samples lands on whole-number x values
    (-2, -1, 0, 1, 2), so the midpoint is x=0.0 exactly, not a
    floating-point near-miss -- only that one point is dropped."""
    result = bpx_gateway.sample_function("1/x", -2.0, 2.0, samples=5)

    assert result.error is None
    assert [x for x, _y in result.points] == [-2.0, -1.0, 1.0, 2.0]


@pytest.mark.parametrize(
    ("low", "high"),
    [
        (1.0, 0.0),  # low > high
        (1.0, 1.0),  # low == high
        (float("nan"), 1.0),
        (0.0, float("inf")),
    ],
)
def test_sample_function_rejects_a_degenerate_domain(low, high):
    result = bpx_gateway.sample_function("x", low, high)
    assert result.points == ()
    assert result.error == "domain must be a finite range with low < high"


def test_sample_function_drops_a_point_calling_an_undefined_function_name():
    """bpx's grammar accepts any identifier as a function call -- validity of
    the *name* is only judged at call time, by whatever the default preamble
    (``exp``/``tanh``/``cosh``) actually imported. "foo(x)" is therefore
    validation-legal but raises NameError on every call; dropped like any
    other per-point failure rather than crashing the whole sample."""
    result = bpx_gateway.sample_function("foo(x)", 0.0, 1.0)
    assert result.points == ()
    assert result.error.startswith("NameError")


def test_sample_function_all_points_failing_names_the_exception():
    """ "1/(x-x)" is zero-over-zero at every x, so every sampled point raises
    -- the error names the exception every point actually hit, rather than
    the generic "no finite values" wording reserved for a domain where
    nothing raised at all."""
    result = bpx_gateway.sample_function("1/(x-x)", -1.0, 1.0)
    assert result.points == ()
    assert result.error.startswith("ZeroDivisionError")


def test_sample_function_handles_bpxs_escaped_parse_syntax_exception():
    """``bpx.Function.validate`` only catches pyparsing's ``ParseException``;
    its own grammar raises the sibling ``ParseSyntaxException`` instead for
    some malformed input (an unclosed function call) -- confirmed against
    the installed bpx/pyparsing, a real gap in bpx's own except clause, not
    something to paper over. Pinned here (rather than silently swallowed)
    so a bpx upgrade that starts catching it too is not missed."""
    result = bpx_gateway.sample_function("exp(-x", 0.0, 1.0)
    assert result.points == ()
    assert result.error.startswith("ParseSyntaxException")


def test_sample_function_reports_a_validation_legal_expression_that_fails_to_compile():
    """A multi-line expression passes ``bpx.Function.validate`` (its grammar
    tolerates the newlines -- this app already renders one verbatim as a
    legitimate reference value, see
    ``test_full_multiline_expression_reference_renders_in_full``), but
    ``to_python_function`` splices the raw string into a single-line
    ``return`` statement, so it fails to even compile. A real gap between
    what bpx validates and what bpx can run, surfaced faithfully rather
    than papered over by reformatting the user's own expression."""
    multiline = "1*x +\n2*x**2 +\n3*x**3"
    bpx.Function.validate(multiline)  # sanity: genuinely validation-legal

    result = bpx_gateway.sample_function(multiline, 0.0, 1.0)

    assert result.points == ()
    assert result.error.startswith("SyntaxError")


def test_sample_function_caches_the_compiled_callable(monkeypatch):
    """The same expression sampled twice compiles once --
    ``to_python_function`` writes and imports a temp file per call, so this
    is a real cost to avoid, not just a micro-optimisation."""
    bpx_gateway._compiled_function.cache_clear()
    calls: list[int] = []
    original = bpx.Function.to_python_function

    def counted(self, preamble=None):
        calls.append(1)
        return original(self, preamble)

    monkeypatch.setattr(bpx.Function, "to_python_function", counted)

    bpx_gateway.sample_function("3*x", 0.0, 1.0)
    bpx_gateway.sample_function("3*x", 0.0, 1.0)

    assert len(calls) == 1
