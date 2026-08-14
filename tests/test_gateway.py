"""Tests for the BPX gateway (the only module coupled to ``bpx``)."""

from __future__ import annotations

import copy

import bpx
import pytest

from explore_bpx.core import bpx_gateway
from explore_bpx.core.bpx_gateway import LoadError
from explore_bpx.core.parameter_types import ParameterKind, classify
from explore_bpx.core.tree_model import build_parameter_path_map, build_tree


def test_load_raw_json(valid_spm_bytes):
    raw, fmt = bpx_gateway.load_raw(valid_spm_bytes, "spm_example_valid.json")
    assert fmt == "json"
    assert raw["Header"]["Model"] == "SPM"


def test_load_raw_yaml_detected_by_extension():
    raw, fmt = bpx_gateway.load_raw(b"Header:\n  Model: SPM\n", "thing.yaml")
    assert fmt == "yaml"
    assert raw == {"Header": {"Model": "SPM"}}


def test_load_raw_json_with_utf8_bom():
    raw, fmt = bpx_gateway.load_raw(b'\xef\xbb\xbf{"Header": {"Model": "SPM"}}', "thing.json")
    assert fmt == "json"
    assert raw == {"Header": {"Model": "SPM"}}


def test_load_raw_yaml_with_utf8_bom():
    raw, fmt = bpx_gateway.load_raw(b"\xef\xbb\xbfHeader:\n  Model: SPM\n", "thing.yaml")
    assert fmt == "yaml"
    assert raw == {"Header": {"Model": "SPM"}}


def test_load_raw_rejects_non_object():
    with pytest.raises(LoadError):
        bpx_gateway.load_raw(b"[1, 2, 3]", "thing.json")


def test_format_for_filename_is_the_one_extension_rule():
    """Loader and ``DocumentSession.save`` both read this rule; a second
    hardcoded extension list is exactly what it exists to prevent."""
    assert bpx_gateway.format_for_filename("a.json") == "json"
    assert bpx_gateway.format_for_filename("a.yaml") == "yaml"
    assert bpx_gateway.format_for_filename("a.yml") == "yaml"
    assert bpx_gateway.format_for_filename("A.YAML") == "yaml"
    assert bpx_gateway.format_for_filename("no_extension") == "json"


def test_load_raw_rejects_malformed():
    with pytest.raises(LoadError):
        bpx_gateway.load_raw(b"{not json", "thing.json")


def test_validate_valid_file(valid_spm_dict):
    result = bpx_gateway.validate(valid_spm_dict)
    assert result.is_valid is True
    assert all(issue.severity.value == "warning" for issue in result.issues)


def test_validate_invalid_file_reports_issues(valid_spm_dict):
    broken = copy.deepcopy(valid_spm_dict)
    del broken["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"]
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.issues


# A Copy up that leaves a dangling or half-built particle name gets no
# invented diagnostic -- the app surfaces exactly what the validator
# reports. These pin what that actually is; a bpx upgrade that changes
# it should fail here.


def test_dangling_particle_name_diagnostic_comes_from_bpx(valid_spm_dict):
    renamed = copy.deepcopy(valid_spm_dict)
    particles = renamed["Parameterisation"]["Positive electrode"]["Particle"]
    particles["Renamed material X"] = particles.pop("Primary")
    result = bpx_gateway.validate(renamed)
    assert result.is_valid is False
    assert len(result.issues) == 1
    issue = result.issues[0]
    assert issue.severity.value == "error"
    assert issue.loc == ()
    assert "keys must exactly match" in issue.message
    assert "unexpected keys: ['Primary']" in issue.message


def test_partial_particle_reports_field_required_for_each_gap(valid_spm_dict):
    partial = copy.deepcopy(valid_spm_dict)
    particles = partial["Parameterisation"]["Positive electrode"]["Particle"]
    diffusivity = copy.deepcopy(particles["Primary"]["Diffusivity [m2.s-1]"])
    particles["Ghost material"] = {"Diffusivity [m2.s-1]": diffusivity}
    result = bpx_gateway.validate(partial)
    assert result.is_valid is False
    assert {issue.message for issue in result.issues} == {"Field required"}
    assert {issue.loc for issue in result.issues} == {
        ("Positive electrode", "Particle", "Ghost material", field)
        for field in (
            "Minimum stoichiometry",
            "Maximum stoichiometry",
            "Maximum concentration [mol.m-3]",
            "Particle radius [m]",
            "Surface area per unit volume [m-1]",
            "OCP [V]",
            "Reaction rate constant [mol.m-2.s-1]",
        )
    }


def test_field_meta_known_fields():
    ocp = bpx_gateway.field_meta(("Parameterisation", "Negative electrode", "OCP [V]"))
    assert ocp.allows_function is True

    model = bpx_gateway.field_meta(("Header", "Model"))
    assert model.is_enum is True
    assert "SPM" in model.enum_values

    pairs = bpx_gateway.field_meta(
        (
            "Parameterisation",
            "Cell",
            "Number of electrode pairs connected in parallel to make a cell",
        )
    )
    assert pairs.is_integer is True

    title = bpx_gateway.field_meta(("Header", "Title"))
    assert title.is_text is True


def test_field_meta_unknown_alias_is_none():
    """A genuinely unknown/custom alias resolves to no metadata -- the
    `meta=None` contract `classify` relies on for value-shape fallback."""
    assert bpx_gateway.field_meta(("Parameterisation", "Cell", "Not a real alias")) is None
    assert classify(5, bpx_gateway.field_meta(("Parameterisation", "Cell", "Not a real alias"))) == (
        ParameterKind.SCALAR
    )


# ---------------------------------------------------------------------------
# Regression coverage for the metadata_index() -> _definition_index()/
# field_meta() split (path-scoped metadata instead of a flat, first-occurrence
# -wins alias map).
# ---------------------------------------------------------------------------


def test_field_meta_electrolyte_conductivity_is_its_own_field():
    """Electrolyte's "Conductivity [S.m-1]" must not pick up the
    electrode's description or lose its function-capable type -- the two
    definitions share an alias but not a meaning."""
    meta = bpx_gateway.field_meta(("Parameterisation", "Electrolyte", "Conductivity [S.m-1]"))
    assert meta.description.startswith("Electrolyte conductivity")
    assert meta.allows_function is True


def test_field_meta_electrode_conductivity_is_scalar_only():
    meta = bpx_gateway.field_meta(("Parameterisation", "Negative electrode", "Conductivity [S.m-1]"))
    assert meta.description.startswith("Effective electronic conductivity")
    assert meta.allows_function is False


def test_field_meta_diffusivity_activation_energy_differs_by_section():
    """The same alias describes electrolyte diffusion in one
    section and particle diffusion in another."""
    electrolyte = bpx_gateway.field_meta(("Parameterisation", "Electrolyte", "Diffusivity activation energy [J.mol-1]"))
    electrode = bpx_gateway.field_meta(
        ("Parameterisation", "Negative electrode", "Diffusivity activation energy [J.mol-1]")
    )
    assert "electrolyte" in electrolyte.description
    assert "particles" in electrode.description


def test_field_meta_blended_particle_instance_resolves_particle_schema():
    """The electrode/particle family resolves at any depth under an
    electrode, including a named blended-particle instance."""
    meta = bpx_gateway.field_meta(
        (
            "Parameterisation",
            "Positive electrode",
            "Particle",
            "Primary",
            "Minimum stoichiometry",
        )
    )
    assert meta is not None
    assert meta.alias == "Minimum stoichiometry"


def test_field_meta_validation_run_resolves_experiment_schema():
    """``Validation`` is ``Dict[str, Experiment]``: the run name is an
    arbitrary, user-chosen key, not a schema identifier, so `field_meta`
    must resolve any run name to `Experiment`'s metadata -- not just a
    specific literal one."""
    meta = bpx_gateway.field_meta(("Validation", "1C discharge", "Time [s]"))
    assert meta is not None
    assert meta.description == "Time in seconds (list of FloatInts)"

    # The run name may itself contain a "/" (see the shipped example file's
    # "C/20 discharge" run) -- resolution must treat it as one opaque path
    # element, never split on "/".
    slashy = bpx_gateway.field_meta(("Validation", "C/20 discharge", "Voltage [V]"))
    assert slashy is not None
    assert slashy.description == "Voltage vs time"


def test_build_tree_electrolyte_conductivity_is_a_function_end_to_end(fixtures_dir):
    """End-to-end: with correct per-section metadata, the
    Electrolyte's function-valued "Conductivity [S.m-1]" in this example file
    renders as a FUNCTION parameter, not a SCALAR one. This example file does
    not fully validate against bpx 1.1.0 (a renamed alias elsewhere) -- build_tree
    does not require validity."""
    import json

    raw = json.loads((fixtures_dir / "nmc_pouch_cell_BPX.json").read_text("utf-8"))
    tree = build_tree(raw)
    parameters = build_parameter_path_map(tree)
    conductivity = parameters[("Parameterisation", "Electrolyte", "Conductivity [S.m-1]")]
    assert conductivity.kind is ParameterKind.FUNCTION
    assert isinstance(conductivity.value, str)


def test_build_tree_validation_parameters_have_descriptions_end_to_end(fixtures_dir):
    """Regression: every `Validation/<run>/<alias>` parameter must resolve
    real `Experiment` schema metadata, not `None` -- this example file has
    two runs (one, "C/20 discharge", with a "/" in its name), each with all
    four `Experiment` aliases."""
    import json

    raw = json.loads((fixtures_dir / "nmc_pouch_cell_BPX.json").read_text("utf-8"))
    tree = build_tree(raw)
    parameters = build_parameter_path_map(tree)
    validation_parameters = [parameter for path, parameter in parameters.items() if path[0] == "Validation"]
    assert validation_parameters
    for parameter in validation_parameters:
        assert parameter.description, f"{parameter.path!r} has no description"


def test_field_meta_degradation_and_thermal_fields_have_no_fabricated_description():
    """Fields with no schema description must not fabricate one
    from the pydantic auto-title (e.g. "LLI" -> "Lli")."""
    lli = bpx_gateway.field_meta(("State", "Degradation", "LLI"))
    assert lli.description == ""

    heat_transfer = bpx_gateway.field_meta(("State", "Thermal environment", "Heat transfer coefficient [W.m-2.K-1]"))
    assert heat_transfer.description == ""


def test_searchable_parameters_excludes_section_container_aliases():
    """Section/container names swept up by the old flat index must
    not appear as addable "parameters"."""
    pool = bpx_gateway.searchable_parameters()
    junk = {
        "x",
        "y",
        "Cell",
        "Particle",
        "Separator",
        "Electrolyte",
        "Negative electrode",
        "Positive electrode",
        "User-defined",
        "Initial conditions",
        "Thermal environment",
        "Degradation",
        "description",
    }
    assert junk.isdisjoint(pool)
    assert "Thickness [m]" in pool


def test_searchable_parameters_includes_experiment_aliases():
    """Decision: `Experiment`'s four aliases (`Time [s]`, `Current [A]`,
    `Voltage [V]`, `Temperature [K]`) belong in the searchable pool. The pool
    backs the add-parameter popup's "other parameters" tier -- every real,
    addable BPX parameter from every parameter-bearing definition, with no
    special-casing per section. `Experiment` is exactly that: a closed set of
    real leaf parameters (none of its properties are container links), so it
    is included on the same structural basis as `Cell`, `Electrolyte`, etc.
    -- there is no principled reason to carve `Validation`'s parameters out
    of a pool meant to cover the whole standard."""
    pool = bpx_gateway.searchable_parameters()
    for alias in ("Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]"):
        assert alias in pool
    assert pool["Time [s]"].description == "Time in seconds (list of FloatInts)"


def test_searchable_parameters_collapses_ambiguous_alias():
    """Decision 2: an alias whose meaning differs across the definitions it
    appears in collapses to an alias-only placeholder, not one definition's
    (arbitrary) meaning."""
    conductivity = bpx_gateway.searchable_parameters()["Conductivity [S.m-1]"]
    assert conductivity.description == ""
    assert conductivity.allows_function is False
    assert conductivity.is_enum is False
    assert conductivity.is_integer is False
    assert conductivity.is_text is False
    assert conductivity.examples == ()


#: Every ``bpx`` schema definition, classified by hand against the live
#: schema at the time of writing. If ``bpx`` adds, removes or renames a
#: definition, this test fails: review the new/changed definition and, if
#: it's a genuine parameter container, confirm its properties are leaf-shaped
#: (see `_is_container_link`/`_is_parameter_bearing_definition` in
#: bpx_gateway.py) before adding it here with the correct classification.
_KNOWN_DEFINITION_CLASSIFICATION = {
    "Cell": "parameter-bearing",
    "Contact": "parameter-bearing",
    "Degradation": "parameter-bearing",
    "ElectrodeBlended": "parameter-bearing",
    "ElectrodeBlendedSPM": "parameter-bearing",
    "ElectrodeSingle": "parameter-bearing",
    "ElectrodeSingleSPM": "parameter-bearing",
    "Electrolyte": "parameter-bearing",
    "Experiment": "parameter-bearing",
    "Header": "parameter-bearing",
    "InitialConditions": "parameter-bearing",
    "Particle": "parameter-bearing",
    "ThermalState": "parameter-bearing",
    "InterpolatedTable": "value-type",
    "UserDefined": "value-type",
    "Parameterisation": "container",
    "ParameterisationPartial": "container",
    "ParameterisationSPM": "container",
    "State": "container",
}


def test_schema_definition_classification_covers_every_definition():
    """Schema-coverage guard for decision 3: `searchable_parameters()` derives
    its parameter-bearing definition set structurally (no hardcoded name
    list), but this test pins that derivation's *result* against a reviewed,
    literal expectation so an upstream `bpx` schema change fails loudly here
    instead of silently mis-classifying a new definition."""
    defs = bpx.BPX.model_json_schema()["$defs"]

    missing = set(defs) - set(_KNOWN_DEFINITION_CLASSIFICATION)
    assert not missing, (
        f"bpx added new schema definition(s) {missing!r} that this guard test "
        "doesn't know about yet. Review each one: is it a genuine parameter "
        "container (add as 'parameter-bearing'), a pure section link whose "
        "properties are all $ref (add as 'container'), or an open/free-form "
        "value shape (add as 'value-type')? Then add it to "
        "_KNOWN_DEFINITION_CLASSIFICATION above with that classification."
    )
    stale = set(_KNOWN_DEFINITION_CLASSIFICATION) - set(defs)
    assert not stale, f"bpx removed schema definition(s) {stale!r}; remove from the table above."

    for name, expected in _KNOWN_DEFINITION_CLASSIFICATION.items():
        definition = defs[name]
        if definition.get("additionalProperties") is not False:
            actual = "value-type"
        elif bpx_gateway._is_parameter_bearing_definition(definition):
            actual = "parameter-bearing"
        else:
            actual = "container"
        assert actual == expected, (
            f"{name} classified as {actual!r}, expected {expected!r} -- bpx's "
            f"schema shape for {name} changed; re-derive its classification."
        )


def test_expected_fields_cell_matches_schema_aliases():
    fields = bpx_gateway.expected_fields(("Parameterisation", "Cell"))
    aliases = {field.alias for field in fields}
    assert aliases == {
        "Electrode area [m2]",
        "External surface area [m2]",
        "Volume [m3]",
        "Number of electrode pairs connected in parallel to make a cell",
        "Lower voltage cut-off [V]",
        "Upper voltage cut-off [V]",
        "Nominal cell capacity [A.h]",
        "Reference temperature [K]",
        "Density [kg.m-3]",
        "Specific heat capacity [J.K-1.kg-1]",
    }


def test_expected_fields_cell_required_flag():
    fields = {field.alias: field for field in bpx_gateway.expected_fields(("Parameterisation", "Cell"))}
    assert fields["Nominal cell capacity [A.h]"].required is True
    assert fields["External surface area [m2]"].required is False


def test_expected_fields_carries_the_same_meta_as_field_meta():
    fields = {field.alias: field for field in bpx_gateway.expected_fields(("Header",))}
    assert fields["Model"].meta == bpx_gateway.field_meta(("Header", "Model"))
    assert fields["Model"].meta.is_enum is True


def test_expected_fields_order_is_stable():
    first = [field.alias for field in bpx_gateway.expected_fields(("Parameterisation", "Cell"))]
    second = [field.alias for field in bpx_gateway.expected_fields(("Parameterisation", "Cell"))]
    assert first == second


def test_expected_fields_parameterisation_varies_by_model():
    spm_aliases = {field.alias for field in bpx_gateway.expected_fields(("Parameterisation",), "SPM")}
    dfn_aliases = {field.alias for field in bpx_gateway.expected_fields(("Parameterisation",), "DFN")}
    assert "Electrolyte" not in spm_aliases
    assert "Electrolyte" in dfn_aliases


def test_expected_fields_unknown_path_raises():
    with pytest.raises(ValueError, match="Unsupported or ambiguous section path"):
        bpx_gateway.expected_fields(("Nonexistent",))


# -- electrode single/blended discriminator ----------------------------------


def test_expected_fields_electrode_single_shape_from_real_spm_example(valid_spm_dict):
    """The SPM example's Negative electrode has no ``Particle`` key: single-
    particle shape. The SPM variant excludes Porosity/Conductivity (those are
    the electrode's own fields in the non-SPM shape, not the SPM one)."""
    value = valid_spm_dict["Parameterisation"]["Negative electrode"]
    aliases = {
        field.alias for field in bpx_gateway.expected_fields(("Parameterisation", "Negative electrode"), "SPM", value)
    }
    assert "Particle" not in aliases
    assert "Porosity" not in aliases
    assert "Conductivity [S.m-1]" not in aliases
    assert "Diffusivity [m2.s-1]" in aliases


def test_expected_fields_electrode_blended_shape_from_real_spm_example(valid_spm_dict):
    """The SPM example's Positive electrode has a ``Particle`` key: blended
    shape, whose particle fields live under ``Particle/<name>`` rather than
    directly on the electrode."""
    value = valid_spm_dict["Parameterisation"]["Positive electrode"]
    aliases = {
        field.alias for field in bpx_gateway.expected_fields(("Parameterisation", "Positive electrode"), "SPM", value)
    }
    assert aliases == {"Thickness [m]", "Particle"}


@pytest.mark.parametrize("empty_value", [{}, None, "oops", []])
def test_expected_fields_electrode_empty_value_resolves_to_single(empty_value):
    """An empty/absent electrode value has no ``Particle`` discriminator and
    resolves to the single-particle shape -- the common case. A non-dict
    value (``"oops"``, ``[]``) is just as discriminator-less as ``{}``/``None``
    -- ``isinstance(value, dict)`` guards the ``"Particle" in value`` check, so
    a non-dict value never raises. Using a non-SPM model here shows the *full*
    single shape (Porosity/Conductivity included), contrasting with the SPM
    variant's narrower set above."""
    aliases = {
        field.alias
        for field in bpx_gateway.expected_fields(("Parameterisation", "Negative electrode"), "DFN", empty_value)
    }
    assert "Particle" not in aliases
    assert "Porosity" in aliases
    assert "Conductivity [S.m-1]" in aliases


@pytest.mark.parametrize("model", ["DFN", None])
def test_expected_fields_electrode_blended_non_spm_model_includes_porosity(model):
    """The non-SPM blended shape (unlike its SPM counterpart) still carries
    Porosity/Conductivity directly on the electrode, alongside Particle. An
    undeclared model (``None``) selects the same full shape as a named
    non-SPM model -- only ``"SPM"`` narrows it."""
    aliases = {
        field.alias
        for field in bpx_gateway.expected_fields(("Parameterisation", "Positive electrode"), model, {"Particle": {}})
    }
    assert aliases == {
        "Conductivity [S.m-1]",
        "Particle",
        "Porosity",
        "Thickness [m]",
        "Transport efficiency",
    }


def test_expected_fields_particle_instance_resolves_to_particle_definition(valid_spm_dict):
    """A named material under a blended electrode's ``Particle`` dict resolves
    to the ``Particle`` definition, regardless of the instance's own content."""
    positive = valid_spm_dict["Parameterisation"]["Positive electrode"]
    name = next(iter(positive["Particle"]))
    aliases = {
        field.alias
        for field in bpx_gateway.expected_fields(("Parameterisation", "Positive electrode", "Particle", name), "SPM")
    }
    assert "Diffusivity [m2.s-1]" in aliases
    assert "Particle" not in aliases


def test_expected_fields_validation_run_resolves_to_experiment_definition():
    """A Validation run's path is a user-chosen key -- the schema types
    ``Validation`` as ``Dict[str, Experiment]``, the same fixed-shape-under-a-
    chosen-key pattern as a ``Particle`` instance -- so it resolves to the
    ``Experiment`` definition regardless of the run name or content."""
    aliases = {field.alias for field in bpx_gateway.expected_fields(("Validation", "Test 1"))}
    assert aliases == {"Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]"}


# ---------------------------------------------------------------------------
# FieldMeta flag detection against the live BPX schema (allows_map,
# is_series, pattern, nullable, material_check, is_container).
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "material_check"),
    [
        (("State", "Degradation", "LAM: Positive electrode"), "positive_electrode"),
        (("State", "Degradation", "LAM: Negative electrode"), "negative_electrode"),
        (
            ("State", "Initial conditions", "Initial hysteresis state: Positive electrode"),
            "positive_electrode",
        ),
        (
            ("State", "Initial conditions", "Initial hysteresis state: Negative electrode"),
            "negative_electrode",
        ),
    ],
)
def test_field_meta_allows_map_and_material_check(path, material_check):
    """The four ``FloatInt | dict[str, FloatInt]`` fields: allows_map is set,
    the schema's own material_check value is carried verbatim, and they are
    not misclassified as text/integer/container."""
    meta = bpx_gateway.field_meta(path)
    assert meta is not None
    assert meta.allows_map is True
    assert meta.material_check == material_check
    assert meta.is_text is False
    assert meta.is_integer is False
    assert meta.is_container is False
    assert meta.allows_function is False


def test_field_meta_experiment_arrays_are_series():
    for alias in ("Time [s]", "Current [A]", "Voltage [V]", "Temperature [K]"):
        meta = bpx_gateway.field_meta(("Validation", "1C discharge", alias))
        assert meta is not None, alias
        assert meta.is_series is True, alias


def test_field_meta_interpolated_table_x_y_are_series():
    """InterpolatedTable's x/y are declared arrays too, even though they are
    never surfaced as their own ParameterItem (see tree_model)."""
    definition_index = bpx_gateway._definition_index()
    table = definition_index["InterpolatedTable"]
    assert table["x"].is_series is True
    assert table["y"].is_series is True


def test_field_meta_user_defined_description_is_text_and_nullable():
    """UserDefined.description (anyOf string|null) is TEXT-flagged and
    genuinely nullable -- the one real ``nullable`` case in the schema."""
    definition_index = bpx_gateway._definition_index()
    meta = definition_index["UserDefined"]["description"]
    assert meta.is_text is True
    assert meta.nullable is True


def test_field_meta_header_bpx_has_pattern():
    meta = bpx_gateway.field_meta(("Header", "BPX"))
    assert meta is not None
    assert meta.pattern == r"^\d+\.\d+(?:\.\d+)?$"


def test_field_meta_header_title_is_not_nullable():
    """A ``default: null`` on a non-null-typed field (no ``anyOf`` member of
    type null) does not make it nullable -- pydantic still rejects an
    explicit ``None`` there."""
    meta = bpx_gateway.field_meta(("Header", "Title"))
    assert meta is not None
    assert meta.nullable is False
    assert meta.is_text is True


def test_field_meta_ocp_allows_function_stays_not_text():
    """OCP's anyOf includes a string member (for function expressions), but
    allows_function must win: is_text stays False so the FUNCTION kind is not
    shadowed by TEXT."""
    meta = bpx_gateway.field_meta(("Parameterisation", "Negative electrode", "OCP [V]"))
    assert meta is not None
    assert meta.allows_function is True
    assert meta.is_text is False


@pytest.mark.parametrize(
    "path",
    [
        ("Parameterisation", "Cell"),
        ("Parameterisation", "Positive electrode", "Particle"),
        ("Parameterisation", "User-defined"),
    ],
)
def test_field_meta_container_links_are_flagged(path):
    """Cell/Particle/User-defined are pure section links (schema properties
    that merely name another definition), so is_container is True."""
    meta = bpx_gateway.field_meta(path)
    assert meta is not None
    assert meta.is_container is True


def test_field_meta_leaf_parameter_is_not_container():
    meta = bpx_gateway.field_meta(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert meta is not None
    assert meta.is_container is False


# ---------------------------------------------------------------------------
# Staged-abort detection: ``ValidationResult.completed``
#
# bpx validates Header first, then Parameterisation, then the rest of the
# model, and a failing stage aborts the whole run -- leaving every later
# section unvalidated while reporting only the failing stage's errors. These
# tests pin both halves of that behaviour: the masking itself (so a bpx
# upgrade that changes it fails loudly) and the gateway's honest reporting of
# it, so no caller ever presents an unvalidated parameter as "Valid".
# ---------------------------------------------------------------------------


def _locs(result):
    return [tuple(getattr(issue, "loc", ()) or ()) for issue in result.issues]


def test_validate_completed_on_valid_file(valid_spm_dict):
    result = bpx_gateway.validate(valid_spm_dict)
    assert result.completed is True
    assert result.reach is bpx_gateway.CheckReach.COMPLETE


def test_validate_completed_when_only_body_sections_fail(valid_spm_dict):
    """A State error comes from the full pydantic pass: the run completed,
    so siblings without issues genuinely passed."""
    broken = copy.deepcopy(valid_spm_dict)
    broken["State"]["Initial conditions"]["Initial temperature [K]"] = "wrong"
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.completed is True
    assert result.reach is bpx_gateway.CheckReach.COMPLETE
    assert any(loc[:2] == ("State", "Initial conditions") for loc in _locs(result))


def test_validate_header_failure_masks_body_and_reports_incomplete(valid_spm_dict):
    """A Header failure aborts before the body is dispatched: bpx reports
    only the Header error (with a Header-relative loc), and the gateway must
    say the run did not complete."""
    broken = copy.deepcopy(valid_spm_dict)
    broken["Header"]["Model"] = "XFN"
    broken["State"]["Initial conditions"]["Initial temperature [K]"] = "wrong"
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.completed is False
    assert result.reach is bpx_gateway.CheckReach.HEADER
    locs = _locs(result)
    assert ("Model",) in locs, "header abort reports a Header-relative loc"
    assert not any("Initial temperature [K]" in loc for loc in locs), (
        "bpx no longer masks body errors on a header failure -- revisit _validation_completed"
    )


def test_validate_parameterisation_failure_masks_state_and_reports_incomplete(
    valid_spm_dict,
):
    """A Parameterisation failure aborts before State/Validation are
    validated; the escaping errors carry Parameterisation-relative locs."""
    broken = copy.deepcopy(valid_spm_dict)
    broken["Parameterisation"]["Cell"]["Nominal cell capacity [A.h]"] = "bad"
    broken["State"]["Initial conditions"]["Initial temperature [K]"] = "wrong"
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.completed is False
    assert result.reach is bpx_gateway.CheckReach.PARAMETERISATION
    locs = _locs(result)
    assert any(loc[:1] == ("Cell",) for loc in locs)
    assert not any("Initial temperature [K]" in loc for loc in locs), (
        "bpx no longer masks State errors on a Parameterisation failure -- revisit _validation_completed"
    )


def test_validate_model_type_mismatch_reports_incomplete(valid_spm_dict):
    """The model-type dispatch mismatch aborts with ``loc == ()``, so it is
    recognised by message alone -- this test pins that message against the
    installed bpx (see ``_MODEL_MISMATCH_MARKER``)."""
    broken = copy.deepcopy(valid_spm_dict)
    broken["Header"]["Model"] = "DFN"  # SPM-shaped Parameterisation stays put
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.completed is False
    assert result.reach is bpx_gateway.CheckReach.PARAMETERISATION
    assert any(bpx_gateway._MODEL_MISMATCH_MARKER in issue.message for issue in result.issues)


def test_validate_raw_exception_reports_incomplete(valid_spm_dict):
    """A raw (non-pydantic) bpx exception -- e.g. an unparsable version
    string checked before model validation -- means nothing was validated."""
    broken = copy.deepcopy(valid_spm_dict)
    broken["Header"]["BPX"] = "banana"
    result = bpx_gateway.validate(broken)
    assert result.is_valid is False
    assert result.completed is False
    assert result.reach is bpx_gateway.CheckReach.NOT_RUN


def test_checking_reach_unrecognised_abort_claims_least():
    """An abort-shaped loc from neither known stage cannot occur with the
    pinned bpx; if an upgrade ever produces one, resolve to HEADER -- the
    least claim a ValidationError still licenses (the Header stage always
    runs first), never an overstatement of what was checked."""
    errors = [{"loc": ("Mystery section",), "msg": "?"}]
    assert bpx_gateway._checking_reach(errors) is bpx_gateway.CheckReach.HEADER


# ---------------------------------------------------------------------------
# The legacy v0.x seam -- is_legacy / convert_legacy route to
# bpx._migrations (is_legacy_bpx / convert_v0_to_v1), a *private* bpx  # noqa: ERA001
# module used deliberately because bpx has no public equivalent. These
# tests pin the installed bpx's behaviour in the same spirit as
# _MODEL_MISMATCH_MARKER: a bpx upgrade that moves the module, changes the
# detection rule, or stops auto-converting inside parse_bpx_obj fails
# loudly here rather than silently skewing what the app says about a file.
# ---------------------------------------------------------------------------


@pytest.fixture
def legacy_v0_dict(fixtures_dir):
    """A real BPX v0.x file (``Header.BPX`` = 0.1): no State block, the
    temperatures still living in Parameterisation.Cell."""
    import json

    return json.loads((fixtures_dir / "nmc_pouch_cell_BPX.json").read_text("utf-8"))


def test_is_legacy_detects_real_v0_file(legacy_v0_dict):
    assert bpx_gateway.is_legacy(legacy_v0_dict) is True


def test_is_legacy_false_for_current_file(valid_spm_dict):
    assert bpx_gateway.is_legacy(valid_spm_dict) is False


def test_is_legacy_false_for_numeric_v1_version(valid_spm_dict):
    """A float ``Header.BPX`` >= 1 is deprecated spelling, not legacy --
    bpx coerces it and judges the file against the current schema."""
    numeric = copy.deepcopy(valid_spm_dict)
    numeric["Header"]["BPX"] = 1.0
    assert bpx_gateway.is_legacy(numeric) is False


def test_is_legacy_false_when_version_not_detectable(valid_spm_dict):
    """A missing or malformed version field means the file is not
    *detectably* legacy: is_legacy says False, and the fault itself is
    validation's to report (bpx raises the same ValueError during parse --
    see test_validate_raw_exception_reports_incomplete)."""
    missing = copy.deepcopy(valid_spm_dict)
    del missing["Header"]["BPX"]
    assert bpx_gateway.is_legacy(missing) is False
    malformed = copy.deepcopy(valid_spm_dict)
    malformed["Header"]["BPX"] = "banana"
    assert bpx_gateway.is_legacy(malformed) is False


def test_validate_auto_converts_legacy_and_warns(legacy_v0_dict):
    """bpx judges a v0.x object only after converting a copy of it: the run
    completes against the *converted* document and the only trace is the
    conversion warning. Pins that ``is_legacy`` and bpx's own
    convert-on-parse can never silently diverge, and that the warning
    stays recognisable."""
    result = bpx_gateway.validate(legacy_v0_dict)
    assert result.completed is True
    assert any("legacy BPX v0.x" in issue.message for issue in result.issues), (
        "bpx no longer warns on legacy auto-conversion -- revisit the legacy seam"
    )


def test_convert_legacy_produces_what_bpx_judges(legacy_v0_dict):
    """convert_legacy returns the v1.x repack bpx itself validates: State
    synthesised, the input untouched, and the converted copy no longer
    detectably legacy nor conversion-warned when validated."""
    pristine = copy.deepcopy(legacy_v0_dict)
    converted = bpx_gateway.convert_legacy(legacy_v0_dict)
    assert legacy_v0_dict == pristine, "convert_legacy must not mutate its input"
    assert "State" in converted
    assert bpx_gateway.is_legacy(converted) is False
    result = bpx_gateway.validate(converted)
    assert result.completed is True
    assert not any("legacy BPX v0.x" in issue.message for issue in result.issues)
