"""Unit tests for the unified parameter-metadata provider.

The provider merges two sources: schema-derived ``FieldMeta`` (physical
meaning, units, accepted types) and the technical-descriptions dataset
(symbol, ontology link, long-form documentation, provenance). Resolution is
keyed by the parameter's *path*, because the same alias carries different
descriptions in different sections.
"""

from __future__ import annotations

from core.bpx_gateway import FieldMeta
from core.parameter_metadata import ParameterMetadata, resolve_parameter_metadata


def _path(alias: str, *sections: str) -> tuple[str, ...]:
    return ("Parameterisation", *sections, alias)


def test_no_meta_and_no_description_yields_all_none():
    # No unit marker, no FieldMeta, and a path outside every dataset section:
    # every category is unpopulated.
    metadata = resolve_parameter_metadata(("User-defined", "Some alias"), None)
    assert metadata == ParameterMetadata()


def test_no_meta_still_extracts_unit_from_alias():
    """Units come from the alias text itself, independent of FieldMeta --
    consistent with the existing alias-driven unit derivation elsewhere
    (see ``tree_model.py``)."""
    metadata = resolve_parameter_metadata(("User-defined", "Some alias [m]"), None)
    assert metadata.units == "m"


def test_physical_meaning_comes_from_description():
    meta = FieldMeta(alias="Ambient temperature [K]", description="The ambient temperature.")
    metadata = resolve_parameter_metadata(_path(meta.alias, "Cell"), meta)
    assert metadata.physical_meaning == "The ambient temperature."


def test_units_extracted_from_alias():
    meta = FieldMeta(alias="Ambient temperature [K]")
    metadata = resolve_parameter_metadata(_path(meta.alias, "Cell"), meta)
    assert metadata.units == "K"


def test_no_unit_in_alias_yields_none():
    meta = FieldMeta(alias="Cell name")
    metadata = resolve_parameter_metadata(("Header", meta.alias), meta)
    assert metadata.units is None


def test_accepted_types_enum():
    meta = FieldMeta(alias="Model", is_enum=True, enum_values=("SPM", "SPMe"))
    metadata = resolve_parameter_metadata(("Header", meta.alias), meta)
    assert metadata.accepted_types == "one of: SPM, SPMe"


def test_accepted_types_integer():
    meta = FieldMeta(alias="Number of electrodes", is_integer=True)
    metadata = resolve_parameter_metadata(("Header", meta.alias), meta)
    assert metadata.accepted_types == "integer"


def test_accepted_types_text():
    meta = FieldMeta(alias="Cell name", is_text=True)
    metadata = resolve_parameter_metadata(("Header", meta.alias), meta)
    assert metadata.accepted_types == "text"


def test_accepted_types_function():
    meta = FieldMeta(alias="Diffusivity [m2.s-1]", allows_function=True)
    metadata = resolve_parameter_metadata(("User-defined", meta.alias), meta)
    assert metadata.accepted_types == "number, function or table"


def test_accepted_types_none_when_no_kind_flags_set():
    meta = FieldMeta(alias="Nominal cell capacity [A.h]")
    metadata = resolve_parameter_metadata(("User-defined", meta.alias), meta)
    assert metadata.accepted_types is None


# ---------------------------------------------------------------------------
# Dataset-sourced fields
# ---------------------------------------------------------------------------


def test_dataset_supplies_symbol_documentation_and_source():
    metadata = resolve_parameter_metadata(
        _path("Nominal cell capacity [A.h]", "Cell"), None
    )
    assert metadata.symbol == r"Q_\mathrm{nom}"
    headings = [heading for heading, _ in metadata.documentation]
    assert "Physical correspondence" in headings
    assert "Model sensitivity" in headings
    assert "Measurement methods" in headings
    assert metadata.source and "October 2024" in metadata.source


def test_dataset_link_present_where_the_source_document_has_one():
    metadata = resolve_parameter_metadata(
        _path("Particle radius [m]", "Negative electrode"), None
    )
    assert metadata.specification_link
    assert metadata.specification_link.startswith("https://w3id.org/")


def test_documentation_is_section_scoped_not_alias_scoped():
    """The same alias resolves different documentation in different sections."""
    separator = resolve_parameter_metadata(_path("Thickness [m]", "Separator"), None)
    electrode = resolve_parameter_metadata(
        _path("Thickness [m]", "Negative electrode"), None
    )
    assert separator.documentation != electrode.documentation
    assert "separator" in dict(separator.documentation)["Description"].lower()


def test_blended_particle_paths_resolve_the_electrode_entry():
    metadata = resolve_parameter_metadata(
        _path("Particle radius [m]", "Positive electrode", "Particle", "Primary"),
        None,
    )
    assert metadata.symbol == "R_{k,m}"


def test_user_defined_alias_reuse_gets_no_documentation():
    """A custom parameter that reuses a standard alias must not inherit the
    standard's documentation -- no dataset section appears in its path."""
    metadata = resolve_parameter_metadata(
        ("User-defined", "Particle radius [m]"), None
    )
    assert metadata.symbol is None
    assert metadata.documentation == ()
