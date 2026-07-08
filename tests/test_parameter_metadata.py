"""Unit tests for the unified parameter-metadata provider.

Scoping constraint under test: the provider sources content from FieldMeta
only.  The five educational categories always resolve empty because
``educational_metadata`` is an explicit, currently-empty seam -- no
educational dataset exists.
"""

from __future__ import annotations

from core.bpx_gateway import FieldMeta
from core.parameter_metadata import ParameterMetadata, resolve_parameter_metadata


def test_no_meta_yields_all_none():
    # No unit marker in the alias, so units also resolves empty: with no
    # FieldMeta and no unit-bearing alias, every category is unpopulated.
    metadata = resolve_parameter_metadata("Some alias", None)
    assert metadata == ParameterMetadata()


def test_no_meta_still_extracts_unit_from_alias():
    """Units come from the alias text itself, independent of FieldMeta --
    consistent with the existing alias-driven unit derivation elsewhere
    (see ``tree_model.py``)."""
    metadata = resolve_parameter_metadata("Some alias [m]", None)
    assert metadata.units == "m"


def test_physical_meaning_comes_from_description():
    meta = FieldMeta(alias="Ambient temperature [K]", description="The ambient temperature.")
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.physical_meaning == "The ambient temperature."


def test_units_extracted_from_alias():
    meta = FieldMeta(alias="Ambient temperature [K]")
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.units == "K"


def test_no_unit_in_alias_yields_none():
    meta = FieldMeta(alias="Cell name")
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.units is None


def test_accepted_types_enum():
    meta = FieldMeta(alias="Model", is_enum=True, enum_values=("SPM", "SPMe"))
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.accepted_types == "one of: SPM, SPMe"


def test_accepted_types_integer():
    meta = FieldMeta(alias="Number of electrodes", is_integer=True)
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.accepted_types == "integer"


def test_accepted_types_text():
    meta = FieldMeta(alias="Cell name", is_text=True)
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.accepted_types == "text"


def test_accepted_types_function():
    meta = FieldMeta(alias="Diffusivity [m2.s-1]", allows_function=True)
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.accepted_types == "number, function or table"


def test_accepted_types_none_when_no_kind_flags_set():
    meta = FieldMeta(alias="Nominal cell capacity [A.h]")
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.accepted_types is None


def test_educational_categories_are_empty_seam():
    """The five educational categories always resolve to None -- no dataset
    exists yet; this is intentional, not a bug."""
    meta = FieldMeta(alias="Ambient temperature [K]", description="x")
    metadata = resolve_parameter_metadata(meta.alias, meta)
    assert metadata.functional_dependence is None
    assert metadata.model_availability is None
    assert metadata.measurement_methods is None
    assert metadata.specification_links is None
    assert metadata.symbols is None
