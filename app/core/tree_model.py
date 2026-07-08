"""Builds a frontend-agnostic object tree from a raw BPX dictionary.

The tree is derived from the raw dict (the document's source of truth), so it
renders even when the file is invalid. Navigable tree nodes represent BPX
objects/sections; direct values owned by those objects are stored as
``ParameterItem`` rows for the inspector/editor surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from . import bpx_gateway
from .parameter_types import (
    ParameterKind,
    classify,
    extract_unit,
    icon_for,
    looks_like_table,
)
from .validation import Severity, ValidatorDiagnostic


class NodeType(str, Enum):
    """How a navigable BPX object node was discovered."""

    STATIC = "static"
    DYNAMIC = "dynamic"
    UNKNOWN = "unknown"


@dataclass
class ParameterItem:
    """A direct parameter owned by a navigable BPX object node."""

    label: str
    path: tuple[str, ...]
    kind: ParameterKind
    value: object = None
    unit: str = ""
    description: str = ""
    examples: tuple = ()
    issues: list[ValidatorDiagnostic] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return icon_for(self.kind)

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)


@dataclass
class TreeNode:
    """A navigable BPX object node in the explorer tree (UI-neutral)."""

    label: str
    path: tuple[str, ...]
    node_type: NodeType = NodeType.UNKNOWN
    value: object = None
    description: str = ""
    children: list["TreeNode"] = field(default_factory=list)
    parameters: list[ParameterItem] = field(default_factory=list)
    issues: list[ValidatorDiagnostic] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return icon_for(ParameterKind.SECTION)

    @property
    def is_section(self) -> bool:
        return True

    @property
    def has_errors(self) -> bool:
        return (
            any(issue.severity == Severity.ERROR for issue in self.issues)
            or any(parameter.has_errors for parameter in self.parameters)
            or any(child.has_errors for child in self.children)
        )

    @property
    def has_direct_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)

    @property
    def has_direct_parameter_errors(self) -> bool:
        return any(parameter.has_errors for parameter in self.parameters)

    @property
    def kind(self) -> ParameterKind:
        """Compatibility property for frontends expecting section-like nodes."""

        return ParameterKind.SECTION


_STATIC_PATHS = {
    (),
    ("Header",),
    ("Parameterisation",),
    ("Parameterisation", "Cell"),
    ("Parameterisation", "Electrolyte"),
    ("Parameterisation", "Negative electrode"),
    ("Parameterisation", "Negative electrode", "Particle"),
    ("Parameterisation", "Positive electrode"),
    ("Parameterisation", "Positive electrode", "Particle"),
    ("Parameterisation", "Separator"),
    ("State",),
    ("State", "Initial conditions"),
    ("State", "Thermal environment"),
    ("Validation",),
}


def build_tree(raw: dict, root_label: str = "BPX File") -> TreeNode:
    """Build the node tree for a raw BPX dictionary."""
    index = bpx_gateway.metadata_index()
    return _build_node(root_label, (), raw, index)


def _build_node(
    label: str,
    path: tuple[str, ...],
    value: dict,
    index: dict[str, bpx_gateway.FieldMeta],
) -> TreeNode:
    meta = index.get(label)
    node = TreeNode(
        label=label,
        path=path,
        node_type=_node_type(path),
        value=value,
        description=meta.description if meta else "",
    )

    for key, child_value in value.items():
        child_path = path + (key,)
        if _is_object_node(child_value):
            node.children.append(
                _build_node(key, child_path, child_value, index)
            )
        else:
            node.parameters.append(_build_parameter(key, child_path, child_value, index))
    return node


def _is_object_node(value: object) -> bool:
    return isinstance(value, dict) and not looks_like_table(value)


def _build_parameter(
    label: str,
    path: tuple[str, ...],
    value: object,
    index: dict[str, bpx_gateway.FieldMeta],
) -> ParameterItem:
    meta = index.get(label)
    return ParameterItem(
        label=label,
        path=path,
        kind=classify(value, meta),
        value=value,
        unit=extract_unit(label),
        description=meta.description if meta else "",
        examples=meta.examples if meta else (),
    )


def _node_type(path: tuple[str, ...]) -> NodeType:
    if path in _STATIC_PATHS:
        return NodeType.STATIC
    if len(path) >= 2 and path[-2] == "Particle":
        return NodeType.DYNAMIC
    if len(path) == 2 and path[0] == "Validation":
        return NodeType.DYNAMIC
    return NodeType.UNKNOWN


def build_path_map(root: TreeNode) -> dict[tuple[str, ...], TreeNode]:
    """Map every visible object node's full path to the node, for O(1) lookup."""

    out: dict[tuple[str, ...], TreeNode] = {}

    def walk(node: TreeNode) -> None:
        out[node.path] = node
        for child in node.children:
            walk(child)

    walk(root)
    return out


def build_parameter_path_map(root: TreeNode) -> dict[tuple[str, ...], ParameterItem]:
    """Map every direct parameter's full path to the parameter item."""

    out: dict[tuple[str, ...], ParameterItem] = {}

    def walk(node: TreeNode) -> None:
        for parameter in node.parameters:
            out[parameter.path] = parameter
        for child in node.children:
            walk(child)

    walk(root)
    return out


def _contains_slice(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    size = len(needle)
    if size == 0:
        return False
    for start in range(len(haystack) - size + 1):
        if haystack[start : start + size] == needle:
            return True
    return False


def match_path(
    path_map: dict[tuple[str, ...], TreeNode],
    loc: tuple[str, ...],
) -> TreeNode | None:
    """Best-effort match of a validation ``loc`` to a visible object node.

    Validation locations omit the section prefix (e.g. ``Parameterisation``), so
    an exact lookup is tried first, then the node whose path shares the longest
    trailing run of keys that appears contiguously within ``loc``.
    """
    if not loc:
        return None
    if loc in path_map:
        return path_map[loc]

    best: TreeNode | None = None
    best_len = 0
    for node in path_map.values():
        node_path = node.path
        for length in range(len(node_path), 0, -1):
            if _contains_slice(loc, node_path[-length:]):
                if length > best_len:
                    best_len = length
                    best = node
                break
    return best


def match_parameter(
    parameter_map: dict[tuple[str, ...], ParameterItem],
    loc: tuple[str, ...],
) -> ParameterItem | None:
    """Best-effort match of a validation ``loc`` to a direct parameter item.

    A match on the leaf key alone (length 1) is only trusted when ``loc``
    itself carries no further context to disambiguate against. When ``loc``
    names a parent (e.g. an electrode) that the candidate parameter does not
    share, a leaf-only match is almost always a same-named sibling elsewhere
    in the tree rather than the diagnostic's real target -- most notably for
    ``missing`` diagnostics, whose target parameter does not exist at all.
    Returning ``None`` in that case lets the caller fall back to attaching
    the diagnostic to the nearest existing ancestor node instead.
    """

    if not loc:
        return None
    if loc in parameter_map:
        return parameter_map[loc]

    best: ParameterItem | None = None
    best_len = 0
    for parameter in parameter_map.values():
        parameter_path = parameter.path
        for length in range(len(parameter_path), 0, -1):
            if _contains_slice(loc, parameter_path[-length:]):
                if length > best_len:
                    best_len = length
                    best = parameter
                break
    if best_len == 1 and len(loc) > 1:
        return None
    return best
