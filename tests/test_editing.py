"""Tests for pure editing operations on the raw BPX dictionary."""

from __future__ import annotations

import copy

import pytest

from core import editing
from core.document import BPXDocument


def test_set_value_returns_new_dict_and_leaves_input_untouched(valid_spm_dict):
    original = copy.deepcopy(valid_spm_dict)
    path = ("Header", "Model")
    updated = editing.set_value(valid_spm_dict, path, "DFN")
    assert updated["Header"]["Model"] == "DFN"
    assert valid_spm_dict == original  # source untouched


def test_set_value_rejects_empty_path(valid_spm_dict):
    with pytest.raises(editing.EditError):
        editing.set_value(valid_spm_dict, (), "x")


def test_set_value_rejects_missing_segment(valid_spm_dict):
    with pytest.raises(editing.EditError):
        editing.set_value(valid_spm_dict, ("Nope", "Field"), 1)


def test_add_and_remove_parameter(valid_spm_dict):
    added = editing.add_parameter(valid_spm_dict, ("Header",), "Custom", 5)
    assert added["Header"]["Custom"] == 5
    removed = editing.remove_parameter(added, ("Header", "Custom"))
    assert "Custom" not in removed["Header"]


def test_add_and_remove_section(valid_spm_dict):
    added = editing.add_section(valid_spm_dict, ("Header",), "Extra")
    assert added["Header"]["Extra"] == {}
    removed = editing.remove_section(added, ("Header", "Extra"))
    assert "Extra" not in removed["Header"]


def test_edit_then_revalidate_through_document(valid_spm_dict):
    document = BPXDocument.from_raw(valid_spm_dict, "spm.json", "json")
    assert document.is_valid
    broken = editing.set_value(document.raw, ("Header", "Model"), "Bogus")
    rebuilt = BPXDocument.from_raw(broken, "spm.json", "json")
    assert not rebuilt.is_valid
    assert valid_spm_dict["Header"]["Model"] != "Bogus"
