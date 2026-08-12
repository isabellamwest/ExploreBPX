"""Tests for the display-merge helpers in ``core.validation``.

Pure Python, no Qt.
"""

from __future__ import annotations

from core.validation import (
    BPXExceptionDiagnostic,
    PydanticErrorDiagnostic,
    PythonWarningDiagnostic,
    Severity,
    input_fact,
    merge_union_pair,
    merge_union_pairs_by_location,
)


def _diag(error_type: str, message: str = "msg") -> PydanticErrorDiagnostic:
    return PydanticErrorDiagnostic(raw_error={"type": error_type, "msg": message})


def _diag_with_input(error_type: str, value: object, message: str = "msg") -> PydanticErrorDiagnostic:
    return PydanticErrorDiagnostic(raw_error={"type": error_type, "msg": message, "input": value})


def test_merge_union_pair_collapses_float_and_int_type():
    float_d = _diag("float_type", "Input should be a valid number")
    int_d = _diag("int_type", "Input should be a valid integer")

    merged = merge_union_pair((float_d, int_d))

    assert merged == (float_d,)
    assert merged[0].message == "Input should be a valid number"


def test_merge_union_pair_collapses_float_and_int_parsing():
    """A bad *string* in a FloatInt field raises float_parsing+int_parsing
    (not float_type+int_type) -- the same one problem, so it collapses the
    same way, to the "valid number" wording."""
    float_d = _diag("float_parsing", "Input should be a valid number, unable to parse string as a number")
    int_d = _diag("int_parsing", "Input should be a valid integer, unable to parse string as an integer")

    merged = merge_union_pair((float_d, int_d))

    assert merged == (float_d,)
    assert merged[0].message.startswith("Input should be a valid number")


def test_merge_union_pair_does_not_cross_variants():
    """A float_type paired with an int_parsing (never emitted together by
    the validator, but a guard against over-eager merging) is left alone --
    only a matched same-variant pair collapses."""
    mixed = (_diag("float_type"), _diag("int_parsing"))
    assert merge_union_pair(mixed) == mixed


def test_merge_union_pair_passes_through_when_incomplete():
    """Only a *complete* float_type+int_type pair merges -- a lone float_type
    (or int_type), or an unrelated error_type, is never touched."""
    float_only = (_diag("float_type"),)
    assert merge_union_pair(float_only) == float_only

    int_only = (_diag("int_type"),)
    assert merge_union_pair(int_only) == int_only

    other = (_diag("missing"), _diag("extra_forbidden"))
    assert merge_union_pair(other) == other


def test_merge_union_pair_preserves_order_and_other_diagnostics():
    missing = _diag("missing", "Field required")
    float_d = _diag("float_type", "Input should be a valid number")
    int_d = _diag("int_type", "Input should be a valid integer")

    merged = merge_union_pair((missing, float_d, int_d))

    assert merged == (missing, float_d)


def test_merge_union_pairs_by_location_groups_by_nav_path():
    loc_a = ("Cell", "Nominal cell capacity [A.h]")
    loc_b = ("Cell", "Electrode area [m2]")
    float_a = _diag("float_type", "Input should be a valid number")
    int_a = _diag("int_type", "Input should be a valid integer")
    missing_b = _diag("missing", "Field required")

    items = ((float_a, loc_a), (int_a, loc_a), (missing_b, loc_b))

    merged = merge_union_pairs_by_location(items)

    assert merged == ((float_a, loc_a), (missing_b, loc_b))


def test_merge_union_pairs_by_location_empty_input():
    assert merge_union_pairs_by_location(()) == ()


def test_merge_union_pairs_by_location_never_merges_across_different_locations():
    """m1 (reviewed gap): the false-positive the plan asks to prove
    impossible. A ``float_type`` at one location and an ``int_type`` at a
    DIFFERENT location must NOT merge -- neither is a complete pair at its
    own location. A location-insensitive grouping bug would instead pool
    both error_types together, wrongly conclude a pair exists, and silently
    drop the second diagnostic (a real validator message vanishing off the
    page). Deliberately asymmetric (unlike the float+float scenario a naive
    fix could still pass): each location holds only ONE half of the pair.
    """
    loc_a = ("Cell", "Nominal cell capacity [A.h]")
    loc_b = ("Cell", "Electrode area [m2]")
    float_a = _diag("float_type", "Input should be a valid number")
    int_b = _diag("int_type", "Input should be a valid integer")

    merged = merge_union_pairs_by_location(((float_a, loc_a), (int_b, loc_b)))

    assert merged == ((float_a, loc_a), (int_b, loc_b))


def test_merge_union_pair_severity_preserved():
    """The merge is display-only -- it never invents/loses severity."""
    float_d = PydanticErrorDiagnostic(
        raw_error={"type": "float_type", "msg": "Input should be a valid number"},
        severity=Severity.ERROR,
    )
    int_d = PydanticErrorDiagnostic(
        raw_error={"type": "int_type", "msg": "Input should be a valid integer"},
        severity=Severity.ERROR,
    )
    merged = merge_union_pair((float_d, int_d))
    assert merged[0].severity == Severity.ERROR


# --- input_fact --------------------------------------------------------


def test_input_fact_numeric_int():
    assert input_fact(_diag_with_input("greater_than", 5)) == "input 5"


def test_input_fact_numeric_float():
    assert input_fact(_diag_with_input("less_than_equal", -0.3)) == "input -0.3"


def test_input_fact_excludes_bool():
    """``bool`` is an ``int`` subclass in Python, but no user typed "True"
    into a numeric field."""
    assert input_fact(_diag_with_input("float_type", True)) is None
    assert input_fact(_diag_with_input("float_type", False)) is None


def test_input_fact_excludes_non_finite_float():
    assert input_fact(_diag_with_input("float_type", float("inf"))) is None
    assert input_fact(_diag_with_input("float_type", float("-inf"))) is None
    assert input_fact(_diag_with_input("float_type", float("nan"))) is None


def test_input_fact_excludes_non_numeric_input():
    assert input_fact(_diag_with_input("dict_type", {"a": 1})) is None
    assert input_fact(_diag_with_input("list_type", [1, 2])) is None
    assert input_fact(_diag_with_input("string_type", "banana")) is None
    assert input_fact(_diag_with_input("float_type", None)) is None


def test_input_fact_none_for_a_missing_field_error():
    """A ``missing`` error carries no offending value at all (``.input`` is
    ``None`` since the raw dict has no ``"input"`` key) -- nothing is
    invented to fill the gap."""
    assert input_fact(_diag("missing", "Field required")) is None


def test_input_fact_none_for_non_pydantic_diagnostic_kinds():
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        warnings.warn("test warning", stacklevel=1)
    warning_diag = PythonWarningDiagnostic(raw_warning=caught[0])
    assert input_fact(warning_diag) is None

    exc_diag = BPXExceptionDiagnostic(raw_exception=ValueError("boom"))
    assert input_fact(exc_diag) is None


def test_merge_union_pair_yields_one_input_fact_not_two():
    """A merged FloatInt union pair must produce at most one input_fact --
    proven directly rather than assumed. Both halves are constructed with
    the same real numeric input (not reachable live, since a genuinely
    numeric value always parses as the float branch and so never raises
    both halves of the pair -- see the float_type/int_type docstring above)
    specifically so a regression that stopped collapsing the pair would be
    caught here as two suffixes, not zero."""
    float_d = _diag_with_input("float_type", 5, "Input should be a valid number")
    int_d = _diag_with_input("int_type", 5, "Input should be a valid integer")

    merged = merge_union_pair((float_d, int_d))

    assert len(merged) == 1
    assert [input_fact(d) for d in merged] == ["input 5"]
