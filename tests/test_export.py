"""Tests for export/roundtrip and JSON <-> YAML conversion."""

from __future__ import annotations

import json
import math

import yaml

from core import export


def test_json_roundtrip_is_lossless(valid_spm_dict):
    data = export.to_json(valid_spm_dict)
    assert json.loads(data) == valid_spm_dict


def test_json_export_round_trips_nan_and_infinity(valid_spm_dict):
    """Deliberate stance (see export.to_json): bare NaN/Infinity tokens are
    not RFC 8259 JSON, but json and bpx both accept them, so export leaves
    them as-is rather than being stricter than the validator."""
    raw = dict(valid_spm_dict)
    raw["Parameterisation"] = dict(raw["Parameterisation"])
    raw["Parameterisation"]["NaN value"] = float("nan")
    raw["Parameterisation"]["Infinity value"] = float("inf")
    raw["Parameterisation"]["Negative infinity value"] = float("-inf")

    data = export.to_json(raw)
    assert b"NaN" in data
    assert b"Infinity" in data

    parsed = json.loads(data)
    assert math.isnan(parsed["Parameterisation"]["NaN value"])
    assert parsed["Parameterisation"]["Infinity value"] == float("inf")
    assert parsed["Parameterisation"]["Negative infinity value"] == float("-inf")


def test_yaml_roundtrip_is_lossless(valid_spm_dict):
    data = export.to_yaml(valid_spm_dict)
    assert yaml.safe_load(data) == valid_spm_dict


def test_to_bytes_selects_format(valid_spm_dict):
    assert export.to_bytes(valid_spm_dict, "yaml") == export.to_yaml(valid_spm_dict)
    assert export.to_bytes(valid_spm_dict, "json") == export.to_json(valid_spm_dict)
