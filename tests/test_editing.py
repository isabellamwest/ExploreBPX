"""Tests for pure editing operations on the raw BPX dictionary."""

from __future__ import annotations

import copy

import pytest

from explore_bpx.core import editing
from explore_bpx.core.document import BPXDocument


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


# --- move_key: reorder a sibling within its parent dict ---


def test_move_key_up_and_down_swaps_with_neighbour():
    raw = {"Parent": {"a": 1, "b": 2, "c": 3}}
    moved_up = editing.move_key(raw, ("Parent", "b"), "up")
    assert list(moved_up["Parent"]) == ["b", "a", "c"]
    moved_down = editing.move_key(raw, ("Parent", "b"), "down")
    assert list(moved_down["Parent"]) == ["a", "c", "b"]
    # Values travel with their key, source untouched.
    assert moved_up["Parent"] == {"b": 2, "a": 1, "c": 3}
    assert raw == {"Parent": {"a": 1, "b": 2, "c": 3}}


def test_move_key_first_up_or_last_down_is_rejected():
    raw = {"Parent": {"a": 1, "b": 2, "c": 3}}
    with pytest.raises(editing.EditError):
        editing.move_key(raw, ("Parent", "a"), "up")
    with pytest.raises(editing.EditError):
        editing.move_key(raw, ("Parent", "c"), "down")


def test_move_key_rejects_unknown_direction():
    raw = {"Parent": {"a": 1, "b": 2}}
    with pytest.raises(editing.EditError):
        editing.move_key(raw, ("Parent", "a"), "sideways")


def test_move_key_rejects_missing_key():
    raw = {"Parent": {"a": 1}}
    with pytest.raises(editing.EditError):
        editing.move_key(raw, ("Parent", "nope"), "up")


# --- duplicate_key: deep-copy a sibling immediately after itself ---


def test_duplicate_key_inserts_adjacent_with_unit_aware_name():
    raw = {"Parent": {"Foo": 1, "Bar": 2}}
    updated, new_key = editing.duplicate_key(raw, ("Parent", "Foo"))
    assert new_key == "Foo (2)"
    assert list(updated["Parent"]) == ["Foo", "Foo (2)", "Bar"]
    assert updated["Parent"]["Foo (2)"] == 1


def test_duplicate_key_keeps_unit_bracket_trailing():
    raw = {"Parent": {"Foo [V]": 3.5}}
    updated, new_key = editing.duplicate_key(raw, ("Parent", "Foo [V]"))
    assert new_key == "Foo (2) [V]"
    assert list(updated["Parent"]) == ["Foo [V]", "Foo (2) [V]"]


def test_duplicate_key_increments_past_a_collision():
    raw = {"Parent": {"Foo": 1, "Foo (2)": 9}}
    updated, new_key = editing.duplicate_key(raw, ("Parent", "Foo"))
    assert new_key == "Foo (3)"
    assert list(updated["Parent"]) == ["Foo", "Foo (3)", "Foo (2)"]


def test_duplicate_key_deep_copies_nested_values_independently():
    raw = {"Parent": {"Foo": {"x": [1, 2, 3]}}}
    updated, new_key = editing.duplicate_key(raw, ("Parent", "Foo"))
    updated["Parent"]["Foo"]["x"].append(4)
    assert updated["Parent"][new_key]["x"] == [1, 2, 3]


def test_duplicate_key_rejects_missing_key():
    raw = {"Parent": {}}
    with pytest.raises(editing.EditError):
        editing.duplicate_key(raw, ("Parent", "nope"))
