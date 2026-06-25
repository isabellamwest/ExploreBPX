"""Tests for export/roundtrip and JSON <-> YAML conversion."""

from __future__ import annotations

import json

import yaml

from core import export


def test_json_roundtrip_is_lossless(valid_spm_dict):
    data = export.to_json(valid_spm_dict)
    assert json.loads(data) == valid_spm_dict


def test_yaml_roundtrip_is_lossless(valid_spm_dict):
    data = export.to_yaml(valid_spm_dict)
    assert yaml.safe_load(data) == valid_spm_dict


def test_json_to_yaml_conversion_preserves_data(valid_spm_dict):
    as_yaml = export.to_yaml(valid_spm_dict)
    reparsed = yaml.safe_load(as_yaml)
    assert reparsed == valid_spm_dict


def test_to_bytes_selects_format(valid_spm_dict):
    assert export.to_bytes(valid_spm_dict, "yaml") == export.to_yaml(valid_spm_dict)
    assert export.to_bytes(valid_spm_dict, "json") == export.to_json(valid_spm_dict)
