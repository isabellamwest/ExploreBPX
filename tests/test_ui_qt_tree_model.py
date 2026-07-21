"""Tests for Qt tree warning marker placement."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

from core.parameter_types import ParameterKind
from core.tree_model import ParameterItem, TreeNode
from core.validation import PydanticErrorDiagnostic
from ui_qt.parameter_row import SEVERITY_ROLE
from ui_qt.tree_model import BpxTreeModel


def _error(path: tuple[str, ...]) -> PydanticErrorDiagnostic:
    return PydanticErrorDiagnostic(raw_error={"loc": path, "msg": "Invalid"})


def _model(root: TreeNode, expanded_paths: set[tuple[str, ...]] | None = None) -> BpxTreeModel:
    expanded_paths = expanded_paths or set()

    def is_expanded(index):
        return index.isValid() and index.internalPointer().path in expanded_paths

    return BpxTreeModel(root, is_expanded=is_expanded)


def _display(model: BpxTreeModel, index) -> str:
    return model.data(index, Qt.DisplayRole)


def _severity(model: BpxTreeModel, index) -> str | None:
    return model.data(index, SEVERITY_ROLE)


def test_collapsed_node_marks_hidden_descendant_error():
    parameter = ParameterItem(
        label="Voltage",
        path=("Parameterisation", "Cell", "Voltage"),
        kind=ParameterKind.SCALAR,
        issues=[_error(("Parameterisation", "Cell", "Voltage"))],
    )
    cell = TreeNode(label="Cell", path=("Parameterisation", "Cell"), parameters=[parameter])
    parameterisation = TreeNode(
        label="Parameterisation",
        path=("Parameterisation",),
        children=[cell],
    )
    root = TreeNode(label="BPX File", path=(), children=[parameterisation])
    model = _model(root)

    parameterisation_index = model.index(0, 0)

    assert _display(model, parameterisation_index) == "Parameterisation"
    assert _severity(model, parameterisation_index) == "error"


def test_expanded_node_defers_descendant_marker_to_visible_child():
    parameter = ParameterItem(
        label="Voltage",
        path=("Parameterisation", "Cell", "Voltage"),
        kind=ParameterKind.SCALAR,
        issues=[_error(("Parameterisation", "Cell", "Voltage"))],
    )
    cell = TreeNode(label="Cell", path=("Parameterisation", "Cell"), parameters=[parameter])
    parameterisation = TreeNode(
        label="Parameterisation",
        path=("Parameterisation",),
        children=[cell],
    )
    root = TreeNode(label="BPX File", path=(), children=[parameterisation])
    model = _model(root, expanded_paths={("Parameterisation",)})

    parameterisation_index = model.index(0, 0)
    cell_index = model.index(0, 0, parameterisation_index)

    assert _display(model, parameterisation_index) == "Parameterisation"
    assert _severity(model, parameterisation_index) is None
    assert _display(model, cell_index) == "Cell"
    assert _severity(model, cell_index) == "error"


def test_expanded_object_with_direct_parameter_error_keeps_marker():
    parameter = ParameterItem(
        label="Voltage",
        path=("Cell", "Voltage"),
        kind=ParameterKind.SCALAR,
        issues=[_error(("Cell", "Voltage"))],
    )
    cell = TreeNode(label="Cell", path=("Cell",), parameters=[parameter])
    root = TreeNode(label="BPX File", path=(), children=[cell])
    model = _model(root, expanded_paths={("Cell",)})

    cell_index = model.index(0, 0)

    assert _display(model, cell_index) == "Cell"
    assert _severity(model, cell_index) == "error"


def test_expanded_object_with_direct_object_error_keeps_marker():
    cell = TreeNode(label="Cell", path=("Cell",), issues=[_error(("Cell",))])
    root = TreeNode(label="BPX File", path=(), children=[cell])
    model = _model(root, expanded_paths={("Cell",)})

    cell_index = model.index(0, 0)

    assert _display(model, cell_index) == "Cell"
    assert _severity(model, cell_index) == "error"


# ----------------------------------------------------------------------
# The "· custom" tag: user-authored User-defined content reads apart from
# the fixed schema sections
# ----------------------------------------------------------------------

_UD = ("Parameterisation", "User-defined")


def _user_defined_model(sub_issue: bool = False):
    sub = TreeNode(
        label="Thermal tweaks",
        path=_UD + ("Thermal tweaks",),
        issues=[_error(_UD + ("Thermal tweaks",))] if sub_issue else [],
    )
    bucket = TreeNode(label="User-defined", path=_UD, children=[sub])
    parameterisation = TreeNode(
        label="Parameterisation", path=("Parameterisation",), children=[bucket]
    )
    root = TreeNode(label="BPX File", path=(), children=[parameterisation])
    model = _model(root, expanded_paths={("Parameterisation",), _UD})
    p_index = model.index(0, 0)
    bucket_index = model.index(0, 0, p_index)
    sub_index = model.index(0, 0, bucket_index)
    return model, bucket_index, sub_index


def test_user_defined_subsection_is_tagged_custom():
    model, bucket_index, sub_index = _user_defined_model()
    # The bucket keeps its fixed schema name; only its user-named content is tagged.
    assert _display(model, bucket_index) == "User-defined"
    assert _display(model, sub_index) == "Thermal tweaks · custom"


def test_custom_tag_and_error_marker_coexist():
    model, _bucket_index, sub_index = _user_defined_model(sub_issue=True)
    assert _display(model, sub_index) == "Thermal tweaks · custom"
    assert _severity(model, sub_index) == "error"


def test_material_is_not_tagged_custom():
    """A Particle material is renamable but not free-form, so it stays untagged
    -- the tag composes ``is_freeform_section`` with ``can_rename``, not
    ``can_rename`` alone."""
    material = TreeNode(
        label="Primary",
        path=("Parameterisation", "Positive electrode", "Particle", "Primary"),
    )
    particle = TreeNode(
        label="Particle",
        path=("Parameterisation", "Positive electrode", "Particle"),
        children=[material],
    )
    root = TreeNode(label="BPX File", path=(), children=[particle])
    model = _model(root, expanded_paths={("Parameterisation", "Positive electrode", "Particle")})
    particle_index = model.index(0, 0)
    material_index = model.index(0, 0, particle_index)
    assert _display(model, material_index) == "Primary"