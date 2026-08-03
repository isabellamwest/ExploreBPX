"""Structure and capability queries (frontend-agnostic).

This is the single backend authority for *what the user may do here*: which
sections are removable, which are required for a model, and what model a raw
dict declares. The Qt frontend asks these questions rather than encoding BPX
structural rules itself.

Deliberately small and durable: queries derive from the declared
``Header.Model`` plus the known top-level structure, not from a deep schema
walk. Container-aware parameter search lands later when add-parameter is
wired, isolated to this module so callers do not change.
"""

from __future__ import annotations

from functools import lru_cache

from . import bpx_gateway, parameter_types

#: Top-level sections that must always exist and can never be removed.
_PROTECTED_TOP_LEVEL = frozenset({"Header", "Parameterisation"})

#: Optional top-level sections a user may add to a document.
_OPTIONAL_TOP_LEVEL = ("State", "Validation")

#: The single BPX free-form authoring bucket. Its ``UserDefined`` schema
#: definition is open (``additionalProperties: True``), so its descendants are
#: the only Parameterisation content the user names and shapes freely --
#: everywhere else keys are fixed schema property names.
_USER_DEFINED = ("Parameterisation", "User-defined")


def infer_model(raw: dict) -> str | None:
    """Return the declared model (``SPM``/``SPMe``/``DFN``/``Partial``) or None."""
    header = raw.get("Header") if isinstance(raw, dict) else None
    return header.get("Model") if isinstance(header, dict) else None


@lru_cache(maxsize=None)
def _required_parameterisation_children(model: str | None) -> tuple[str, ...]:
    """Child sections the schema's own ``Parameterisation`` shape for *model*
    marks required, in schema declaration order.

    Derived live through the gateway, never restated here: ``Partial``, an
    undeclared model, and any model this app has never heard of all resolve
    to the partial shape, whose ``required`` list is empty.
    """
    return tuple(
        f.alias
        for f in bpx_gateway.expected_fields(("Parameterisation",), model)
        if f.required
    )


def required_sections(model: str | None) -> tuple[tuple[str, ...], ...]:
    """Top-level/child sections the validator actually requires for a model
    (excludes ``Partial``).

    The ``Parameterisation`` children come straight from the schema's own
    ``required`` list for the model's shape (schema order), so a ``bpx``
    change moves this list automatically. ``State`` is NOT here: bpx 1.1.1
    made it optional (``schema.py``'s ``State`` field is
    ``Field(None, alias="State")``) and deleted the root validator that used
    to demand it. The two root sections are the schema root's own
    ``required`` list, pinned by :mod:`tests.test_spec_literals_contract`
    (the gateway exposes no root-properties query yet).
    """
    children = _required_parameterisation_children(model)
    return (("Header",), ("Parameterisation",)) + tuple(
        ("Parameterisation", child) for child in children
    )


def can_remove(path: tuple[str, ...]) -> bool:
    """Whether the object at ``path`` may be removed structurally."""
    if not path:
        return False
    if len(path) == 1 and path[0] in _PROTECTED_TOP_LEVEL:
        return False
    return True


def available_top_level_additions(raw: dict) -> tuple[str, ...]:
    """Optional top-level sections not yet present in the document."""
    present = set(raw) if isinstance(raw, dict) else set()
    return tuple(name for name in _OPTIONAL_TOP_LEVEL if name not in present)


def _within_user_defined(path: tuple[str, ...]) -> bool:
    """True for a node strictly *inside* the User-defined bucket -- not the
    bucket itself, whose name is the fixed ``User-defined`` schema property."""
    return len(path) > len(_USER_DEFINED) and path[: len(_USER_DEFINED)] == _USER_DEFINED


def can_rename(path: tuple[str, ...]) -> bool:
    """Whether the key at ``path`` is a user-owned name.

    User-named keys are: Particle material instances (``.../Particle/<name>``),
    Validation runs (``Validation/<name>``), and anything the user authored
    inside the open ``User-defined`` bucket (subsections and parameters at any
    depth). Every other key is a fixed schema property name and is never
    editable. Mirrors the tree's ``NodeType.DYNAMIC`` rule plus the free-form
    User-defined content.
    """
    if len(path) >= 2 and path[-2] == "Particle":
        return True
    if len(path) == 2 and path[0] == "Validation":
        return True
    if _within_user_defined(path):
        return True
    return False


def can_duplicate(path: tuple[str, ...]) -> bool:
    """Whether the key at ``path`` may be duplicated.

    Duplication is allowed exactly where renaming is: Particle materials,
    Validation runs, and User-defined content -- a duplicate is itself a new
    user-owned name, so it can only exist where the user is already free to
    name things. See :func:`can_rename`.
    """
    return can_rename(path)


def _is_schema_undefined_leaf(path: tuple[str, ...], value: object) -> bool:
    """True when *path* names a parameter LEAF (never a section) that the BPX
    schema defines nowhere. ``field_meta`` being ``None`` is not sufficient on
    its own -- it is equally ``None`` for a schema SECTION path -- so the
    value is classified with the same no-metadata rule the tree uses to keep
    a section out of the parameter list (see ``ui_qt.tree_model``'s object-node
    check / :func:`parameter_types.classify`): a bare, non-table dict is a
    SECTION, everything else is a leaf. Deliberately NOT
    ``ParameterMetadata.is_custom``, which also requires an absent
    technical-description entry (a docs concern); this is a rename-legality
    concern and must not block an undocumented-but-real field.
    """
    if bpx_gateway.field_meta(path) is not None:
        return False
    return parameter_types.classify(value, None) != parameter_types.ParameterKind.SECTION


def can_rename_parameter(path: tuple[str, ...], value: object) -> bool:
    """Whether the parameter LEAF at ``path`` may be renamed: :func:`can_rename`'s
    positional rule, OR a leaf the schema defines nowhere (a user-authored
    custom parameter -- legal in any section now, not only User-defined --
    or an alias we genuinely don't recognise, treated the same). Never call
    this for a tree/section node; use :func:`can_rename` there.
    """
    return can_rename(path) or _is_schema_undefined_leaf(path, value)


def can_duplicate_parameter(path: tuple[str, ...], value: object) -> bool:
    """Mirrors :func:`can_rename_parameter`; see its docstring."""
    return can_rename_parameter(path, value)


def is_particle_material(path: tuple[str, ...]) -> bool:
    """Whether ``path`` names a Particle material instance
    (``.../Particle/<name>``) -- the one renamable key whose old name may
    still be referenced elsewhere in the raw dict (a per-material MAP key,
    e.g. under a Degradation field) after a rename, since ``RenameKey``
    deliberately does not rewrite those references (the validator reports
    the mismatch, the app invents nothing). Validation runs and User-defined
    content are never referenced by name elsewhere, so this is False for
    them. Used only to decide whether the rename UI shows a note about this;
    it plays no part in whether the rename itself is legal (see
    :func:`can_rename`).
    """
    return len(path) >= 2 and path[-2] == "Particle"


def is_freeform_section(path: tuple[str, ...]) -> bool:
    """Whether *path* is a place the user may freely add named subsections and
    parameters: the ``User-defined`` bucket and any subsection within it.

    Unlike the single-noun dict-keyed collections (see
    :func:`named_child_noun`), the schema's ``UserDefined`` definition is open
    (``additionalProperties: True``), so both a named *section* and a named
    *parameter* are legal here -- which is why this drives two menu actions
    ("Add subsection…" / "Add parameter…") rather than one.
    """
    return path == _USER_DEFINED or _within_user_defined(path)


def named_child_noun(path: tuple[str, ...]) -> str | None:
    """The noun for "Add <noun>…" on a dict-keyed container, or ``None``.

    A ``Particle`` container holds user-named materials; ``Validation`` holds
    user-named experiments. These are the only two places the schema lets the
    user *create a name*; everywhere else children are schema-fixed sections.
    """
    if path and path[-1] == "Particle":
        return "material"
    if path == ("Validation",):
        return "experiment"
    return None


def addable_child_sections(
    path: tuple[str, ...], value: object, model: str | None = None
) -> tuple[str, ...]:
    """Schema-expected child *sections* absent from the object at ``path``.

    The source is the live schema (``bpx_gateway.expected_fields``), so the
    menu can never offer a section the schema does not declare. The document
    root offers the optional top-level sections instead (it has no schema
    definition of its own). ``value`` is also passed to ``expected_fields``,
    which needs it to discriminate the electrode sections' single/blended
    union (no longer a genuine fallback case). A path still has no single
    schema definition for the user-named dict-keyed collections themselves --
    a ``Particle`` container, or the ``Validation`` collection at
    ``("Validation",)`` (its named runs, ``("Validation", <name>)``, do
    resolve, to ``Experiment``) -- those offer "Add material…"/"Add
    experiment…" instead (see :func:`named_child_noun`), never "Add
    section", so this degrades to ``()`` for them rather than raising.
    """
    present = set(value) if isinstance(value, dict) else set()
    if not path:
        return available_top_level_additions(value if isinstance(value, dict) else {})
    try:
        fields = bpx_gateway.expected_fields(path, model, value)
    except ValueError:
        return ()
    return tuple(
        field.alias
        for field in fields
        if field.meta.is_container and field.alias not in present
    )
