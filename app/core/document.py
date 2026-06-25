"""In-memory BPX document model (frontend-agnostic).

The raw dictionary is the single source of truth: it can represent any file,
including invalid ones and (in future) intermediate editing states. The parsed
BPX model and validation issues are *derived* from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import bpx_gateway
from .tree_model import (
    ParameterItem,
    TreeNode,
    build_parameter_path_map,
    build_path_map,
    build_tree,
    match_parameter,
    match_path,
)
from .validation import Severity, ValidationIssue


@dataclass
class BPXDocument:
    """A loaded BPX file plus its derived tree and validation state."""

    filename: str
    fmt: str
    raw: dict
    tree: TreeNode
    issues: list[ValidationIssue] = field(default_factory=list)
    is_valid: bool = False
    _node_path_map: dict[tuple[str, ...], TreeNode] = field(
        default_factory=dict, repr=False
    )
    _parameter_path_map: dict[tuple[str, ...], ParameterItem] = field(
        default_factory=dict, repr=False
    )

    @classmethod
    def from_bytes(cls, data: bytes | str, filename: str) -> "BPXDocument":
        """Load, validate and build the tree for raw file bytes.

        Raises :class:`core.bpx_gateway.LoadError` only if the bytes are not
        decodable JSON/YAML; schema-invalid files still load successfully.
        """
        raw, fmt = bpx_gateway.load_raw(data, filename)
        result = bpx_gateway.validate(raw)
        tree = build_tree(raw)
        node_path_map = build_path_map(tree)
        parameter_path_map = build_parameter_path_map(tree)
        document = cls(
            filename=filename,
            fmt=fmt,
            raw=raw,
            tree=tree,
            issues=result.issues,
            is_valid=result.is_valid,
            _node_path_map=node_path_map,
            _parameter_path_map=parameter_path_map,
        )
        document._attach_issues()
        return document

    def _attach_issues(self) -> None:
        for issue in self.issues:
            parameter = match_parameter(self._parameter_path_map, issue.path)
            if parameter is not None:
                parameter.issues.append(issue)

            target = match_path(self._node_path_map, issue.path) or self.tree
            if parameter is None:
                target.issues.append(issue)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == Severity.WARNING)

    def find(self, path: tuple[str, ...]) -> TreeNode | None:
        """Return the visible object node at an exact path, if it exists."""
        return self._node_path_map.get(tuple(path))

    def find_best(self, path: tuple[str, ...]) -> TreeNode | None:
        """Return the best-effort visible object node match for a path."""
        return match_path(self._node_path_map, tuple(path))

    def find_parameter(self, path: tuple[str, ...]) -> ParameterItem | None:
        """Return the direct parameter item at an exact path, if it exists."""
        return self._parameter_path_map.get(tuple(path))

    def find_best_parameter(self, path: tuple[str, ...]) -> ParameterItem | None:
        """Return the best-effort direct parameter match for a path."""
        return match_parameter(self._parameter_path_map, tuple(path))
