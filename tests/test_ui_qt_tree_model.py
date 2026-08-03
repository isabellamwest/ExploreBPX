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


def _model(
    root: TreeNode,
    expanded_paths: set[tuple[str, ...]] | None = None,
    visible_error_paths: frozenset[tuple[str, ...]] = frozenset(),
) -> BpxTreeModel:
    expanded_paths = expanded_paths or set()

    def is_expanded(index):
        return index.isValid() and index.internalPointer().path in expanded_paths

    return BpxTreeModel(root, is_expanded=is_expanded, visible_error_paths=visible_error_paths)


def _display(model: BpxTreeModel, index) -> str:
    return model.data(index, Qt.DisplayRole)


def _severity(model: BpxTreeModel, index) -> str | None:
    return model.data(index, SEVERITY_ROLE)


def _cell_under_parameterisation() -> TreeNode:
    cell = TreeNode(label="Cell", path=("Parameterisation", "Cell"))
    parameterisation = TreeNode(
        label="Parameterisation",
        path=("Parameterisation",),
        children=[cell],
    )
    return TreeNode(label="BPX File", path=(), children=[parameterisation])


_CELL_VISIBLE = frozenset({("Parameterisation", "Cell")})


def test_collapsed_node_marks_hidden_descendant_error():
    model = _model(_cell_under_parameterisation(), visible_error_paths=_CELL_VISIBLE)

    parameterisation_index = model.index(0, 0)

    assert _display(model, parameterisation_index) == "Parameterisation"
    assert _severity(model, parameterisation_index) == "error"


def test_expanded_node_defers_descendant_marker_to_visible_child():
    model = _model(
        _cell_under_parameterisation(),
        expanded_paths={("Parameterisation",)},
        visible_error_paths=_CELL_VISIBLE,
    )

    parameterisation_index = model.index(0, 0)
    cell_index = model.index(0, 0, parameterisation_index)

    assert _display(model, parameterisation_index) == "Parameterisation"
    assert _severity(model, parameterisation_index) is None
    assert _display(model, cell_index) == "Cell"
    assert _severity(model, cell_index) == "error"


def test_expanded_object_in_visible_set_keeps_marker():
    cell = TreeNode(label="Cell", path=("Cell",))
    root = TreeNode(label="BPX File", path=(), children=[cell])
    model = _model(root, expanded_paths={("Cell",)}, visible_error_paths=frozenset({("Cell",)}))

    cell_index = model.index(0, 0)

    assert _display(model, cell_index) == "Cell"
    assert _severity(model, cell_index) == "error"


def test_verbatim_issues_alone_never_light_the_marker():
    """Attached issues whose diagnostics were absorbed (e.g. every field
    merely empty) must NOT paint the tree dot. The marker reads only the
    page-visible set the partition derives -- the same truth as the
    parameter list and rail badge -- never
    ``node.issues``/``parameter.has_errors`` directly."""
    parameter = ParameterItem(
        label="Voltage",
        path=("Parameterisation", "Cell", "Voltage"),
        kind=ParameterKind.SCALAR,
        issues=[_error(("Parameterisation", "Cell", "Voltage"))],
    )
    cell = TreeNode(
        label="Cell",
        path=("Parameterisation", "Cell"),
        parameters=[parameter],
        issues=[_error(("Parameterisation", "Cell"))],
    )
    parameterisation = TreeNode(
        label="Parameterisation", path=("Parameterisation",), children=[cell]
    )
    root = TreeNode(label="BPX File", path=(), children=[parameterisation])
    model = _model(root)  # empty visible set; issues attached everywhere

    parameterisation_index = model.index(0, 0)
    assert _severity(model, parameterisation_index) is None  # collapsed rollup
    model_expanded = _model(root, expanded_paths={("Parameterisation",)})
    parameterisation_index = model_expanded.index(0, 0)
    cell_index = model_expanded.index(0, 0, parameterisation_index)
    assert _severity(model_expanded, cell_index) is None  # direct


# ----------------------------------------------------------------------
# The "· custom" tag: user-authored User-defined content reads apart from
# the fixed schema sections
# ----------------------------------------------------------------------

_UD = ("Parameterisation", "User-defined")


def _user_defined_model(sub_issue: bool = False):
    sub = TreeNode(label="Thermal tweaks", path=_UD + ("Thermal tweaks",))
    bucket = TreeNode(label="User-defined", path=_UD, children=[sub])
    parameterisation = TreeNode(
        label="Parameterisation", path=("Parameterisation",), children=[bucket]
    )
    root = TreeNode(label="BPX File", path=(), children=[parameterisation])
    visible = frozenset({_UD + ("Thermal tweaks",)}) if sub_issue else frozenset()
    model = _model(root, expanded_paths={("Parameterisation",), _UD}, visible_error_paths=visible)
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