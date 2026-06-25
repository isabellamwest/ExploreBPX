"""Tests for tree generation and validation-path matching."""

from __future__ import annotations

from core.parameter_types import ParameterKind
from core.tree_model import build_path_map, build_tree, match_path


def _find(node, label):
    if node.label == label:
        return node
    for child in node.children:
        found = _find(child, label)
        if found is not None:
            return found
    return None


def test_build_tree_top_level(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    labels = {child.label for child in tree.children}
    assert {"Header", "Parameterisation", "State"} <= labels


def test_tree_classifies_known_nodes(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    cell = _find(tree, "Cell")
    assert cell.kind == ParameterKind.SECTION

    ocp = _find(tree, "OCP [V]")
    assert ocp.kind == ParameterKind.TABLE

    capacity = _find(tree, "Nominal cell capacity [A.h]")
    assert capacity.kind == ParameterKind.SCALAR
    assert capacity.unit == "A.h"
    assert capacity.description  # enriched from schema metadata


def test_match_path_handles_partial_loc(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    path_map = build_path_map(tree)
    # Validation loc omits the "Parameterisation" prefix and may carry a tag.
    loc = ("Cell", "Upper voltage cut-off [V]")
    node = match_path(path_map, loc)
    assert node is not None
    assert node.path == ("Parameterisation", "Cell", "Upper voltage cut-off [V]")
