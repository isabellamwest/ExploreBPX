"""Tests for parameter kind classification."""

from __future__ import annotations

from core.bpx_gateway import FieldMeta
from core.parameter_types import ParameterKind, classify, extract_unit, looks_like_table


def test_classify_scalar_float():
    assert classify(3.3e-14) == ParameterKind.SCALAR


def test_classify_integer_uses_metadata():
    meta = FieldMeta(alias="n", is_integer=True)
    assert classify(5, meta) == ParameterKind.INTEGER
    # A FloatInt field given as an int is still a scalar.
    assert classify(5) == ParameterKind.SCALAR


def test_classify_table():
    assert classify({"x": [0, 1], "y": [2, 3]}) == ParameterKind.TABLE


def test_classify_section():
    assert classify({"Cell": {}}) == ParameterKind.SECTION


def test_classify_function_string():
    meta = FieldMeta(alias="d", allows_function=True)
    assert classify("1 + x", meta) == ParameterKind.FUNCTION


def test_classify_text_string_is_scalar():
    meta = FieldMeta(alias="Title", is_text=True)
    assert classify("My cell", meta) == ParameterKind.SCALAR


def test_classify_enum():
    meta = FieldMeta(alias="Model", is_enum=True, enum_values=("SPM", "DFN"))
    assert classify("DFN", meta) == ParameterKind.ENUM


def test_extract_unit():
    assert extract_unit("Reference temperature [K]") == "K"
    assert extract_unit("Porosity") == ""


def test_looks_like_table():
    assert looks_like_table({"x": [1], "y": [2]}) is True
    assert looks_like_table({"a": 1}) is False


# ---------------------------------------------------------------------------
# Metadata-authoritative classification: invalid stored values
# ---------------------------------------------------------------------------

def test_classify_invalid_string_in_float_field_stays_scalar():
    """A string stored in a plain float field must remain SCALAR.

    Without this, the string branch would fall through to FUNCTION and the
    parameter would open read-only, trapping the user.
    """
    meta = FieldMeta(alias="Upper voltage cut-off [V]")
    assert classify("bad-value", meta) == ParameterKind.SCALAR


def test_classify_invalid_string_in_integer_field_stays_integer():
    """A string stored in an integer field must remain INTEGER."""
    meta = FieldMeta(alias="n", is_integer=True)
    assert classify("bad-value", meta) == ParameterKind.INTEGER


def test_classify_function_field_number_stays_scalar():
    """A numeric constant in an allows_function field must open in the scalar editor."""
    meta = FieldMeta(alias="Diffusivity [m2.s-1]", allows_function=True)
    assert classify(1.5e-14, meta) == ParameterKind.SCALAR
    assert classify(2, meta) == ParameterKind.SCALAR


def test_classify_function_field_string_stays_function():
    """A function expression string in an allows_function field must stay FUNCTION."""
    meta = FieldMeta(alias="Diffusivity [m2.s-1]", allows_function=True)
    assert classify("1.5e-14 * exp(-x)", meta) == ParameterKind.FUNCTION


def test_classify_function_field_invalid_string_stays_function():
    """An invalid string in an allows_function field is still FUNCTION.

    The field legitimately accepts strings (as function expressions), so a
    non-parseable string is an invalid expression, not a type violation.  The
    function editor (once implemented) is responsible for showing the error.
    """
    meta = FieldMeta(alias="Diffusivity [m2.s-1]", allows_function=True)
    assert classify("not-a-function", meta) == ParameterKind.FUNCTION


def test_classify_bool_in_float_field_stays_scalar():
    """A bool stored in a plain float field must remain SCALAR (not INTEGER)."""
    meta = FieldMeta(alias="Porosity")
    assert classify(True, meta) == ParameterKind.SCALAR


def test_classify_no_metadata_bool_is_scalar():
    """Bool without metadata is SCALAR (no-meta fallback)."""
    assert classify(True) == ParameterKind.SCALAR


def test_classify_no_metadata_string_is_function():
    """A string without metadata is FUNCTION (BPX treats unknown strings as expressions)."""
    assert classify("something") == ParameterKind.FUNCTION
