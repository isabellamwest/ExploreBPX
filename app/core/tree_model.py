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
    looks_like_table,
)
from .validation import Severity, ValidatorDiagnostic


class NodeType(str, Enum):
    """How a navigable BPX object node was discovered."""

    STATIC = "static"
    DYNAMIC = "dynamic"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class SiblingSeries:
    """A read-only snapshot of a co-located experiment array.

    Carried on a Validation run's ``SERIES`` parameters so an editor can show
    the run's other arrays alongside (a length mismatch is visible while
    editing) and a CSV import can target all of them in one atomic command.
    A plain (label, path, value) triple rather than a reference to the sibling
    :class:`ParameterItem`: mutual item references would make the dataclass
    repr recurse and tie the editor to tree internals it must not mutate.
    """

    label: str
    path: tuple[str, ...]
    value: object


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
    #: For a ``MAP``-kind parameter, the sibling Particle names of the
    #: electrode named by ``FieldMeta.material_check`` (e.g. "Primary",
    #: "Secondary" for a blended electrode) -- a hint for per-material key
    #: entry, not a schema constraint. Empty for every other kind and for a
    #: single-particle (unblended) electrode.
    key_suggestions: tuple[str, ...] = ()
    #: For a ``SERIES`` parameter inside a Validation run, the run's *other*
    #: series arrays (e.g. Current/Voltage/Temperature beside Time). Seeded by
    #: ``_seed_sibling_series``; empty everywhere else.
    sibling_series: tuple[SiblingSeries, ...] = ()

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
    root = _build_node(root_label, (), raw)
    _seed_key_suggestions(root, raw)
    _seed_sibling_series(root)
    return root


def _build_node(
    label: str,
    path: tuple[str, ...],
    value: dict,
) -> TreeNode:
    meta = bpx_gateway.field_meta(path)
    node = TreeNode(
        label=label,
        path=path,
        node_type=_node_type(path),
        value=value,
        description=meta.description if meta else "",
    )

    for key, child_value in value.items():
        child_path = path + (key,)
        child_meta = bpx_gateway.field_meta(child_path)
        if is_object_node(child_value, child_meta):
            node.children.append(_build_node(key, child_path, child_value))
        else:
            node.parameters.append(_build_parameter(key, child_path, child_value, child_meta))
    return node


def is_object_node(value: object, meta: bpx_gateway.FieldMeta | None) -> bool:
    """True if *value* should render as a navigable tree section rather than
    a leaf parameter.

    Public (not module-private) so :mod:`core.compare` can mirror this exact
    section/parameter split when walking a raw dict for comparison, rather
    than duplicating the schema-vs-shape classification rule and risking the
    two drifting apart.

    When metadata is known, the schema's declaration is authoritative: a
    field is an object node only if the schema declares it a container link
    (``meta.is_container``) *and* the value is actually a dict -- a declared
    container holding a non-dict invalid value degrades to a parameter row
    (the validator reports it) rather than misclassifying it as a section.
    This keeps a per-material map field (e.g. a dict-valued "LAM: Positive
    electrode") a ``ParameterItem`` instead of turning it into a tree
    section, whatever it currently holds.

    When metadata is genuinely absent, value shape is the only information
    available (unchanged from before).
    """
    if meta is not None:
        return meta.is_container and isinstance(value, dict)
    return isinstance(value, dict) and not looks_like_table(value)


def _build_parameter(
    label: str,
    path: tuple[str, ...],
    value: object,
    meta: bpx_gateway.FieldMeta | None,
) -> ParameterItem:
    return ParameterItem(
        label=label,
        path=path,
        kind=classify(value, meta),
        value=value,
        unit=extract_unit(label),
        description=meta.description if meta else "",
        examples=meta.examples if meta else (),
    )


def _seed_key_suggestions(root: TreeNode, raw: dict) -> None:
    """Populate ``key_suggestions`` on every ``MAP``-kind parameter from the
    raw dict's Particle names, read once. A post-pass over the finished tree
    rather than threaded through ``_build_node``/``_build_parameter`` because
    it is a display hint over the result, not a classification input.
    """
    suggestions_by_material_check = {
        "positive_electrode": _particle_names(raw, "Positive electrode"),
        "negative_electrode": _particle_names(raw, "Negative electrode"),
    }

    def walk(node: TreeNode) -> None:
        for parameter in node.parameters:
            if parameter.kind is not ParameterKind.MAP:
                continue
            meta = bpx_gateway.field_meta(parameter.path)
            if meta is None:
                continue
            parameter.key_suggestions = suggestions_by_material_check.get(meta.material_check, ())
        for child in node.children:
            walk(child)

    walk(root)


def _seed_sibling_series(root: TreeNode) -> None:
    """Populate ``sibling_series`` on each SERIES parameter of a Validation run.

    Like ``_seed_key_suggestions``, a post-pass over the finished tree: it is a
    display/import hint over the result, not a classification input. Scoped to
    ``Validation/<run>`` nodes -- the one place the schema declares co-owned
    arrays -- so an undeclared list elsewhere never sprouts invented context.
    Sibling values are carried verbatim (whatever the run holds, valid or not);
    consumers render defensively and the validator keeps judging legality.
    """

    def walk(node: TreeNode) -> None:
        if len(node.path) == 2 and node.path[0] == "Validation":
            series = [p for p in node.parameters if p.kind is ParameterKind.SERIES]
            if len(series) >= 2:
                for parameter in series:
                    parameter.sibling_series = tuple(
                        SiblingSeries(other.label, other.path, other.value)
                        for other in series
                        if other is not parameter
                    )
        for child in node.children:
            walk(child)

    walk(root)


def _particle_names(raw: dict, electrode_label: str) -> tuple[str, ...]:
    """The blended-electrode Particle instance names for *electrode_label*
    (e.g. "Primary", "Secondary"), or ``()`` for a missing/single-particle/
    malformed shape. Defensive by design: this seeds a suggestion, not a
    schema requirement."""
    parameterisation = raw.get("Parameterisation")
    if not isinstance(parameterisation, dict):
        return ()
    electrode = parameterisation.get(electrode_label)
    if not isinstance(electrode, dict):
        return ()
    particle = electrode.get("Particle")
    if not isinstance(particle, dict):
        return ()
    return tuple(particle.keys())


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
