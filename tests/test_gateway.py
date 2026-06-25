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
