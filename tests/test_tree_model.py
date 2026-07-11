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
from core.validation import PydanticErrorDiagnostic


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
    # OCP is declared allows_function; the union is one kind (FUNCTION)
    # regardless of the stored value's own shape (here, an {x, y} table).
    assert ocp.kind == ParameterKind.FUNCTION


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
        issues=[PydanticErrorDiagnostic(raw_error={"loc": ("Cell", "Voltage"), "msg": "Invalid"})],
    )
    child = TreeNode(label="Cell", path=("Cell",), parameters=[parameter])
    root = TreeNode(label="BPX File", path=(), children=[child])

    assert child.has_errors
    assert not child.has_direct_errors
    assert child.has_direct_parameter_errors
    assert root.has_errors
    assert not root.has_direct_errors
    assert not root.has_direct_parameter_errors

    root.issues.append(PydanticErrorDiagnostic(raw_error={"loc": (), "msg": "Invalid root"}))
    assert root.has_direct_errors


# ---------------------------------------------------------------------------
# Tree boundary: a field the schema declares a leaf value is always a
# ParameterItem, never a TreeNode, whatever it currently holds. Container-link
# fields (Cell, Particle, ...) stay TreeNodes when their value is a dict; a
# value-less/malformed one degrades to a parameter row instead of crashing.
# ---------------------------------------------------------------------------


def test_tree_boundary_declared_container_with_dict_value_stays_tree_node(valid_spm_dict):
    """("Parameterisation", "Cell") -- a declared container link holding a
    dict -- is still a TreeNode."""
    tree = build_tree(valid_spm_dict)
    path_map = build_path_map(tree)
    assert ("Parameterisation", "Cell") in path_map


def test_tree_boundary_per_material_map_is_a_parameter_not_a_section(valid_spm_dict):
    """A dict-valued per-material field (allows_map) must stay a
    ParameterItem of kind MAP, never become a tree section -- the exact bug
    this phase fixes. The SPM fixture already has a blended-electrode
    hysteresis-state dict here."""
    tree = build_tree(valid_spm_dict)
    path = ("State", "Initial conditions", "Initial hysteresis state: Positive electrode")
    path_map = build_path_map(tree)
    parameter_map = build_parameter_path_map(tree)

    assert path not in path_map  # never a TreeNode
    parameter = parameter_map[path]
    assert parameter.kind == ParameterKind.MAP
    assert parameter.value == {"Primary": 1.0, "Secondary": 1.0}


def test_tree_boundary_validation_run_dict_stays_tree_node(valid_spm_dict):
    """("Validation", "<run>") has no schema meta (Validation is not a
    _SECTION_DEFS entry as a 2-tuple path itself); the shape rule alone must
    still make a run dict a TreeNode."""
    raw = dict(valid_spm_dict)
    raw["Validation"] = {
        "1C discharge": {
            "Time [s]": [0, 1, 2],
            "Current [A]": [1, 1, 1],
            "Voltage [V]": [4.2, 4.1, 4.0],
        }
    }
    tree = build_tree(raw)
    path_map = build_path_map(tree)
    assert ("Validation", "1C discharge") in path_map


def test_tree_boundary_particle_instance_nodes_stay_tree_nodes_under_blended_electrode(
    valid_spm_dict,
):
    """A named blended-particle instance (e.g. "Primary") has no schema
    meta of its own (the name is arbitrary, not an alias) -- the shape rule
    alone must still make it a TreeNode."""
    tree = build_tree(valid_spm_dict)
    path_map = build_path_map(tree)
    assert ("Parameterisation", "Positive electrode", "Particle", "Primary") in path_map
    assert ("Parameterisation", "Positive electrode", "Particle", "Secondary") in path_map


def test_tree_boundary_ocp_table_value_is_a_function_parameter(valid_spm_dict):
    """OCP [V] (allows_function) holding an {x, y} dict classifies FUNCTION,
    not TABLE -- the declared union is one kind."""
    tree = build_tree(valid_spm_dict)
    parameter_map = build_parameter_path_map(tree)
    ocp = parameter_map[("Parameterisation", "Negative electrode", "OCP [V]")]
    assert ocp.kind == ParameterKind.FUNCTION
    assert isinstance(ocp.value, dict)


def test_tree_boundary_user_defined_children_classify_by_shape(valid_spm_dict):
    """User-defined has no schema-known children (meta=None for any custom
    alias under it), so the meta=None shape fallback applies: dict -> a
    SECTION tree node, str -> TEXT, bool -> BOOLEAN."""
    raw = dict(valid_spm_dict)
    raw["Parameterisation"] = dict(valid_spm_dict["Parameterisation"])
    raw["Parameterisation"]["User-defined"] = {
        "Notes": {"Author": "A. Person"},
        "Supplier": "Acme Cells",
        "Verified": True,
    }
    tree = build_tree(raw)
    path_map = build_path_map(tree)
    parameter_map = build_parameter_path_map(tree)

    assert ("Parameterisation", "User-defined", "Notes") in path_map  # dict -> section

    supplier = parameter_map[("Parameterisation", "User-defined", "Supplier")]
    assert supplier.kind == ParameterKind.TEXT

    verified = parameter_map[("Parameterisation", "User-defined", "Verified")]
    assert verified.kind == ParameterKind.BOOLEAN


# ---------------------------------------------------------------------------
# key_suggestions seeding for MAP-kind parameters.
# ---------------------------------------------------------------------------


def test_key_suggestions_seeded_from_blended_electrode_particle_names(valid_spm_dict):
    """The Positive electrode is blended (Primary/Secondary particles) in the
    SPM fixture, so its material_check="positive_electrode" MAP parameter
    gets those names as key_suggestions."""
    tree = build_tree(valid_spm_dict)
    parameter_map = build_parameter_path_map(tree)
    hysteresis = parameter_map[
        ("State", "Initial conditions", "Initial hysteresis state: Positive electrode")
    ]
    assert hysteresis.key_suggestions == ("Primary", "Secondary")


def test_key_suggestions_empty_for_single_particle_electrode(valid_spm_dict):
    """The Negative electrode is single-particle (no "Particle" dict) in the
    SPM fixture, so its material_check="negative_electrode" MAP parameter
    gets no key suggestions."""
    tree = build_tree(valid_spm_dict)
    parameter_map = build_parameter_path_map(tree)
    hysteresis = parameter_map[
        ("State", "Initial conditions", "Initial hysteresis state: Negative electrode")
    ]
    assert hysteresis.key_suggestions == ()


# ---------------------------------------------------------------------------
# sibling_series seeding for a Validation run's SERIES parameters.
# ---------------------------------------------------------------------------


def _with_validation_run(valid_spm_dict, arrays):
    doc = dict(valid_spm_dict)
    doc["Validation"] = {"C/20 discharge": arrays}
    return doc


def test_sibling_series_seeded_for_validation_run(valid_spm_dict):
    """Each of a run's four arrays carries the other three -- label, path and
    verbatim value -- so an editor can show them and CSV import can target
    them, without referencing the sibling ParameterItems themselves."""
    doc = _with_validation_run(
        valid_spm_dict,
        {
            "Time [s]": [0, 100, 200],
            "Current [A]": [-0.6, -0.6, -0.6],
            "Voltage [V]": [4.1, 4.0, 3.9],
            "Temperature [K]": [298.15, 298.15, 298.15],
        },
    )
    tree = build_tree(doc)
    parameter_map = build_parameter_path_map(tree)
    time = parameter_map[("Validation", "C/20 discharge", "Time [s]")]
    assert [s.label for s in time.sibling_series] == [
        "Current [A]",
        "Voltage [V]",
        "Temperature [K]",
    ]
    voltage = next(s for s in time.sibling_series if s.label == "Voltage [V]")
    assert voltage.path == ("Validation", "C/20 discharge", "Voltage [V]")
    assert voltage.value == [4.1, 4.0, 3.9]
    # The value is carried, never re-derived: whatever the run holds.
    current = parameter_map[("Validation", "C/20 discharge", "Current [A]")]
    assert [s.label for s in current.sibling_series] == [
        "Time [s]",
        "Voltage [V]",
        "Temperature [K]",
    ]


def test_sibling_series_not_seeded_outside_validation(valid_spm_dict):
    """An undeclared list elsewhere (kind SERIES by shape) gets no invented
    context: seeding is scoped to Validation/<run> nodes."""
    doc = dict(valid_spm_dict)
    doc["Parameterisation"] = dict(valid_spm_dict["Parameterisation"])
    doc["Parameterisation"]["User-defined"] = {
        "List A": [1, 2],
        "List B": [3, 4],
    }
    tree = build_tree(doc)
    parameter_map = build_parameter_path_map(tree)
    assert parameter_map[("Parameterisation", "User-defined", "List A")].sibling_series == ()


def test_sibling_series_needs_a_second_series(valid_spm_dict):
    """A run holding a single array has nothing to show alongside it."""
    doc = _with_validation_run(valid_spm_dict, {"Time [s]": [0, 100]})
    tree = build_tree(doc)
    parameter_map = build_parameter_path_map(tree)
    assert parameter_map[("Validation", "C/20 discharge", "Time [s]")].sibling_series == ()
