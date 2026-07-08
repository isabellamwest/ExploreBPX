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
from .validation import PydanticErrorDiagnostic, Severity, ValidatorDiagnostic


# Navigation constants: Pydantic union-type discriminator suffixes that are
# artefacts of validation mechanics, not data-path components.  These are
# stripped only when deriving a navigation path for tree matching.
_NAV_STRIP_TAGS = frozenset({
    "float", "int", "str", "bool", "number", "integer", "boolean", "string",
    "function-after", "function-before", "is-instance",
})


def _derive_nav_path(loc: tuple[str, ...]) -> tuple[str, ...]:
    """Derive a tree-navigation path from a Pydantic loc tuple.

    Strips trailing union-discriminator tags that are artefacts of Pydantic
    union validation, leaving only the data-path components.
    """
    cleaned = list(loc)
    while cleaned and cleaned[-1] in _NAV_STRIP_TAGS:
        cleaned.pop()
    return tuple(cleaned)


def _nav_path_for(issue: ValidatorDiagnostic) -> tuple[str, ...]:
    """Derive a navigation path from a diagnostic for tree-matching."""
    if isinstance(issue, PydanticErrorDiagnostic):
        return _derive_nav_path(issue.loc)
    return ()


@dataclass(frozen=True)
class DocumentIdentity:
    """Identity fields read from a BPX document's Header.

    Frontend-agnostic: both the top bar and the Workspace info panel read
    identity through this value object rather than the raw dict, keeping
    knowledge of the BPX Header shape inside ``core``.
    """

    title: str
    model: str
    bpx_version: str


def _identity_from_raw(raw: dict) -> DocumentIdentity:
    header = raw.get("Header") or {}
    title = header.get("Title") or ""
    model = header.get("Model") or ""
    bpx_version = header.get("BPX") or ""
    return DocumentIdentity(
        title=str(title),
        model=str(model),
        bpx_version=str(bpx_version),
    )


@dataclass
class BPXDocument:
    """A loaded BPX file plus its derived tree and validation state."""

    filename: str
    fmt: str
    raw: dict
    tree: TreeNode
    issues: list[ValidatorDiagnostic] = field(default_factory=list)
    is_valid: bool = False
    _node_path_map: dict[tuple[str, ...], TreeNode] = field(
        default_factory=dict, repr=False
    )
    _parameter_path_map: dict[tuple[str, ...], ParameterItem] = field(
        default_factory=dict, repr=False
    )
    _issue_nav_paths: list[tuple[str, ...]] = field(default_factory=list, repr=False)

    @classmethod
    def from_bytes(cls, data: bytes | str, filename: str) -> "BPXDocument":
        """Load, validate and build the tree for raw file bytes.

        Raises :class:`core.bpx_gateway.LoadError` only if the bytes are not
        decodable JSON/YAML; schema-invalid files still load successfully.
        """
        raw, fmt = bpx_gateway.load_raw(data, filename)
        return cls.from_raw(raw, filename=filename, fmt=fmt)

    @classmethod
    def from_raw(cls, raw: dict, filename: str, fmt: str) -> "BPXDocument":
        """Build a document from an already-decoded raw dict.

        Validation, tree building and issue attachment are identical to
        :meth:`from_bytes`; this is the rebuild path after an edit, where the
        raw dict (the source of truth) has already been mutated.
        """
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
            nav_path = _nav_path_for(issue)
            self._issue_nav_paths.append(nav_path)

            parameter = match_parameter(self._parameter_path_map, nav_path)
            if parameter is not None:
                parameter.issues.append(issue)

            target = match_path(self._node_path_map, nav_path) or self.tree
            if parameter is None:
                target.issues.append(issue)

    def iter_issues(self) -> list[tuple[ValidatorDiagnostic, tuple[str, ...]]]:
        """Return ``(diagnostic, nav_path)`` pairs for all document issues."""
        return list(zip(self.issues, self._issue_nav_paths))

    @property
    def identity(self) -> DocumentIdentity:
        """Return the document's identity (Title, Model, BPX version)."""
        return _identity_from_raw(self.raw)

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
