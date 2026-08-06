"""The single integration point with the official ``bpx`` package.

All coupling to BPX lives here (an anti-corruption layer). The rest of the
application depends on this module's interface, never on ``bpx`` internals.
Only the public ``bpx`` API is used:

* ``bpx.parse_bpx_obj`` for parsing/validation,
* ``bpx.BPX.model_json_schema`` for parameter metadata.
"""

from __future__ import annotations

import copy
import inspect
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


def function_syntax_help() -> str:
    """The ``bpx.Function`` docstring: what a function expression may contain.

    Read from the package rather than restated here, so the hint the user sees
    tracks whatever ``bpx`` actually accepts. This module is the only one that
    imports ``bpx``; the UI asks for the text through this seam.
    """
    return inspect.getdoc(bpx.Function) or ""


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
    #: True for a per-material field declared ``FloatInt | dict[str, FloatInt]``
    #: (e.g. Degradation's LAM fields, InitialConditions' hysteresis-state
    #: fields): a single value applies to every material, or a dict keyed by
    #: particle name overrides it per material.
    allows_map: bool = False
    #: True for a field declared ``type: "array"`` (e.g. Experiment's Time/
    #: Current/Voltage/Temperature, InterpolatedTable's x/y).
    is_series: bool = False
    #: The schema's ``pattern`` (checked on the property itself and any
    #: ``anyOf`` member), or ``""`` if the field declares none.
    pattern: str = ""
    #: True only when an ``anyOf`` member is exactly ``{"type": "null"}`` --
    #: a ``default: null`` on a non-null-typed field does not make it
    #: nullable (pydantic still rejects an explicit ``None`` there).
    nullable: bool = False
    #: Verbatim value of the schema's custom ``material_check`` key
    #: (``"positive_electrode"`` / ``"negative_electrode"``), or ``""``.
    material_check: str = ""
    #: True if the property merely names another schema section (see
    #: :func:`_is_container_link`) rather than describing a leaf value.
    is_container: bool = False


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
    #: False when ``bpx`` aborted before judging the whole document. ``bpx``
    #: validates in stages -- Header first, then Parameterisation, then the
    #: rest of the model -- and a failing stage aborts the run, leaving every
    #: later section unvalidated (a bad Header masks the whole body; a bad
    #: Parameterisation masks State/Validation). When False, a parameter
    #: without issues has *not* been checked: absence of an issue is not a
    #: clean bill of health, and callers must not present it as one.
    completed: bool = True


#: The extensions :func:`load_raw` reads as YAML. Everything else is read as
#: JSON, so this is the whole of the format decision.
YAML_EXTENSIONS = (".yaml", ".yml")
#: Every extension the app opens, in the order a file dialog should offer
#: them. The single source of truth: the UI's dialog filters and drop-target
#: check both derive from this rather than repeating the list (see
#: ``ui_qt/file_filters.py``), so a new format is added in one place.
SUPPORTED_EXTENSIONS = (".json", *YAML_EXTENSIONS)


def load_raw(data: bytes | str, filename: str = "") -> tuple[dict, str]:
    """Decode raw JSON/YAML bytes into a ``dict`` and report the format.

    The format is inferred from the file extension and defaults to JSON.
    Raises :class:`LoadError` if the content is not a JSON/YAML object.
    """
    # utf-8-sig strips a leading UTF-8 BOM (common in files saved by Windows
    # editors) and is a no-op otherwise. json.loads rejects a BOM outright,
    # while yaml.safe_load tolerates one -- decoding here keeps the two
    # supported formats consistent.
    text = data.decode("utf-8-sig") if isinstance(data, (bytes, bytearray)) else data
    fmt = "yaml" if filename.lower().endswith(YAML_EXTENSIONS) else "json"
    try:
        parsed = yaml.safe_load(text) if fmt == "yaml" else json.loads(text)
    except (json.JSONDecodeError, yaml.YAMLError) as exc:
        raise LoadError(f"File is not valid {fmt.upper()}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise LoadError("BPX root must be a JSON/YAML object (dictionary).")
    return parsed, fmt


#: bpx's model-type dispatch abort (``schema.py`` ``_dispatch_param_subclasses``
#: raising ``ValueError("[Valid|Valid SPM] parameter set does not correspond
#: with the model type ...")``) surfaces as a pydantic error with ``loc == ()``,
#: so unlike the other staged aborts it is only recognisable by its message.
#: Pinned to the installed bpx (see :data:`BPX_VERSION`); behaviour is asserted
#: in ``tests/test_gateway.py`` so a bpx upgrade that rewords it fails loudly.
_MODEL_MISMATCH_MARKER = "does not correspond with the model type"


def _validation_completed(errors: list[dict]) -> bool:
    """Whether ``bpx`` ran validation to completion, judged from the shape of
    a ``ValidationError``'s error list.

    An abort is visible in the report itself: errors escaping a staged
    validator carry locs *relative to the stage that raised* (``("Model",)``
    from Header, ``("Cell", ...)`` from Parameterisation), whereas a completed
    run only reports locs anchored at a top-level BPX property (``("State",
    ...)``) or model-level checks at ``()``. The top-level property names come
    from the live schema, not a hand-kept list. The one abort that also
    reports ``()`` -- the model-type dispatch mismatch -- is recognised by
    its message (see :data:`_MODEL_MISMATCH_MARKER`).
    """
    top_level = set(_schema().get("properties", {}))
    for error in errors:
        loc = tuple(error.get("loc") or ())
        if not loc:
            if _MODEL_MISMATCH_MARKER in str(error.get("msg", "")):
                return False
        elif loc[0] not in top_level:
            return False
    return True


def validate(raw: dict, v_tol: float = 0.001) -> ValidationResult:
    """Validate a raw BPX dict by attempting to parse it with ``bpx``.

    Never raises: parsing errors and deprecation warnings are captured and
    returned as :class:`ValidatorDiagnostic` objects so invalid files can
    still be explored.
    """
    issues: list[ValidatorDiagnostic] = []
    completed = True
    # ``parse_bpx_obj`` mutates the dict it is given (it replaces sections with
    # parsed models), so validate against a copy to keep ``raw`` pristine.
    candidate = copy.deepcopy(raw)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            bpx.parse_bpx_obj(candidate, v_tol=v_tol)
            is_valid = True
        except ValidationError as exc:
            errors = exc.errors()
            issues.extend(issues_from_pydantic(errors))
            is_valid = False
            completed = _validation_completed(errors)
        except Exception as exc:  # noqa: BLE001 - BPXSchemaError, ValueError, etc.
            # A raw exception means ``bpx`` died before producing any
            # field-level judgement at all -- nothing was validated.
            issues.append(BPXExceptionDiagnostic(raw_exception=exc))
            is_valid = False
            completed = False
    issues.extend(warnings_as_diagnostics(caught))
    return ValidationResult(is_valid=is_valid, issues=issues, completed=completed)


@lru_cache(maxsize=1)
def _schema() -> dict:
    """The public BPX JSON schema, computed once and cached."""
    return bpx.BPX.model_json_schema()


@lru_cache(maxsize=1)
def _definition_index() -> dict[str, dict[str, FieldMeta]]:
    """Build a definition name -> alias -> :class:`FieldMeta` index from the
    public BPX schema.

    BPX keys parameter metadata by *(definition, alias)*, not by alias alone:
    the same alias (e.g. ``"Conductivity [S.m-1]"``) means different things in
    different sections. This index preserves that scoping instead of
    flattening it. Every property of every ``$defs`` definition is included
    verbatim, including properties that merely link to another definition
    (e.g. ``Parameterisation``'s ``"Cell"``) -- callers that want only real,
    addable parameters filter those separately (see
    :func:`searchable_parameters`).
    """
    return {
        name: {
            alias: _field_meta(alias, prop)
            for alias, prop in definition.get("properties", {}).items()
        }
        for name, definition in _schema().get("$defs", {}).items()
    }


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
    ("State", "Degradation"): "Degradation",
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

#: The three ``Parameterisation`` shapes (SPM/DFN-SPMe/Partial) agree on every
#: alias they share (each is a pure section link, identical regardless of
#: model) -- so :func:`field_meta` can resolve ``("Parameterisation", <section>)``
#: without knowing the declared model, unlike :func:`expected_fields`.
_PARAMETERISATION_FAMILY: tuple[str, ...] = (
    "Parameterisation",
    "ParameterisationSPM",
    "ParameterisationPartial",
)

#: The electrode/particle family: for every alias two or more of these share,
#: the schema metadata is identical (verified against the live BPX schema --
#: see the ``principal-engineer`` implementation notes for this change).
#: Electrolyte is the one section that diverges and is deliberately excluded.
#: Including ``Particle`` lets this same family resolve both single-particle
#: electrodes (whose particle fields live directly on the electrode) and
#: blended electrodes (whose particle fields live under a nested
#: ``Particle/<name>`` instance).
_ELECTRODE_FAMILY: tuple[str, ...] = (
    "ElectrodeSingle",
    "ElectrodeBlended",
    "ElectrodeSingleSPM",
    "ElectrodeBlendedSPM",
    "Particle",
)


def expected_fields(
    path: tuple[str, ...], model: str | None = None, value: object = None
) -> tuple[ExpectedField, ...]:
    """Return the schema-expected parameter fields for a BPX section.

    ``path`` identifies the section using the same tuple convention as
    :mod:`core.tree_model`/:mod:`core.structure` (e.g.
    ``("Parameterisation", "Cell")``). ``model`` disambiguates
    ``("Parameterisation",)`` itself and the electrode sections, whose
    definition depends on the declared BPX model. ``value`` is the section's
    live content; it is only consulted for the electrode sections (see
    below) and is otherwise ignored.

    Each returned :class:`ExpectedField` carries the alias, its
    :class:`FieldMeta` (from :func:`_definition_index`, scoped to this
    section's own schema definition, so metadata never drifts between this
    query and the rest of the app), and whether the schema's ``required``
    list for that definition names it. Order matches the schema definition's
    declared property order (stable across calls).

    The electrode sections (``"Negative electrode"``/``"Positive
    electrode"``) resolve via a discriminator on ``value``: the schema
    represents each as a union of a single-particle shape (``ElectrodeSingle``)
    and a blended-particle shape (``ElectrodeBlended``, whose particle fields
    live under a nested ``"Particle"`` dict of named materials instead of
    directly on the electrode). A ``"Particle"`` key in ``value`` picks the
    blended shape; anything else -- including an empty/absent ``value`` --
    picks the single shape, the common and default case: the discriminator
    is a pure reflection of the document's own content, not a rule this
    function enforces or an affordance it offers. ``model == "SPM"`` selects
    the ``*SPM`` variants; every other model (``SPMe``/``DFN``/``Partial``/
    undeclared) selects the full ``ElectrodeSingle``/``ElectrodeBlended``. A
    blended particle instance (``("Parameterisation", <electrode>, "Particle",
    <name>)``) resolves to ``Particle`` regardless of ``value``, and a
    ``Validation`` run instance (``("Validation", <run name>)``) resolves to
    ``Experiment`` regardless of ``value`` (the schema types ``Validation`` as
    ``Dict[str, Experiment]`` -- a fixed shape under a user-chosen key, the
    same shape as a ``Particle`` instance).

    Raises :class:`ValueError` if ``path`` still has no single schema
    definition (e.g. a ``Particle``/``Validation`` collection itself, whose
    keys are user-chosen names rather than a fixed schema shape).
    """
    definition_name = _resolve_definition(path, model, value)
    definition = _schema().get("$defs", {}).get(definition_name)
    if definition is None:
        raise ValueError(f"No schema definition found for section {path!r}")
    required = set(definition.get("required") or ())
    index = _definition_index()[definition_name]
    return tuple(
        ExpectedField(alias=alias, meta=index[alias], required=alias in required)
        for alias in definition.get("properties", {})
    )


def supported_models() -> tuple[str, ...]:
    """The ``Header.Model`` enum, verbatim from the schema (declaration order).

    The single source for *which models exist*: the New-document chooser,
    scaffolding and completion all consume this rather than restating the
    enum. Returns ``()`` if the schema ever stops declaring ``Model`` as an
    enum -- a world in which :mod:`tests.test_spec_literals_contract` fails
    loudly rather than this function guessing.
    """
    meta = field_meta(("Header", "Model"))
    return tuple(meta.enum_values) if meta is not None else ()


#: The two electrode section names, in the position the schema fixes them
#: at (``("Parameterisation", <name>, ...)``).
_ELECTRODE_NAMES: tuple[str, ...] = ("Negative electrode", "Positive electrode")


def _resolve_instance_definition(
    path: tuple[str, ...], model: str | None, value: object
) -> str | None:
    """Resolve a user-named-key instance path to its schema definition, or
    ``None`` if *path* is not one of these shapes.

    Three shapes share this path family -- a fixed schema shape sitting under
    a position/length match rather than a literal name (mirroring
    :func:`_definitions_for`'s ``Dict[str, ...]`` handling):

    * an electrode section itself (``("Parameterisation", <electrode>)``) --
      not user-named, but *its definition* is a union that a discriminator on
      ``value`` resolves (see :func:`expected_fields`);
    * a blended electrode's named material
      (``("Parameterisation", <electrode>, "Particle", <name>)``) -> always
      ``Particle``, regardless of ``value``;
    * a ``Validation`` run (``("Validation", <run name>)``) -> always
      ``Experiment`` (the schema types ``Validation`` as
      ``Dict[str, Experiment]``), regardless of ``value``.
    """
    is_electrode = (
        len(path) == 2 and path[0] == "Parameterisation" and path[1] in _ELECTRODE_NAMES
    )
    if is_electrode:
        is_blended = isinstance(value, dict) and "Particle" in value
        if model == "SPM":
            return "ElectrodeBlendedSPM" if is_blended else "ElectrodeSingleSPM"
        return "ElectrodeBlended" if is_blended else "ElectrodeSingle"
    is_particle_instance = (
        len(path) == 4
        and path[0] == "Parameterisation"
        and path[1] in _ELECTRODE_NAMES
        and path[2] == "Particle"
    )
    if is_particle_instance:
        return "Particle"
    is_validation_run = len(path) == 2 and path[0] == "Validation"
    if is_validation_run:
        return "Experiment"
    return None


def _resolve_definition(
    path: tuple[str, ...], model: str | None, value: object = None
) -> str:
    if path == ("Parameterisation",):
        return _PARAMETERISATION_DEFS.get(model, "ParameterisationPartial")
    if path in _SECTION_DEFS:
        return _SECTION_DEFS[path]
    instance_definition = _resolve_instance_definition(path, model, value)
    if instance_definition is not None:
        return instance_definition
    raise ValueError(f"Unsupported or ambiguous section path: {path!r}")


def _definitions_for(path: tuple[str, ...]) -> tuple[str, ...]:
    """Return the schema definition(s) whose properties back *path*'s
    children, or ``()`` if the path isn't a recognised section.

    Unlike :func:`_resolve_definition` (one definition, raises on
    ambiguity), this returns every definition that plausibly describes
    *path* -- including the electrode/particle subtree, at any depth beneath
    ``"Negative electrode"``/``"Positive electrode"`` -- so
    :func:`field_meta` can merge them and check they agree instead of
    guessing one.

    ``("Validation", <run name>)`` also resolves here, to ``Experiment``:
    the schema types ``Validation`` as ``Dict[str, Experiment]`` (an
    arbitrary, user-chosen run name keying a fixed ``Experiment`` shape), so
    the match is on position/length, never on the run name's literal value
    (which may itself contain a ``/``).
    """
    if not path:
        return ()
    if path == ("Parameterisation",):
        return _PARAMETERISATION_FAMILY
    if len(path) >= 2 and path[0] == "Parameterisation" and path[1] in _ELECTRODE_NAMES:
        return _ELECTRODE_FAMILY
    if len(path) == 2 and path[0] == "Validation":
        return ("Experiment",)
    if path in _SECTION_DEFS:
        return (_SECTION_DEFS[path],)
    return ()


def field_meta(path: tuple[str, ...]) -> FieldMeta | None:
    """Return the schema :class:`FieldMeta` for the parameter or section at
    *path*, or ``None`` if *path* has no known schema meaning.

    ``path`` uses the same tuple convention as :mod:`core.tree_model`/
    :mod:`core.structure` and identifies the field itself (its last element
    is the alias; the rest identifies the owning section). Metadata is
    model-independent for every real BPX parameter, so no ``model`` argument
    is needed. When *path*'s section resolves to more than one schema
    definition (the electrode/particle family), the alias must carry
    identical metadata in every definition that defines it; a disagreement
    (which does not occur for any current BPX alias) resolves to ``None``
    rather than guessing.
    """
    if not path:
        return None
    section_path, alias = path[:-1], path[-1]
    definitions = _definitions_for(section_path)
    if not definitions:
        return None
    index = _definition_index()
    candidates = [
        index[definition][alias] for definition in definitions if alias in index.get(definition, {})
    ]
    if not candidates:
        return None
    first = candidates[0]
    return first if all(candidate == first for candidate in candidates[1:]) else None


def _is_container_link(prop: dict) -> bool:
    """True if schema property *prop* merely names another section (a plain
    ``$ref``, a union of only ``$ref``s, or a dict keyed by another
    definition) rather than describing a leaf parameter value.

    Examples: ``Parameterisation``'s ``"Cell"`` (``$ref`` to ``Cell``),
    ``"Negative electrode"`` (union of ``ElectrodeSingle``/``ElectrodeBlended``
    refs), ``ElectrodeBlended``'s ``"Particle"`` (dict of ``Particle`` refs).
    A field whose value may be a plain number *or* a ``$ref`` to
    ``InterpolatedTable`` (the function/table fields) is not a container
    link: its ``anyOf`` mixes the ref with primitive types. A ``null``
    member does not count as such a primitive: ``anyOf: [$ref, null]`` is
    how the schema spells an *optional* section (bpx 1.1.1's
    ``State.Initial conditions`` / ``State.Thermal environment``), still a
    container link.
    """
    if "$ref" in prop:
        return True
    any_of = prop.get("anyOf")
    if (
        any_of
        and any("$ref" in member for member in any_of)
        and all("$ref" in member or member.get("type") == "null" for member in any_of)
    ):
        return True
    additional = prop.get("additionalProperties")
    if isinstance(additional, dict) and "$ref" in additional:
        return True
    return False


def _is_parameter_bearing_definition(definition: dict) -> bool:
    """True for schema definitions describing a closed set of real BPX
    parameters (``Cell``, ``Electrolyte``, ``Particle``, ...).

    False for: open/free-form value shapes, identified structurally by
    ``additionalProperties`` not being exactly ``False`` (``InterpolatedTable``
    leaves it unset; ``UserDefined`` sets it ``True`` for its arbitrary
    user content); and pure section containers whose every property is a
    container link to another definition rather than a parameter
    (``Parameterisation``/``State`` and their variants) -- these contribute
    no entries to :func:`searchable_parameters` because they own no
    parameters of their own, only named sub-sections.
    """
    if definition.get("additionalProperties") is not False:
        return False
    properties = definition.get("properties", {})
    return any(not _is_container_link(prop) for prop in properties.values())


@lru_cache(maxsize=1)
def searchable_parameters() -> dict[str, FieldMeta]:
    """The full BPX standard's addable parameter aliases, flattened across
    every parameter-bearing schema definition (see
    :func:`_is_parameter_bearing_definition`), for the add-parameter popup's
    "other parameters" list.

    Container-link properties (schema property names that merely name
    another section, e.g. ``"Cell"``, ``"Particle"`` -- see
    :func:`_is_container_link`) are excluded: they identify a section, not an
    addable parameter. An alias whose :class:`FieldMeta` differs across the
    definitions it appears in (e.g. ``"Conductivity [S.m-1]"``, which means
    something different for an electrode than for the electrolyte) collapses
    to an alias-only placeholder (no description, no type flags) rather than
    arbitrarily picking one definition's meaning -- the authoritative
    per-section meta is resolved separately, once the parameter's actual
    section is known, via :func:`field_meta`.
    """
    candidates: dict[str, list[FieldMeta]] = {}
    for definition in _schema().get("$defs", {}).values():
        if not _is_parameter_bearing_definition(definition):
            continue
        for alias, prop in definition.get("properties", {}).items():
            if _is_container_link(prop):
                continue
            candidates.setdefault(alias, []).append(_field_meta(alias, prop))

    result: dict[str, FieldMeta] = {}
    for alias, metas in candidates.items():
        first = metas[0]
        result[alias] = first if all(meta == first for meta in metas[1:]) else FieldMeta(alias=alias)
    return result


def _field_meta(alias: str, prop: dict) -> FieldMeta:
    any_of = prop.get("anyOf", [])
    allows_function = _allows_function(prop, any_of)
    allows_map = _allows_map(any_of)
    is_enum = "enum" in prop
    prop_type = prop.get("type")
    member_types = _member_types(prop, any_of)
    return FieldMeta(
        alias=alias,
        description=prop.get("description") or "",
        examples=tuple(prop.get("examples", ()) or ()),
        allows_function=allows_function,
        is_enum=is_enum,
        enum_values=tuple(prop.get("enum", ())) if is_enum else (),
        is_integer=prop_type == "integer",
        is_text="string" in member_types and not is_enum and not allows_function and not allows_map,
        allows_map=allows_map,
        is_series=prop_type == "array",
        pattern=_pattern(prop, any_of),
        nullable=any(member.get("type") == "null" for member in any_of),
        material_check=prop.get("material_check") or "",
        is_container=_is_container_link(prop),
    )


def _member_types(prop: dict, any_of: list) -> set[str]:
    """Every ``type`` the property declares, checking both the property
    itself and its ``anyOf`` members."""
    types = set()
    prop_type = prop.get("type")
    if prop_type:
        types.add(prop_type)
    for member in any_of:
        member_type = member.get("type")
        if member_type:
            types.add(member_type)
    return types


def _pattern(prop: dict, any_of: list) -> str:
    """The schema ``pattern``, checked on the property itself first, then any
    ``anyOf`` member (e.g. Header's ``BPX`` version string)."""
    if "pattern" in prop:
        return prop["pattern"]
    for member in any_of:
        if "pattern" in member:
            return member["pattern"]
    return ""


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


def _allows_map(any_of: list) -> bool:
    """Detect a per-material field declared ``FloatInt | dict[str, FloatInt]``:
    an ``anyOf`` with a number member, an integer member, and an object member
    whose ``additionalProperties`` is itself an ``anyOf`` of number/integer
    (e.g. Degradation's LAM fields, InitialConditions' hysteresis-state
    fields)."""
    if not any_of:
        return False
    has_number = any(member.get("type") == "number" for member in any_of)
    has_integer = any(member.get("type") == "integer" for member in any_of)
    object_member = next((member for member in any_of if member.get("type") == "object"), None)
    if object_member is None:
        return False
    additional = object_member.get("additionalProperties")
    if not isinstance(additional, dict):
        return False
    additional_any_of = additional.get("anyOf", [])
    additional_has_number = any(member.get("type") == "number" for member in additional_any_of)
    additional_has_integer = any(member.get("type") == "integer" for member in additional_any_of)
    return has_number and has_integer and additional_has_number and additional_has_integer
