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

    assert _display(model, parameterisation_index) == "Parameterisation ⚠"


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
    assert _display(model, cell_index) == "Cell ⚠"


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

    assert _display(model, cell_index) == "Cell ⚠"


def test_expanded_object_with_direct_object_error_keeps_marker():
    cell = TreeNode(label="Cell", path=("Cell",), issues=[_error(("Cell",))])
    root = TreeNode(label="BPX File", path=(), children=[cell])
    model = _model(root, expanded_paths={("Cell",)})

    cell_index = model.index(0, 0)

    assert _display(model, cell_index) == "Cell ⚠"