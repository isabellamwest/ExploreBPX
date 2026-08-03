"""Layer B schema-evolution invariants: every spec fact the app still holds
as a literal (or now derives) is pinned against the live ``bpx`` schema.

Companion to :mod:`tests.test_schema_contract` (Layer A, path-resolution).
Layer A guarantees a new/reshaped section fails loudly through
``field_meta``; it says nothing about *requiredness*, the model enum, or the
handful of section/model maps the gateway must hand-maintain because the
JSON schema carries no model->definition link. Those are what this file
pins, guarding against two silent failure modes -- a new upstream model
quietly contradicting the validator, and a schema-required section quietly
missing from scaffolds/completion -- and every test here exists to convert
one of those silences into a loud, instructive failure.

Like Layer A, facts are read straight off ``bpx.BPX.model_json_schema()``
(never through the gateway's own resolvers) so a derivation bug and a stale
literal both disagree with the raw schema, loudly.
"""

from __future__ import annotations

import bpx
import pytest

from core import bpx_gateway, completion, document_factory, structure

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def schema() -> dict:
    return bpx.BPX.model_json_schema()


@pytest.fixture(scope="module")
def defs(schema: dict) -> dict:
    return schema["$defs"]


@pytest.fixture(scope="module")
def model_enum(defs: dict) -> tuple[str, ...]:
    return tuple(defs["Header"]["properties"]["Model"]["enum"])


# ---------------------------------------------------------------------------
# B1/B2 -- the model set.
# ---------------------------------------------------------------------------


def test_B1_supported_models_is_exactly_the_header_model_enum(model_enum):
    """``SUPPORTED_MODELS`` is derived from the schema enum; this pins the
    derivation against the raw schema (order included -- it fixes the
    New-document button order). If this fires, bpx changed the model enum:
    onboard the new model deliberately -- ``_PARAMETERISATION_DEFS`` in
    bpx_gateway.py (B3 below will also be failing), the workspace panel's
    ``_MODEL_DESCRIPTORS`` blurb, and a scaffold/completion sanity pass."""
    assert document_factory.SUPPORTED_MODELS == model_enum


def test_B2_concrete_models_is_the_enum_minus_partial(model_enum):
    """``Partial`` is the one enum member the schema gives no fixed
    Parameterisation shape (no ``required`` list); everything else counts as
    concrete. If ``Partial`` itself vanishes from the enum, the subtraction
    in completion.py is dead wording and needs rethinking, not excusing."""
    assert "Partial" in model_enum
    assert completion.CONCRETE_MODELS == frozenset(model_enum) - {"Partial"}


# ---------------------------------------------------------------------------
# B3 -- the hand-maintained model -> Parameterisation-definition map.
# ---------------------------------------------------------------------------


def test_B3_every_model_has_a_parameterisation_definition(model_enum, defs):
    """The JSON schema carries no model->definition link (it lives in bpx's
    validators), so ``_PARAMETERISATION_DEFS`` is genuinely hand-maintained.
    This pins its coverage: every enum model plus the undeclared case, each
    mapping to a definition that really exists. A new model failing here is
    the loud version of the audit's worst silent failure (completion quietly
    falling back to the partial shape)."""
    mapping = bpx_gateway._PARAMETERISATION_DEFS
    assert set(mapping) == set(model_enum) | {None}, (
        "bpx's Header.Model enum and bpx_gateway._PARAMETERISATION_DEFS have "
        "drifted apart. Map every model to its Parameterisation definition "
        "(or explicitly to ParameterisationPartial if bpx really gives it no "
        "fixed shape)."
    )
    missing = [name for name in mapping.values() if name not in defs]
    assert not missing, f"_PARAMETERISATION_DEFS names nonexistent $defs: {missing}"


# ---------------------------------------------------------------------------
# B4 -- required sections per model.
# ---------------------------------------------------------------------------


def test_B4_required_sections_match_the_schemas_own_required_lists(model_enum, defs):
    """``structure.required_sections`` = the two root-required sections plus
    the schema's own ``required`` list for the model's Parameterisation
    shape. Read here from the raw schema (via the B3-pinned mapping), so a
    derivation bug in structure.py and an upstream requiredness change both
    fail loudly. Covers the audit's 'scaffold silently under-builds'
    scenario."""
    for model in model_enum:
        definition = defs[bpx_gateway._PARAMETERISATION_DEFS[model]]
        want = {("Header",), ("Parameterisation",)} | {
            ("Parameterisation", alias)
            for alias in (definition.get("required") or ())
        }
        assert set(structure.required_sections(model)) == want, (
            f"required_sections({model!r}) disagrees with the schema's own "
            f"required list for {bpx_gateway._PARAMETERISATION_DEFS[model]}"
        )
    assert structure.required_sections(None) == (("Header",), ("Parameterisation",))


# ---------------------------------------------------------------------------
# B5 -- the Experiment column aliases (both UI derivations).
# ---------------------------------------------------------------------------


def test_B5_experiment_aliases_and_their_required_split(defs):
    """The experiment card and the Compare... dialog each derive the
    Experiment column list through the gateway (they cannot import each
    other). Pin both against the raw schema, and pin the card's structural
    assumption that exactly ONE column is optional -- its '+' affordance is
    built for a single addable column, so a second optional column must
    arrive as a loud design decision, not a quiet extra button."""
    from ui_qt.cards import database_examples_dialog, experiment

    experiment_def = defs["Experiment"]
    aliases = tuple(experiment_def["properties"])
    required = set(experiment_def.get("required") or ())

    assert experiment.KNOWN_ALIASES == aliases
    assert database_examples_dialog._KNOWN_ALIASES == aliases
    optional = [alias for alias in aliases if alias not in required]
    assert optional == [experiment._OPTIONAL_ALIAS], (
        "The experiment card assumes exactly one schema-optional column "
        f"(got {optional!r}). Rework the '+' affordance before excusing this."
    )


# ---------------------------------------------------------------------------
# B6/B7 -- top-level structure literals (no gateway primitive exists yet
# for the schema root's own properties, so these stay hand-held).
# ---------------------------------------------------------------------------


def test_B6_top_level_partition_matches_the_schema_root(schema):
    """``_PROTECTED_TOP_LEVEL`` must be exactly the root's required
    properties, and protected + optional must partition the root's full
    property set -- so a new/renamed top-level section (or a requiredness
    flip like 1.1.1's State) fails here instead of silently missing from
    the Add-section menu."""
    root_properties = set(schema["properties"])
    root_required = set(schema.get("required") or ())
    protected = structure._PROTECTED_TOP_LEVEL
    optional = set(structure._OPTIONAL_TOP_LEVEL)

    assert protected == root_required
    assert protected | optional == root_properties
    assert protected.isdisjoint(optional)


def test_B7_every_state_child_has_a_section_definition_entry(defs):
    """``_SECTION_DEFS`` maps each State child by literal path. Pin the map
    to the State definition's own properties (both directions: a new child
    must be added, a stale entry must be removed) so a new State subsection
    gets completion/add-section support the moment bpx ships it."""
    state_children = set(defs["State"]["properties"])
    mapped = {
        path[1]
        for path in bpx_gateway._SECTION_DEFS
        if len(path) == 2 and path[0] == "State"
    }
    assert mapped == state_children
