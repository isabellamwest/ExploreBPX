"""Structure and capability queries (frontend-agnostic).

This is the single backend authority for *what the user may do here*: which
sections are removable, which are required for a model, and what model a raw
dict declares. The Qt frontend asks these questions rather than encoding BPX
structural rules itself.

V2 scope is deliberately small and durable: queries derive from the declared
``Header.Model`` plus the known top-level structure, not from a deep schema
walk. Container-aware parameter search lands later when add-parameter is wired,
isolated to this module so callers do not change.
"""

from __future__ import annotations

from . import bpx_gateway

#: Models that require a full electrolyte section.
_ELECTROLYTE_MODELS = frozenset({"SPMe", "DFN"})
#: Models that require a separator section.
_SEPARATOR_MODELS = frozenset({"DFN"})

#: Top-level sections that must always exist and can never be removed.
_PROTECTED_TOP_LEVEL = frozenset({"Header", "Parameterisation"})

#: Optional top-level sections a user may add to a document.
_OPTIONAL_TOP_LEVEL = ("State", "Validation")


def infer_model(raw: dict) -> str | None:
    """Return the declared model (``SPM``/``SPMe``/``DFN``/``Partial``) or None."""
    header = raw.get("Header") if isinstance(raw, dict) else None
    return header.get("Model") if isinstance(header, dict) else None


def model_requires_electrolyte(model: str | None) -> bool:
    return model in _ELECTROLYTE_MODELS


def model_requires_separator(model: str | None) -> bool:
    return model in _SEPARATOR_MODELS


def required_sections(model: str | None) -> tuple[tuple[str, ...], ...]:
    """Top-level/child sections expected for a model (excludes ``Partial``)."""
    if model == "Partial" or model is None:
        return (("Header",), ("Parameterisation",))
    sections: list[tuple[str, ...]] = [
        ("Header",),
        ("Parameterisation",),
        ("Parameterisation", "Cell"),
        ("Parameterisation", "Negative electrode"),
        ("Parameterisation", "Positive electrode"),
        ("State",),
    ]
    if model_requires_electrolyte(model):
        sections.append(("Parameterisation", "Electrolyte"))
    if model_requires_separator(model):
        sections.append(("Parameterisation", "Separator"))
    return tuple(sections)


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


def can_rename(path: tuple[str, ...]) -> bool:
    """Whether the key at ``path`` is a user-owned name.

    Only the schema's dict-keyed collections have user-named keys: Particle
    material instances (``.../Particle/<name>``) and Validation runs
    (``Validation/<name>``). Every other key is a schema property name and is
    never editable. Mirrors the tree's ``NodeType.DYNAMIC`` rule.
    """
    if len(path) >= 2 and path[-2] == "Particle":
        return True
    if len(path) == 2 and path[0] == "Validation":
        return True
    return False


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
    definition of its own). A path with no single schema definition -- notably
    the electrode sections, whose single/blended union needs live content to
    resolve -- degrades to ``()`` rather than guessing.
    """
    present = set(value) if isinstance(value, dict) else set()
    if not path:
        return available_top_level_additions(value if isinstance(value, dict) else {})
    try:
        fields = bpx_gateway.expected_fields(path, model)
    except ValueError:
        return ()
    return tuple(
        field.alias
        for field in fields
        if field.meta.is_container and field.alias not in present
    )
