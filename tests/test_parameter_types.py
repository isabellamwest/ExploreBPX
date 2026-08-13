"""Tests for parameter kind classification."""

from __future__ import annotations

from core import bpx_gateway
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


def test_classify_text_string_is_text():
    meta = FieldMeta(alias="Title", is_text=True)
    assert classify("My cell", meta) == ParameterKind.TEXT


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


def test_classify_function_field_number_stays_function():
    """A numeric constant in an allows_function field is still FUNCTION.

    The declared union is one kind; the stored value's shape only picks the
    card's initial mode (a card-level concern), never the classified kind.
    This replaces the removed exception where a numeric value classified as
    SCALAR, which made the field's Function/InterpolatedTable modes
    unreachable from the UI.
    """
    meta = FieldMeta(alias="Diffusivity [m2.s-1]", allows_function=True)
    assert classify(1.5e-14, meta) == ParameterKind.FUNCTION
    assert classify(2, meta) == ParameterKind.FUNCTION


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


def test_classify_no_metadata_bool_is_boolean():
    """Bool without metadata is BOOLEAN (no-meta fallback), checked before the
    int/float branch since ``bool`` is a subclass of ``int`` in Python."""
    assert classify(True) == ParameterKind.BOOLEAN
    assert classify(False) == ParameterKind.BOOLEAN


def test_classify_no_metadata_string_is_text():
    """A string without metadata is TEXT: prose under User-defined (or any
    other metadata-less string) must not get an expression editor."""
    assert classify("something") == ParameterKind.TEXT


# ---------------------------------------------------------------------------
# The meta=None contract for user-authored custom parameters
# ---------------------------------------------------------------------------
# A user-authored custom parameter is an ordinary raw-dict entry whose BPX
# metadata is genuinely absent (``meta=None``) -- nothing is synthesised or
# persisted for it. Absence is a valid first-class state, and value shape is
# the honest classifier when metadata is absent. These tests lock that
# contract.


def test_classify_custom_parameter_valueless_is_unknown():
    """A custom parameter with no value yet and no metadata is UNKNOWN."""
    assert classify(None) == ParameterKind.UNKNOWN


def test_classify_custom_parameter_numeric_is_scalar():
    """A custom parameter with a numeric value and no metadata is SCALAR."""
    assert classify(5) == ParameterKind.SCALAR
    assert classify(5.5) == ParameterKind.SCALAR


def test_classify_custom_parameter_string_is_text():
    """A custom parameter with a string value and no metadata is TEXT."""
    assert classify("some expression") == ParameterKind.TEXT


def test_classify_known_alias_from_field_meta_stays_authoritative():
    """A known BPX alias resolves real `FieldMeta` and stays metadata-
    authoritative -- the meta=None fallback above is reached only when
    metadata is genuinely absent, not for known schema aliases."""
    meta = bpx_gateway.field_meta(("Header", "Model"))
    assert classify("DFN", meta) == ParameterKind.ENUM


# ---------------------------------------------------------------------------
# Declared MAP and SERIES kinds, and the meta=None fallback's list -> SERIES
# / dict -> TABLE/SECTION shape rule (the one place value shape still
# classifies).
# ---------------------------------------------------------------------------


def test_classify_series_uses_metadata():
    """A declared array field (Experiment's Time/Current/Voltage/Temperature,
    InterpolatedTable's x/y) classifies SERIES regardless of the stored
    value's own shape."""
    meta = FieldMeta(alias="Time [s]", is_series=True)
    assert classify([0, 0.1, 0.2], meta) == ParameterKind.SERIES
    # Declared-type-first: an invalid non-list stored value stays SERIES too.
    assert classify("not-a-list", meta) == ParameterKind.SERIES


def test_classify_map_uses_metadata_unconditionally():
    """A declared per-material field (allows_map) classifies MAP whatever
    shape the stored value currently has -- a single FloatInt, a per-material
    dict, or an invalid value. Kind is declared; representation is a
    card-level concern."""
    meta = FieldMeta(alias="LAM: Positive electrode", allows_map=True)
    assert classify(1.0, meta) == ParameterKind.MAP
    assert classify({"Primary": 1.0, "Secondary": 5.0}, meta) == ParameterKind.MAP
    assert classify(None, meta) == ParameterKind.MAP


def test_classify_function_field_dict_value_stays_function():
    """A declared allows_function field holding an InterpolatedTable dict
    classifies FUNCTION, not TABLE -- the union is one kind; a table-shaped
    value only selects the InterpolatedTable mode."""
    meta = FieldMeta(alias="OCP [V]", allows_function=True)
    assert classify({"x": [0, 1], "y": [2, 3]}, meta) == ParameterKind.FUNCTION


def test_classify_no_metadata_list_is_series():
    """A list without metadata is SERIES (changed from TABLE): the
    structural dict/list shape check only classifies in the meta=None
    fallback, and an undeclared list's topology is a series, not a table."""
    assert classify([1, 2, 3]) == ParameterKind.SERIES


def test_classify_no_metadata_dict_shape_rule_unchanged():
    """The meta=None dict rule (table-shaped -> TABLE, else -> SECTION) is
    unchanged; only its position in `classify` moved (from unconditional to
    the meta=None branch only)."""
    assert classify({"x": [0, 1], "y": [2, 3]}) == ParameterKind.TABLE
    assert classify({"Cell": {}}) == ParameterKind.SECTION
