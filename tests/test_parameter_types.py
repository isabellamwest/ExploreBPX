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
