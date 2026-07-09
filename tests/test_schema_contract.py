"""Layer A schema-evolution invariants for the BPX gateway's path-scoped
metadata resolution (`field_meta` / `_definitions_for` / `_definition_index`
in `core.bpx_gateway`).

These tests auto-discover every leaf parameter path the `bpx` JSON schema can
produce (no hardcoded path/alias/count lists) and pin behaviour and
provenance, never documentation wording: that every real BPX parameter path
resolves metadata, that open/free-form user content never fabricates
metadata, that this test module's own traversal still understands the
schema's shape, that definitions merged into one "family" (electrode/
particle, parameterisation) genuinely agree on every alias they share, and
that a resolved description is always either empty or the schema's own
text -- never a pydantic auto-generated title or anything else invented.

Why the traversal below is a second, independent implementation rather than
reusing core.bpx_gateway's own path resolvers (_definitions_for,
_resolve_definition, _SECTION_DEFS): a test built from the same resolver it
is meant to check can only ever agree with itself -- it would be a
tautology, incapable of catching the exact class of bug this file exists
for (the Validation/<run>/* subtree silently resolving to None, because
Validation was never a *new* $defs name, just a path into an existing
definition the resolver hadn't been taught about). This traversal is
written from scratch against the raw JSON schema shape and disagrees
loudly, by design, whenever production and schema diverge.

Classification of a *definition* (parameter-bearing vs. open/value-type) is
different: it is not path resolution, so the production predicates
_is_parameter_bearing_definition/_is_container_link are reused directly (as
the existing test_schema_definition_classification_covers_every_definition
guard in tests/test_gateway.py already pins their result against the live
schema).
"""

from __future__ import annotations

import bpx
import pytest

from core import bpx_gateway

# ---------------------------------------------------------------------------
# Independent structural traversal.
#
# Enumerates every leaf parameter path reachable from the BPX schema root by
# following, at each property:
#   - a direct $ref to a definition (a container link)              -> descend
#   - an anyOf whose members are ALL $refs (a union of sections)     -> descend into each
#   - additionalProperties: {"$ref": ...} (Dict[str, Model])         -> descend with
#     an EXTRA arbitrary key level, because a real document path carries a
#     user-chosen key there (e.g. root Validation -> Experiment,
#     ElectrodeBlended.Particle -> Particle)
#   - anything else                                                  -> a leaf parameter
#
# InterpolatedTable is deliberately never descended into: it is a value shape
# (a table cell), not a section -- core.tree_model classifies such dicts as
# TABLE and never creates per-axis parameter nodes, so its x/y are not
# parameter paths.
# ---------------------------------------------------------------------------

_VALUE_SHAPE_DEFS = {"InterpolatedTable"}


def _direct_refs(prop: dict) -> list[str]:
    """Definition name(s) *prop* names directly: a bare $ref, or an anyOf
    whose members are ALL $refs (a union of section shapes, e.g. "Negative
    electrode"). Does NOT include additionalProperties -- that is a
    dict-of-model, which introduces an extra user-chosen key level in a real
    document path (see _dict_model_ref)."""
    if "$ref" in prop:
        return [prop["$ref"].split("/")[-1]]
    any_of = prop.get("anyOf")
    if any_of and all("$ref" in member for member in any_of):
        return [member["$ref"].split("/")[-1] for member in any_of]
    return []


def _dict_model_ref(prop: dict) -> str | None:
    """Definition name reached through additionalProperties (i.e.
    Dict[str, Model]), or None if *prop* isn't shaped that way."""
    additional = prop.get("additionalProperties")
    if isinstance(additional, dict) and "$ref" in additional:
        return additional["$ref"].split("/")[-1]
    return None


def _traverse(schema: dict):
    """Walk *schema* from its root properties, returning:

    - leaves: leaf parameter path -> (owning definition name, alias, the
      property's own schema dict).
    - reached: every (definition name, alias) pair actually visited,
      regardless of whether it turned out to be a leaf or a container link
      -- used by the A3 coverage guard below.
    """
    defs = schema.get("$defs", {})
    leaves: dict[tuple[str, ...], tuple[str, str, dict]] = {}
    reached: set[tuple[str, str]] = set()

    def walk(defname: str, path: tuple[str, ...], depth: int) -> None:
        assert depth <= 10, f"traversal depth exceeded at {path!r} -- possible schema cycle"
        definition = defs.get(defname)
        if definition is None:
            return
        for alias, prop in (definition.get("properties") or {}).items():
            reached.add((defname, alias))
            descend(alias, prop, path, defname, depth)

    def descend(alias: str, prop: dict, path: tuple[str, ...], defname: str, depth: int) -> None:
        refs = [name for name in _direct_refs(prop) if name not in _VALUE_SHAPE_DEFS]
        dict_ref = _dict_model_ref(prop)
        if refs:
            for target in refs:
                walk(target, path + (alias,), depth + 1)
        elif dict_ref and dict_ref not in _VALUE_SHAPE_DEFS:
            walk(dict_ref, path + (alias, "<key>"), depth + 1)
        else:
            leaves[path + (alias,)] = (defname, alias, prop)

    for alias, prop in schema.get("properties", {}).items():
        descend(alias, prop, (), "<root>", 0)

    return leaves, reached


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
def traversal(schema: dict):
    return _traverse(schema)


@pytest.fixture(scope="module")
def leaves(traversal):
    return traversal[0]


@pytest.fixture(scope="module")
def reached(traversal):
    return traversal[1]


def test_traversal_sanity_finds_a_substantial_number_of_leaves(leaves):
    """Not an invariant on its own -- just a guard that the traversal above
    isn't silently returning nothing (e.g. from a typo that makes every
    property look like a container link). No count is asserted, only that
    the traversal produced something plausible."""
    assert len(leaves) > 50


# ---------------------------------------------------------------------------
# A1 -- path-resolution completeness.
# ---------------------------------------------------------------------------


def test_A1_every_parameter_bearing_leaf_path_resolves(leaves, defs):
    """Every leaf path owned by a parameter-bearing definition must resolve
    real metadata. This is the invariant that would have caught the
    Validation/<run>/* regression with no example file involved: that bug
    was never a missing $defs name, just a path shape _definitions_for
    hadn't been taught about."""
    unresolved = [
        path
        for path, (defname, alias, prop) in leaves.items()
        if bpx_gateway._is_parameter_bearing_definition(defs[defname])
        and bpx_gateway.field_meta(path) is None
    ]
    assert not unresolved, (
        "field_meta(path) returned None for leaf path(s) whose owning schema "
        "definition is parameter-bearing (a closed set of real BPX "
        "parameters), i.e. metadata that should exist is missing:\n"
        + "\n".join(f"  {'/'.join(p)}" for p in sorted(unresolved))
        + "\n\nLikely cause: bpx introduced a new section SHAPE (a new "
        "Dict[str, Model] subtree, a new anyOf-of-refs union, or similar) "
        "that _definitions_for() in bpx_gateway.py does not yet resolve. "
        "Teach _definitions_for about the new shape (see how it already "
        "handles Validation's Dict[str, Experiment])."
    )


# ---------------------------------------------------------------------------
# A2 -- open/value-type definitions resolve to None.
# ---------------------------------------------------------------------------


def test_A2_open_value_type_leaves_resolve_to_none(leaves, defs):
    """The mirror of A1: a leaf owned by an open/free-form definition (e.g.
    UserDefined) must resolve to meta=None -- the honest contract from the
    3.0 decision (a user-defined entry is an ordinary raw-dict entry with
    genuinely absent metadata). Asserting both directions stops a future
    change from "fixing" A1 by fabricating metadata for free-form entries.

    Definitions classified neither parameter-bearing nor open/value-type are
    pure section containers (e.g. Parameterisation, State): every one of
    their properties is itself a container link, so by construction they
    never own a traversal leaf -- a leaf's owning definition is always
    parameter-bearing or open/value-type."""
    fabricated = [
        path
        for path, (defname, alias, prop) in leaves.items()
        if not bpx_gateway._is_parameter_bearing_definition(defs[defname])
        and bpx_gateway.field_meta(path) is not None
    ]
    assert not fabricated, (
        "field_meta(path) returned real metadata for leaf path(s) whose "
        "owning schema definition is open/free-form (additionalProperties "
        "is not False, e.g. UserDefined):\n"
        + "\n".join(f"  {'/'.join(p)}" for p in sorted(fabricated))
        + "\n\nA custom/user-defined entry must have genuinely absent "
        "metadata (meta=None is the honest contract from the 3.0 decision -- "
        "see PROJECT_STATUS.md). If this fires, field_meta is fabricating "
        "metadata for free-form user content; do not add an entry to excuse "
        "it -- fix the fabrication in field_meta/_definitions_for."
    )


# ---------------------------------------------------------------------------
# A3 -- traversal coverage (guards the guard).
# ---------------------------------------------------------------------------


def test_A3_traversal_reaches_every_property_of_every_parameter_bearing_definition(defs, reached):
    """If a future bpx release restructures a union as oneOf instead of
    anyOf, or nests a Dict[str, Model] some other way, this test module's own
    traversal would quietly stop reaching things -- and A1 would then pass
    VACUOUSLY (it can only flag paths it enumerates). Anchored on the raw
    $defs properties, which neither the traversal nor production can
    fabricate."""
    blind_spots = [
        (defname, alias)
        for defname, definition in defs.items()
        if bpx_gateway._is_parameter_bearing_definition(definition)
        for alias in (definition.get("properties") or {})
        if (defname, alias) not in reached
    ]
    assert not blind_spots, (
        "This test module's traversal never reached the following "
        "(definition, property) pair(s), even though their owning "
        "definition is parameter-bearing:\n"
        + "\n".join(f"  {d}.{a!r}" for d, a in sorted(blind_spots))
        + "\n\nThe traversal has gone blind to a schema construct bpx now "
        "uses -- e.g. a union expressed as 'oneOf' instead of 'anyOf', or a "
        "new way of nesting a Dict[str, Model]. Because it can no longer "
        "enumerate these paths, A1 above would pass vacuously (silently, "
        "without checking anything real). Update _direct_refs/_dict_model_ref "
        "in this test module to recognise the new construct -- independently "
        "of however bpx_gateway.py's own resolvers were updated, so this "
        "test keeps its value as a second opinion."
    )


# ---------------------------------------------------------------------------
# A4 -- family agreement.
# ---------------------------------------------------------------------------

#: The merge families field_meta() relies on (imported, not re-derived: this
#: IS the thing under test here, unlike the traversal above where deriving
#: it independently is the whole point).
_FAMILIES: dict[str, tuple[str, ...]] = {
    "electrode/particle": bpx_gateway._ELECTRODE_FAMILY,
    "parameterisation": bpx_gateway._PARAMETERISATION_FAMILY,
}


def test_A4_family_members_agree_on_every_shared_alias():
    """field_meta() merges each family's definitions into one lookup and
    silently returns None the moment two members disagree on a shared alias
    (bpx_gateway.py, field_meta(), the all(candidate == first ...) check) --
    an assumption that currently holds for every bpx 1.1.0 alias but is
    otherwise unstated and unverified anywhere. If bpx 1.2 diverges two
    family members on an alias they used to share, every parameter through
    that alias's section silently loses its metadata and falls back to
    value-shape classification -- the same silent-failure shape as the
    Validation regression this whole file exists to prevent."""
    index = bpx_gateway._definition_index()
    disagreements = []
    for family_name, members in _FAMILIES.items():
        per_alias: dict[str, list[tuple[str, bpx_gateway.FieldMeta]]] = {}
        for member in members:
            for alias, meta in index.get(member, {}).items():
                per_alias.setdefault(alias, []).append((member, meta))
        for alias, entries in per_alias.items():
            if len(entries) < 2:
                continue
            first_member, first_meta = entries[0]
            for member, meta in entries[1:]:
                if meta != first_meta:
                    disagreements.append(
                        (family_name, alias, first_member, first_meta, member, meta)
                    )
    assert not disagreements, (
        "field_meta() treats these schema definitions as one family and "
        "assumes every alias two or more members define carries IDENTICAL "
        "metadata. That assumption just broke for:\n"
        + "\n".join(
            f"  family={fam!r} alias={alias!r}:\n"
            f"      {m1}: {meta1!r}\n"
            f"      {m2}: {meta2!r}"
            for fam, alias, m1, meta1, m2, meta2 in disagreements
        )
        + "\n\nbpx has diverged this alias's meaning between the listed "
        "definitions. field_meta(path) will now silently return None for "
        "every path through this alias's section (the disagreement branch "
        "in bpx_gateway.py's field_meta()), and classify() will silently "
        "fall back to value-shape classification, losing description/type "
        "info for a real BPX parameter. Either the divergence is genuine "
        "(field_meta needs to become section-aware for this alias instead "
        "of family-merged), or it's incidental drift upstream should not "
        "have introduced -- confirm which before changing anything here."
    )


# ---------------------------------------------------------------------------
# A5 -- description provenance, not content.
# ---------------------------------------------------------------------------


def test_A5_description_is_empty_or_exactly_the_schema_propertys_own_text(leaves):
    """Never assert a specific description STRING (upstream rewording must
    never fail this file) -- only that field_meta never invents one. This
    permanently kills the "description or title" fabrication bug (LLI ->
    "Lli", "Heat transfer coefficient [W.m-2.K-1]" -> "Heat Transfer
    Coefficient [W.M-2.K-1]") while remaining totally indifferent to
    upstream rewording of real descriptions."""
    mismatches = []
    for path, (defname, alias, prop) in leaves.items():
        meta = bpx_gateway.field_meta(path)
        if meta is None:
            continue  # A2 already covers the None case.
        schema_description = prop.get("description") or ""
        if meta.description not in ("", schema_description):
            mismatches.append((path, meta.description, schema_description))
    assert not mismatches, (
        "field_meta(path).description was neither empty nor byte-identical "
        "to the schema property's own 'description' for:\n"
        + "\n".join(
            f"  {'/'.join(p)}:\n      got:    {got!r}\n      schema: {want!r}"
            for p, got, want in mismatches
        )
        + "\n\nThis is the exact shape of the old title-fabrication bug: a "
        "pydantic auto-generated 'title' (or any other invented text) "
        "leaking into description. field_meta must only ever surface the "
        "schema's own 'description' verbatim, or the empty string when none "
        "exists -- never fall back to 'title' or fabricate text."
    )
