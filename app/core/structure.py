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
