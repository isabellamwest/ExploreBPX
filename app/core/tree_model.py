"""Builds a frontend-agnostic node tree from a raw BPX dictionary.

The tree is derived from the raw dict (the document's source of truth), so it
renders even when the file is invalid. Each node is enriched with schema
metadata (description, unit) and classified into a :class:`ParameterKind`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import bpx_gateway
from .parameter_types import ParameterKind, classify, extract_unit, icon_for
from .validation import Severity, ValidationIssue


@dataclass
class TreeNode:
    """A single node in the BPX explorer tree (UI-neutral)."""

    label: str
    path: tuple[str, ...]
    kind: ParameterKind
    value: object = None
    unit: str = ""
    description: str = ""
    examples: tuple = ()
    children: list["TreeNode"] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def icon(self) -> str:
        return icon_for(self.kind)

    @property
    def is_section(self) -> bool:
        return self.kind == ParameterKind.SECTION

    @property
    def has_errors(self) -> bool:
        return any(issue.severity == Severity.ERROR for issue in self.issues)


def build_tree(raw: dict, root_label: str = "BPX File") -> TreeNode:
    """Build the node tree for a raw BPX dictionary."""
    index = bpx_gateway.metadata_index()
    return _build_node(root_label, (), raw, index)


def _build_node(
    label: str,
    path: tuple[str, ...],
    value: object,
    index: dict[str, bpx_gateway.FieldMeta],
) -> TreeNode:
    meta = index.get(label)
    kind = classify(value, meta)
    node = TreeNode(
        label=label,
        path=path,
        kind=kind,
        value=value,
        unit=extract_unit(label),
        description=meta.description if meta else "",
        examples=meta.examples if meta else (),
    )
    if kind == ParameterKind.SECTION and isinstance(value, dict):
        for key, child_value in value.items():
            node.children.append(
                _build_node(key, path + (key,), child_value, index)
            )
    return node


def build_path_map(root: TreeNode) -> dict[tuple[str, ...], TreeNode]:
    """Map every node's full path to the node, for O(1) lookup."""
    out: dict[tuple[str, ...], TreeNode] = {}

    def walk(node: TreeNode) -> None:
        out[node.path] = node
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
    """Best-effort match of a (possibly partial) validation ``loc`` to a node.

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
