"""Tests for object-tree generation and validation-path matching."""

from __future__ import annotations

from core.parameter_types import ParameterKind
from core.tree_model import (
    NodeType,
    ParameterItem,
    TreeNode,
    build_parameter_path_map,
    build_path_map,
    build_tree,
    match_parameter,
    match_path,
)
from core.validation import ValidationIssue


def _find(node, label):
    if node.label == label:
        return node
    for child in node.children:
        found = _find(child, label)
        if found is not None:
            return found
    return None


def _find_parameter(node, label):
    for parameter in node.parameters:
        if parameter.label == label:
            return parameter
    for child in node.children:
        found = _find_parameter(child, label)
        if found is not None:
            return found
    return None


def test_build_tree_top_level(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    labels = {child.label for child in tree.children}
    assert {"Header", "Parameterisation", "State"} <= labels


def test_tree_contains_object_nodes_not_parameter_leaves(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    cell = _find(tree, "Cell")
    assert cell is not None
    assert cell.kind == ParameterKind.SECTION
    assert cell.node_type == NodeType.STATIC

    capacity = _find(tree, "Nominal cell capacity [A.h]")
    assert capacity is None


def test_parameters_are_owned_by_object_nodes(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    cell = _find(tree, "Cell")
    assert cell is not None

    capacity = _find_parameter(cell, "Nominal cell capacity [A.h]")
    assert capacity is not None
    assert capacity.kind == ParameterKind.SCALAR
    assert capacity.unit == "A.h"
    assert capacity.description  # enriched from schema metadata

    ocp = _find_parameter(tree, "OCP [V]")
    assert ocp is not None
    assert ocp.kind == ParameterKind.TABLE


def test_dynamic_particle_nodes_are_generated_from_file(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    primary = _find(tree, "Primary")
    secondary = _find(tree, "Secondary")

    assert primary is not None
    assert primary.path == (
        "Parameterisation",
        "Positive electrode",
        "Particle",
        "Primary",
    )
    assert primary.node_type == NodeType.DYNAMIC
    assert secondary is not None


def test_match_path_handles_partial_loc(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    path_map = build_path_map(tree)
    # Validation loc omits the "Parameterisation" prefix and may carry a tag.
    loc = ("Cell", "Upper voltage cut-off [V]")
    node = match_path(path_map, loc)
    assert node is not None
    assert node.path == ("Parameterisation", "Cell")


def test_match_parameter_handles_partial_loc(valid_spm_dict):
    tree = build_tree(valid_spm_dict)
    parameter_map = build_parameter_path_map(tree)
    loc = ("Cell", "Upper voltage cut-off [V]")
    parameter = match_parameter(parameter_map, loc)
    assert parameter is not None
    assert parameter.path == ("Parameterisation", "Cell", "Upper voltage cut-off [V]")


def test_tree_node_distinguishes_direct_and_descendant_errors():
    parameter = ParameterItem(
        label="Voltage",
        path=("Cell", "Voltage"),
        kind=ParameterKind.SCALAR,
        issues=[ValidationIssue(path=("Cell", "Voltage"), message="Invalid")],
    )
    child = TreeNode(label="Cell", path=("Cell",), parameters=[parameter])
    root = TreeNode(label="BPX File", path=(), children=[child])

    assert child.has_errors
    assert not child.has_direct_errors
    assert child.has_direct_parameter_errors
    assert root.has_errors
    assert not root.has_direct_errors
    assert not root.has_direct_parameter_errors

    root.issues.append(ValidationIssue(path=(), message="Invalid root"))
    assert root.has_direct_errors
