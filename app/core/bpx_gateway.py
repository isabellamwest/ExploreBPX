"""The single integration point with the official ``bpx`` package.

All coupling to BPX lives here (an anti-corruption layer). The rest of the
application depends on this module's interface, never on ``bpx`` internals.
Only the public ``bpx`` API is used:

* ``bpx.parse_bpx_obj`` for parsing/validation,
* ``bpx.BPX.model_json_schema`` for parameter metadata.
"""

from __future__ import annotations

import copy
import json
import warnings
from dataclasses import dataclass, field
from functools import lru_cache

import bpx
import yaml
from pydantic import ValidationError

from .validation import (
    BPXExceptionDiagnostic,
    ValidatorDiagnostic,
    issues_from_pydantic,
    warnings_as_diagnostics,
)

#: The exact BPX version this application is built and tested against.
BPX_VERSION: str = bpx.__version__


class LoadError(Exception):
    """Raised when raw bytes cannot be decoded into a BPX dictionary."""


@dataclass(frozen=True)
class FieldMeta:
    """Schema-derived metadata for a single parameter alias."""

    alias: str
    description: str = ""
    examples: tuple = ()
    allows_function: bool = False
    is_enum: bool = False
    enum_values: tuple = ()
    is_integer: bool = False
    is_text: bool = False


@dataclass(frozen=True)
class ExpectedField:
    """A parameter alias the schema expects for a given BPX section."""

    alias: str
    meta: FieldMeta
    required: bool


@dataclass
class ValidationResult:
    """Outcome of validating a raw BPX dictionary."""

    is_valid: bool
    issues: list[ValidatorDiagnostic] = field(default_factory=list)


def load_raw(data: bytes | str, filename: str = "") -> tuple[dict, str]:
    """Decode raw JSON/YAML bytes into a ``dict`` and report the format.

    The format is inferred from the file extension and defaults to JSON.
    Raises :class:`LoadError` if the content is not a JSON/YAML object.
    """
    text = data.decode("utf-8") if isinstance(data, (bytes, bytearray)) else data
    fmt = "yaml" if filename.lower().endswith((".yml", ".yaml")) else "json"
    try:
        parsed = yaml.safe_load(text) if fmt == "yaml" else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise LoadError(f"File is not valid {fmt.upper()}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LoadError("BPX root must be a JSON/YAML object (dictionary).")
    return parsed, fmt


def validate(raw: dict, v_tol: float = 0.001) -> ValidationResult:
    """Validate a raw BPX dict by attempting to parse it with ``bpx``.

    Never raises: parsing errors and deprecation warnings are captured and
    returned as :class:`ValidatorDiagnostic` objects so invalid files can
    still be explored.
    """
    issues: list[ValidatorDiagnostic] = []
    # ``parse_bpx_obj`` mutates the dict it is given (it replaces sections with
    # parsed models), so validate against a copy to keep ``raw`` pristine.
    candidate = copy.deepcopy(raw)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            bpx.parse_bpx_obj(candidate, v_tol=v_tol)
            is_valid = True
        except ValidationError as exc:
            issues.extend(issues_from_pydantic(exc.errors()))
            is_valid = False
        except Exception as exc:  # noqa: BLE001 - BPXSchemaError, ValueError, etc.
            issues.append(BPXExceptionDiagnostic(raw_exception=exc))
            is_valid = False
    issues.extend(warnings_as_diagnostics(caught))
    return ValidationResult(is_valid=is_valid, issues=issues)


@lru_cache(maxsize=1)
def _schema() -> dict:
    """The public BPX JSON schema, computed once and cached."""
    return bpx.BPX.model_json_schema()


@lru_cache(maxsize=1)
def metadata_index() -> dict[str, FieldMeta]:
    """Build an alias -> :class:`FieldMeta` index from the public BPX schema.

    The index is flat across all schema definitions. A handful of aliases (e.g.
    ``"Conductivity [S.m-1]"``) appear in more than one section with differing
    types; the first occurrence wins. This is acceptable because node kind is
    classified value-shape first (see :mod:`core.parameter_types`).
    """
    index: dict[str, FieldMeta] = {}
    for definition in _schema().get("$defs", {}).values():
        for alias, prop in definition.get("properties", {}).items():
            if alias not in index:
                index[alias] = _field_meta(alias, prop)
    return index


#: Section paths that map to a single schema definition regardless of model.
#: Uses the same path-tuple convention as :mod:`core.tree_model`/
#: :mod:`core.structure` (e.g. ``("Parameterisation", "Cell")``).
_SECTION_DEFS: dict[tuple[str, ...], str] = {
    ("Header",): "Header",
    ("Parameterisation", "Cell"): "Cell",
    ("Parameterisation", "Electrolyte"): "Electrolyte",
    ("Parameterisation", "Separator"): "Contact",
    ("State",): "State",
    ("State", "Initial conditions"): "InitialConditions",
    ("State", "Thermal environment"): "ThermalState",
}

#: ``Parameterisation`` is the one section whose definition depends on the
#: declared model, mirroring :func:`core.structure.required_sections`
#: (``SPM`` omits Electrolyte/Separator; an undeclared or ``Partial`` model has
#: no fixed shape).
_PARAMETERISATION_DEFS: dict[str | None, str] = {
    "SPM": "ParameterisationSPM",
    "SPMe": "Parameterisation",
    "DFN": "Parameterisation",
    "Partial": "ParameterisationPartial",
    None: "ParameterisationPartial",
}


def expected_fields(path: tuple[str, ...], model: str | None = None) -> tuple[ExpectedField, ...]:
    """Return the schema-expected parameter fields for a BPX section.

    ``path`` identifies the section using the same tuple convention as
    :mod:`core.tree_model`/:mod:`core.structure` (e.g.
    ``("Parameterisation", "Cell")``). ``model`` disambiguates
    ``("Parameterisation",)`` itself, the one section whose definition
    depends on the declared BPX model.

    Each returned :class:`ExpectedField` carries the alias, its
    :class:`FieldMeta` (from the shared :func:`metadata_index`, so metadata
    never drifts between this query and the rest of the app), and whether the
    schema's ``required`` list for that definition names it. Order matches
    the schema definition's declared property order (stable across calls).

    Raises :class:`ValueError` if ``path`` has no single schema definition.
    Notably, the electrode sections (``"Negative electrode"``/``"Positive
    electrode"``) are **not** resolved here: the schema represents each as a
    union of a single-particle and a blended-particle shape (``ElectrodeSingle``
    vs ``ElectrodeBlended``), and picking between them requires the section's
    actual content, not just its identifier. Resolving that union is left for
    the container-aware work :mod:`core.structure` already defers ("lands
    later when add-parameter is wired").
    """
    definition_name = _resolve_definition(path, model)
    definition = _schema().get("$defs", {}).get(definition_name)
    if definition is None:
        raise ValueError(f"No schema definition found for section {path!r}")
    required = set(definition.get("required") or ())
    index = metadata_index()
    return tuple(
        ExpectedField(alias=alias, meta=index[alias], required=alias in required)
        for alias in definition.get("properties", {})
    )


def _resolve_definition(path: tuple[str, ...], model: str | None) -> str:
    if path == ("Parameterisation",):
        return _PARAMETERISATION_DEFS.get(model, "ParameterisationPartial")
    if path in _SECTION_DEFS:
        return _SECTION_DEFS[path]
    raise ValueError(f"Unsupported or ambiguous section path: {path!r}")


def _field_meta(alias: str, prop: dict) -> FieldMeta:
    any_of = prop.get("anyOf", [])
    allows_function = _allows_function(prop, any_of)
    is_enum = "enum" in prop
    prop_type = prop.get("type")
    return FieldMeta(
        alias=alias,
        description=prop.get("description") or prop.get("title") or "",
        examples=tuple(prop.get("examples", ()) or ()),
        allows_function=allows_function,
        is_enum=is_enum,
        enum_values=tuple(prop.get("enum", ())) if is_enum else (),
        is_integer=prop_type == "integer",
        is_text=prop_type == "string" and not is_enum and not allows_function,
    )


def _allows_function(prop: dict, any_of: list) -> bool:
    """Detect a ``FloatFunctionTable`` field (number | int | Function | Table)."""
    members = any_of or [prop]
    for member in members:
        ref = member.get("$ref", "")
        if "InterpolatedTable" in ref or "Function" in ref:
            return True
    has_string = any(member.get("type") == "string" for member in members)
    has_number = any(member.get("type") in ("number", "integer") for member in members)
    return has_string and has_number
