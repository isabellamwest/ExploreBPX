"""Tests for the BPX gateway (the only module coupled to ``bpx``)."""

from __future__ import annotations

import copy

import pytest

from core import bpx_gateway
from core.bpx_gateway import LoadError


def test_load_raw_json(valid_spm_bytes):
    raw, fmt = bpx_gateway.load_raw(valid_spm_bytes, "spm_example_valid.json")
    assert fmt == "json"
    assert raw["Header"]["Model"] == "SPM"


def test_load_raw_yaml_detected_by_extension():
    raw, fmt = bpx_gateway.load_raw(b"Header:\n  Model: SPM\n", "thing.yaml")
    assert fmt == "yaml"
    assert raw == {"Header": {"Model": "SPM"}}


def test_load_raw_rejects_non_object():
    with pytest.raises(LoadError):
        bpx_gateway.load_raw(b"[1, 2, 3]", "thing.json")


def test_load_raw_rejects_malformed():
    with pytest.raises(LoadError):
        bpx_gateway.load_raw(b"{not json", "thing.json")


def test_validate_valid_file(valid_spm_dict):
    result = bpx_gateway.validate(valid_spm_dict)
    assert result.is_valid is True
    assert all(issue.severity.value == "warning" for issue in result.issues)


def test_validate_invalid_file_reports_issues(valid_spm_dict):
    broken = copy.deepcopy(valid_spm_dict)
    del broken["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.issues


def test_metadata_index_known_fields():
    index = bpx_gateway.metadata_index()
    assert index["OCP [V]"].allows_function is True
    assert index["Model"].is_enum is True
    assert "SPM" in index["Model"].enum_values
    assert index[
        "Number of electrode pairs connected in parallel to make a cell"
    ].is_integer is True
    assert index["Title"].is_text is True


def test_expected_fields_cell_matches_schema_aliases():
    fields = bpx_gateway.expected_fields(("Parameterisation", "Cell"))
    aliases = {field.alias for field in fields}
    assert aliases == {
        "Electrode area [m2]",
        "External surface area [m2]",
        "Volume [m3]",
        "Number of electrode pairs connected in parallel to make a cell",
        "Lower voltage cut-off [V]",
        "Upper voltage cut-off [V]",
        "Nominal cell capacity [A.h]",
        "Reference temperature [K]",
        "Density [kg.m-3]",
        "Specific heat capacity [J.K-1.kg-1]",
    }


def test_expected_fields_cell_required_flag():
    fields = {field.alias: field for field in bpx_gateway.expected_fields(
        ("Parameterisation", "Cell")
    )}
    assert fields["Nominal cell capacity [A.h]"].required is True
    assert fields["External surface area [m2]"].required is False


def test_expected_fields_carries_metadata_index_meta():
    fields = {field.alias: field for field in bpx_gateway.expected_fields(("Header",))}
    assert fields["Model"].meta is bpx_gateway.metadata_index()["Model"]
    assert fields["Model"].meta.is_enum is True


def test_expected_fields_order_is_stable():
    first = [field.alias for field in bpx_gateway.expected_fields(("Parameterisation", "Cell"))]
    second = [field.alias for field in bpx_gateway.expected_fields(("Parameterisation", "Cell"))]
    assert first == second


def test_expected_fields_parameterisation_varies_by_model():
    spm_aliases = {field.alias for field in bpx_gateway.expected_fields(("Parameterisation",), "SPM")}
    dfn_aliases = {field.alias for field in bpx_gateway.expected_fields(("Parameterisation",), "DFN")}
    assert "Electrolyte" not in spm_aliases
    assert "Electrolyte" in dfn_aliases


def test_expected_fields_unsupported_electrode_path_raises():
    with pytest.raises(ValueError):
        bpx_gateway.expected_fields(("Parameterisation", "Negative electrode"))


def test_expected_fields_unknown_path_raises():
    with pytest.raises(ValueError):
        bpx_gateway.expected_fields(("Nonexistent",))
