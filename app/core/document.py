"""In-memory BPX document model (frontend-agnostic).

The raw dictionary is the single source of truth: it can represent any file,
including invalid ones and (in future) intermediate editing states. The parsed
BPX model and validation issues are *derived* from it.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import bpx_gateway
from .tree_model import (
    TreeNode,
    build_path_map,
    build_tree,
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
    _path_map: dict[tuple[str, ...], TreeNode] = field(
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
        path_map = build_path_map(tree)
        document = cls(
            filename=filename,
            fmt=fmt,
            raw=raw,
            tree=tree,
            issues=result.issues,
            is_valid=result.is_valid,
            _path_map=path_map,
        )
        document._attach_issues()
        return document

    def _attach_issues(self) -> None:
        for issue in self.issues:
            target = match_path(self._path_map, issue.path) or self.tree
            target.issues.append(issue)

    @property
    def error_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == Severity.ERROR)

    @property
    def warning_count(self) -> int:
        return sum(1 for issue in self.issues if issue.severity == Severity.WARNING)

    def find(self, path: tuple[str, ...]) -> TreeNode | None:
        """Return the node at an exact path, if it exists."""
        return self._path_map.get(tuple(path))

    def find_best(self, path: tuple[str, ...]) -> TreeNode | None:
        """Return the best-effort node match for a (possibly partial) path."""
        return match_path(self._path_map, tuple(path))
