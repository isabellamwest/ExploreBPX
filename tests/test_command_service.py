"""Tests for the command/structure/factory backend layer."""

from __future__ import annotations

from core import bpx_gateway, command_service, document_factory, editing, export, structure
from core.command_service import CommandError
from core.commands import (
    AddParameter,
    AddSection,
    ChangeModel,
    CreateDocument,
    DuplicateParameter,
    MoveParameter,
    PullParameter,
    PullSection,
    RemoveParameter,
    RemoveSection,
    RenameKey,
    SetValue,
    SetValues,
)

import pytest


def test_factory_creates_incomplete_scaffold_no_fake_values():
    raw = document_factory.create("DFN", "Demo")
    assert raw["Header"]["Model"] == "DFN"
    assert raw["Header"]["Title"] == "Demo"
    # Required object sections present but empty (no invented values).
    assert raw["Parameterisation"]["Cell"] == {}
    assert raw["Parameterisation"]["Electrolyte"] == {}
    assert raw["Parameterisation"]["Separator"] == {}


def test_factory_partial_has_minimal_structure():
    raw = document_factory.create("Partial")
    assert set(raw) == {"Header", "Parameterisation"}


def test_factory_creates_spme_scaffold_with_separator_no_section_level_missing():
    """SPMe requires Separator, not just DFN. The scaffold
    must include an empty Separator section so the validator draws its usual
    field-level diagnostics inside it, never a bare ``missing ('Separator',)``."""
    raw = document_factory.create("SPMe", "Demo")
    assert raw["Parameterisation"]["Separator"] == {}
    issues = bpx_gateway.validate(raw).issues
    missing_locs = {
        getattr(issue, "loc", None)
        for issue in issues
        if getattr(issue, "error_type", None) == "missing"
    }
    assert ("Separator",) not in missing_locs
    assert ("Separator", "Thickness [m]") in missing_locs


def test_factory_never_scaffolds_state_since_it_is_schema_optional():
    """bpx 1.1.1 made ``State`` a genuinely optional field (``Field(None,
    alias="State")``), removing the root validator that used to demand it
    for every concrete model. The factory only scaffolds validator-required
    structure, so a fresh document -- concrete model or Partial -- never gets
    a ``State`` section; the user adds it explicitly if they want one."""
    for model in ("SPM", "SPMe", "DFN", "Partial"):
        assert "State" not in document_factory.create(model)


def test_protected_top_level_cannot_be_removed():
    assert not structure.can_remove(("Header",))
    assert not structure.can_remove(("Parameterisation",))
    assert structure.can_remove(("State",))


def test_set_value_is_non_destructive():
    raw = {"Header": {"Title": "a"}}
    result = command_service.execute(raw, SetValue(("Header", "Title"), "b"))
    assert result.raw["Header"]["Title"] == "b"
    assert raw["Header"]["Title"] == "a"


# --- ChangeModel: switch the declared model, completing structure ---


def test_change_model_adds_the_missing_required_sections_empty(valid_spm_dict):
    """SPM -> DFN adds Electrolyte and Separator as empty sections (structure
    only, exactly like the new-document scaffolds): with them present the
    validator reports the actual missing parameters field-by-field instead of
    one opaque root error. Populated sections are untouched."""
    import copy

    original = copy.deepcopy(valid_spm_dict)
    result = command_service.execute(valid_spm_dict, ChangeModel("DFN"))
    parameterisation = result.raw["Parameterisation"]
    assert result.raw["Header"]["Model"] == "DFN"
    assert parameterisation["Electrolyte"] == {}
    assert parameterisation["Separator"] == {}
    # Existing content untouched; source dict untouched.
    assert parameterisation["Cell"] == original["Parameterisation"]["Cell"]
    assert valid_spm_dict == original
    assert result.label == "Change model"
    assert result.select_parameter_path == ("Header", "Model")


def test_change_model_to_spme_adds_electrolyte_and_separator(valid_spm_dict):
    """SPMe needs Separator too, mirroring the DFN case
    above."""
    import copy

    original = copy.deepcopy(valid_spm_dict)
    result = command_service.execute(valid_spm_dict, ChangeModel("SPMe"))
    parameterisation = result.raw["Parameterisation"]
    assert result.raw["Header"]["Model"] == "SPMe"
    assert parameterisation["Electrolyte"] == {}
    assert parameterisation["Separator"] == {}
    assert parameterisation["Cell"] == original["Parameterisation"]["Cell"]


def test_change_model_never_removes_sections(valid_spm_dict):
    """Switching down (DFN -> SPM) keeps a now-extraneous Electrolyte: the
    validator reports it as an extra input, and the tree's confirm-gated
    Remove section is the deliberate way to drop populated data."""
    dfn = command_service.execute(valid_spm_dict, ChangeModel("DFN")).raw
    dfn["Parameterisation"]["Electrolyte"]["Initial concentration [mol.m-3]"] = 1000
    back = command_service.execute(dfn, ChangeModel("SPM")).raw
    assert back["Header"]["Model"] == "SPM"
    assert back["Parameterisation"]["Electrolyte"] == {
        "Initial concentration [mol.m-3]": 1000
    }


def test_change_model_to_an_unknown_string_presumes_no_structure():
    """The value is set verbatim (never gatekept; the validator judges it),
    but no sections are presumed for a model the app does not know."""
    raw = {"Header": {"Model": "SPM"}, "Parameterisation": {}}
    result = command_service.execute(raw, ChangeModel("NOT_A_MODEL"))
    assert result.raw["Header"]["Model"] == "NOT_A_MODEL"
    assert result.raw["Parameterisation"] == {}
    assert "State" not in result.raw


def test_change_model_skips_children_of_a_broken_parent():
    """A non-dict Parameterisation must not fail the whole model change: the
    model is still set, and the unreachable child sections are skipped (never
    raised) rather than failing the whole command -- the validator reports
    the broken parent. (``State`` is schema-optional since bpx 1.1.1, so it
    is never presumed here either; nothing else is required independently of
    ``Parameterisation``, so no section is added at all.)"""
    raw = {"Header": {"Model": "SPM"}, "Parameterisation": "oops"}
    result = command_service.execute(raw, ChangeModel("DFN"))
    assert result.raw["Header"]["Model"] == "DFN"
    assert result.raw["Parameterisation"] == "oops"
    assert "State" not in result.raw


def test_change_model_creates_a_missing_parent_before_its_children():
    raw = {"Header": {"Model": "Partial"}}
    result = command_service.execute(raw, ChangeModel("SPM"))
    assert result.raw["Parameterisation"]["Cell"] == {}
    assert "State" not in result.raw


def test_change_model_preview_lists_the_model_and_every_addition(valid_spm_dict):
    preview = command_service.preview(valid_spm_dict, ChangeModel("DFN"))
    assert preview.label == "Change model"
    assert ("Header", "Model") in preview.changed_paths
    assert ("Parameterisation", "Electrolyte") in preview.changed_paths
    assert ("Parameterisation", "Separator") in preview.changed_paths


def test_apply_value_on_header_model_is_one_undoable_model_change(spm_workfile):
    """Committing the Model parameter routes through ChangeModel: the value
    and the added sections arrive together and revert together."""
    from state.app_state import AppState

    state = AppState()
    state.open(spm_workfile)
    session = state.active
    assert "Electrolyte" not in session.document.raw["Parameterisation"]

    session.apply_value(("Header", "Model"), "DFN")
    assert session.document.raw["Header"]["Model"] == "DFN"
    assert session.document.raw["Parameterisation"]["Electrolyte"] == {}

    session.undo()
    assert session.document.raw["Header"]["Model"] == "SPM"
    assert "Electrolyte" not in session.document.raw["Parameterisation"]


# --- RenameKey: user-owned dict keys only (materials, Validation runs) ---


def _raw_with_run(run_name="C/20 discharge"):
    return {
        "Header": {},
        "Validation": {run_name: {"Time [s]": [0, 1]}, "1C discharge": {}},
    }


def test_rename_run_moves_value_and_preserves_key_order():
    raw = _raw_with_run()
    result = command_service.execute(
        raw, RenameKey(("Validation", "C/20 discharge"), "C/10 discharge")
    )
    assert list(result.raw["Validation"]) == ["C/10 discharge", "1C discharge"]
    assert result.raw["Validation"]["C/10 discharge"] == {"Time [s]": [0, 1]}
    assert result.label == "Rename"
    assert result.select_path == ("Validation", "C/10 discharge")
    assert raw["Validation"]["C/20 discharge"] == {"Time [s]": [0, 1]}  # source untouched


def test_rename_particle_material_is_allowed():
    raw = {
        "Parameterisation": {
            "Positive electrode": {"Particle": {"Primary": {"a": 1}, "Secondary": {}}}
        }
    }
    path = ("Parameterisation", "Positive electrode", "Particle", "Primary")
    result = command_service.execute(raw, RenameKey(path, "Main"))
    particle = result.raw["Parameterisation"]["Positive electrode"]["Particle"]
    assert list(particle) == ["Main", "Secondary"]
    assert particle["Main"] == {"a": 1}


def test_rename_a_custom_parameter_under_a_schema_section_is_allowed():
    """A schema-undefined parameter leaf is renamable directly inside a
    schema section (e.g. Cell), not only inside User-defined -- the widened
    gate under test."""
    raw = {"Parameterisation": {"Cell": {"myname [cm7]": 1.0, "Other": 2}}}
    path = ("Parameterisation", "Cell", "myname [cm7]")
    result = command_service.execute(raw, RenameKey(path, "renamed [cm7]"))
    cell = result.raw["Parameterisation"]["Cell"]
    assert list(cell) == ["renamed [cm7]", "Other"]
    assert cell["renamed [cm7]"] == 1.0
    assert "myname [cm7]" in raw["Parameterisation"]["Cell"]  # source untouched


def test_rename_a_schema_property_is_refused():
    """Schema property names are never editable; only the dict-keyed
    collections (materials, runs) carry user-owned names."""
    with pytest.raises(CommandError):
        command_service.execute({"Header": {}}, RenameKey(("Header",), "Kopfzeile"))


def test_rename_onto_an_existing_sibling_is_refused():
    """A rename is a move, never a merge -- overwriting the sibling would
    silently destroy its contents."""
    raw = _raw_with_run()
    with pytest.raises(CommandError):
        command_service.execute(
            raw, RenameKey(("Validation", "C/20 discharge"), "1C discharge")
        )
    assert "C/20 discharge" in raw["Validation"]


def test_rename_to_blank_or_unchanged_is_refused():
    raw = _raw_with_run()
    with pytest.raises(CommandError):
        command_service.execute(raw, RenameKey(("Validation", "C/20 discharge"), "   "))
    with pytest.raises(CommandError):
        command_service.execute(
            raw, RenameKey(("Validation", "C/20 discharge"), "C/20 discharge")
        )


def test_rename_then_undo_restores_the_old_name_and_position():
    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    session.execute_command(AddSection((), "Validation"))
    session.execute_command(AddSection(("Validation",), "Run A"))
    session.execute_command(AddSection(("Validation",), "Run B"))
    session.execute_command(RenameKey(("Validation", "Run A"), "Run C"))
    assert list(session.document.raw["Validation"]) == ["Run C", "Run B"]
    session.undo()
    assert list(session.document.raw["Validation"]) == ["Run A", "Run B"]


# --- MoveParameter: reorder a sibling, undo restores the prior order ---


def test_move_parameter_up_and_down_changes_sibling_order():
    raw = {"Header": {"a": 1, "b": 2, "c": 3}}
    up = command_service.execute(raw, MoveParameter(("Header",), "b", "up"))
    assert list(up.raw["Header"]) == ["b", "a", "c"]
    assert up.label == "Move up"
    assert up.select_path == ("Header",)
    assert up.select_parameter_path == ("Header", "b")
    down = command_service.execute(raw, MoveParameter(("Header",), "b", "down"))
    assert list(down.raw["Header"]) == ["a", "c", "b"]
    assert down.label == "Move down"
    # Source untouched.
    assert list(raw["Header"]) == ["a", "b", "c"]


def test_move_parameter_boundary_move_is_refused():
    raw = {"Header": {"a": 1, "b": 2, "c": 3}}
    with pytest.raises(CommandError):
        command_service.execute(raw, MoveParameter(("Header",), "a", "up"))
    with pytest.raises(CommandError):
        command_service.execute(raw, MoveParameter(("Header",), "c", "down"))


def test_move_parameter_unknown_direction_is_refused():
    raw = {"Header": {"a": 1, "b": 2}}
    with pytest.raises(CommandError):
        command_service.execute(raw, MoveParameter(("Header",), "a", "sideways"))


def test_move_parameter_missing_key_is_refused():
    raw = {"Header": {"a": 1}}
    with pytest.raises(CommandError):
        command_service.execute(raw, MoveParameter(("Header",), "nope", "up"))


def test_move_parameter_then_undo_restores_order():
    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    session.execute_command(AddParameter(("Header",), "a", 1))
    session.execute_command(AddParameter(("Header",), "b", 2))
    before = list(session.document.raw["Header"])
    session.execute_command(MoveParameter(("Header",), "a", "down"))
    assert list(session.document.raw["Header"]) != before
    session.undo()
    assert list(session.document.raw["Header"]) == before


# --- DuplicateParameter: adjacent copy with a unit-aware unique name ---


def _raw_with_material():
    return {
        "Parameterisation": {
            "Positive electrode": {
                "Particle": {"Primary": {"Radius [m]": 1e-6}, "Secondary": {}}
            }
        }
    }


def test_duplicate_parameter_inserts_adjacent_with_correct_name():
    raw = _raw_with_material()
    parent_path = ("Parameterisation", "Positive electrode", "Particle")
    result = command_service.execute(raw, DuplicateParameter(parent_path, "Primary"))
    particle = result.raw["Parameterisation"]["Positive electrode"]["Particle"]
    assert list(particle) == ["Primary", "Primary (2)", "Secondary"]
    assert particle["Primary (2)"] == {"Radius [m]": 1e-6}
    assert result.label == "Duplicate parameter"
    assert result.select_parameter_path == parent_path + ("Primary (2)",)
    # Source untouched.
    assert "Primary (2)" not in raw["Parameterisation"]["Positive electrode"]["Particle"]


def test_duplicate_parameter_unit_suffixed_key():
    """Duplication is gated like renaming, so a unit-suffixed key is
    exercised inside the User-defined bucket (a place the user actually owns
    parameter names), not at an arbitrary schema-fixed location."""
    raw = {"Parameterisation": {"User-defined": {"Time [s]": [0, 1], "Other": True}}}
    parent_path = ("Parameterisation", "User-defined")
    result = command_service.execute(raw, DuplicateParameter(parent_path, "Time [s]"))
    user_defined = result.raw["Parameterisation"]["User-defined"]
    assert list(user_defined) == ["Time [s]", "Time (2) [s]", "Other"]
    assert user_defined["Time (2) [s]"] == [0, 1]


def test_duplicate_a_custom_parameter_under_a_schema_section_is_allowed():
    """Mirrors the RenameKey widening test above for DuplicateParameter."""
    raw = {"Parameterisation": {"Cell": {"myname [cm7]": 1.0, "Other": 2}}}
    parent_path = ("Parameterisation", "Cell")
    result = command_service.execute(raw, DuplicateParameter(parent_path, "myname [cm7]"))
    cell = result.raw["Parameterisation"]["Cell"]
    assert list(cell) == ["myname [cm7]", "myname (2) [cm7]", "Other"]
    assert cell["myname (2) [cm7]"] == 1.0


def test_duplicate_parameter_name_collision_increments_to_three():
    raw = {
        "Parameterisation": {
            "User-defined": {"Foo": 1, "Foo (2)": 9},
        }
    }
    result = command_service.execute(
        raw, DuplicateParameter(("Parameterisation", "User-defined"), "Foo")
    )
    user_defined = result.raw["Parameterisation"]["User-defined"]
    assert list(user_defined) == ["Foo", "Foo (3)", "Foo (2)"]


def test_duplicate_parameter_gated_like_rename_is_refused_for_schema_keys():
    raw = {"Header": {"Model": "SPM"}}
    with pytest.raises(CommandError):
        command_service.execute(raw, DuplicateParameter(("Header",), "Model"))


def test_duplicate_parameter_then_undo_removes_it():
    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    session.execute_command(AddSection((), "Validation"))
    session.execute_command(AddSection(("Validation",), "Run A"))
    session.execute_command(DuplicateParameter(("Validation",), "Run A"))
    assert "Run A (2)" in session.document.raw["Validation"]
    session.undo()
    assert "Run A (2)" not in session.document.raw["Validation"]


# --- structure queries behind the tree's context menu ---


def test_can_rename_materials_runs_and_user_defined_content():
    assert structure.can_rename(("Validation", "C/20 discharge"))
    assert structure.can_rename(
        ("Parameterisation", "Negative electrode", "Particle", "Primary")
    )
    # User-defined content is user-owned at any depth; the bucket itself is not.
    assert structure.can_rename(("Parameterisation", "User-defined", "Thermal"))
    assert structure.can_rename(("Parameterisation", "User-defined", "Thermal", "h"))
    assert not structure.can_rename(("Parameterisation", "User-defined"))
    assert not structure.can_rename(("Header",))
    assert not structure.can_rename(("Parameterisation", "Cell"))
    assert not structure.can_rename(("Validation",))


def test_can_duplicate_mirrors_can_rename():
    """Duplication is allowed exactly where renaming is: it produces a new
    user-owned name, so it can only exist where the user already owns
    names."""
    allowed = (
        ("Validation", "C/20 discharge"),
        ("Parameterisation", "Negative electrode", "Particle", "Primary"),
        ("Parameterisation", "User-defined", "Thermal"),
        ("Parameterisation", "User-defined", "Thermal", "h"),
    )
    refused = (
        ("Parameterisation", "User-defined"),
        ("Header",),
        ("Parameterisation", "Cell"),
        ("Validation",),
    )
    for path in allowed:
        assert structure.can_rename(path) is True
        assert structure.can_duplicate(path) is True
    for path in refused:
        assert structure.can_rename(path) is False
        assert structure.can_duplicate(path) is False


def test_can_rename_parameter_widens_to_schema_undefined_leaves_anywhere():
    """A custom (schema-undefined) parameter leaf is renamable/duplicable
    wherever it lives -- not only inside User-defined -- while a real schema
    field and the section itself stay refused. See :func:`structure.can_rename_parameter`."""
    custom_leaf = ("Parameterisation", "Cell", "myname [V]")
    real_field = ("Parameterisation", "Cell", "Reference temperature [K]")
    section_itself = ("Parameterisation", "Cell")
    custom_section_like = ("Parameterisation", "Cell", "My section")

    assert structure.can_rename_parameter(custom_leaf, 1.5) is True
    assert structure.can_duplicate_parameter(custom_leaf, 1.5) is True

    assert structure.can_rename_parameter(real_field, 298.15) is False
    assert structure.can_duplicate_parameter(real_field, 298.15) is False

    assert structure.can_rename_parameter(section_itself, {}) is False
    assert structure.can_duplicate_parameter(section_itself, {}) is False

    # A dict-shaped custom value classifies as a SECTION, not a leaf -- still
    # not renamable, even though its key is schema-undefined too.
    assert structure.can_rename_parameter(custom_section_like, {"a": 1}) is False
    assert structure.can_duplicate_parameter(custom_section_like, {"a": 1}) is False

    # can_rename_parameter still covers everywhere can_rename already does.
    for path in (
        ("Validation", "C/20 discharge"),
        ("Parameterisation", "Negative electrode", "Particle", "Primary"),
        ("Parameterisation", "User-defined", "Thermal", "h"),
    ):
        assert structure.can_rename_parameter(path, 1.0) is True
        assert structure.can_duplicate_parameter(path, 1.0) is True


def test_is_freeform_section_covers_the_user_defined_bucket_and_its_content():
    ud = ("Parameterisation", "User-defined")
    assert structure.is_freeform_section(ud)  # the bucket accepts new children
    assert structure.is_freeform_section(ud + ("Thermal",))  # so do its subsections
    assert structure.is_freeform_section(ud + ("Thermal", "Nested"))
    # Not the free-form area: schema sections and the dict-keyed collections.
    assert not structure.is_freeform_section(("Parameterisation", "Cell"))
    assert not structure.is_freeform_section(("Validation",))
    assert not structure.is_freeform_section(("Parameterisation",))


def test_named_child_noun_for_the_two_dict_keyed_containers():
    assert structure.named_child_noun(("Validation",)) == "experiment"
    assert (
        structure.named_child_noun(("Parameterisation", "Positive electrode", "Particle"))
        == "material"
    )
    assert structure.named_child_noun(("Parameterisation",)) is None


def test_required_sections_never_includes_state():
    """bpx 1.1.1 made ``State`` schema-optional and removed the root
    validator that used to demand it, so no model -- concrete or not --
    lists it as required structure."""
    for model in ("SPM", "SPMe", "DFN", "Partial", None):
        assert ("State",) not in structure.required_sections(model)


def test_required_sections_includes_separator_for_spme_and_dfn_only():
    assert ("Parameterisation", "Separator") in structure.required_sections("SPMe")
    assert ("Parameterisation", "Separator") in structure.required_sections("DFN")
    assert ("Parameterisation", "Separator") not in structure.required_sections("SPM")


def test_required_sections_partial_and_none_are_header_and_parameterisation_only():
    assert structure.required_sections("Partial") == (("Header",), ("Parameterisation",))
    assert structure.required_sections(None) == (("Header",), ("Parameterisation",))


def test_addable_child_sections_come_from_the_schema():
    """State is missing Thermal environment and Degradation here, so exactly
    those (both schema-declared containers) are offered."""
    value = {"Initial conditions": {}}
    additions = structure.addable_child_sections(("State",), value)
    assert additions == ("Thermal environment", "Degradation")


def test_addable_child_sections_at_the_root_are_the_optional_top_levels():
    assert structure.addable_child_sections((), {"Header": {}, "Parameterisation": {}}) == (
        "State",
        "Validation",
    )
    assert structure.addable_child_sections((), {"Header": {}, "State": {}}) == ("Validation",)


# Deliberately no electrode-union test here: neither electrode shape
# (``ElectrodeSingle``/``ElectrodeSingleSPM`` have no container properties at
# all; a blended electrode's only container property, ``Particle``, is
# necessarily already present -- it is what discriminates blended in the
# first place) ever offers a further child *section* through this function,
# so an assertion here can't distinguish correct single/blended resolution
# from the old unconditional-``()`` behaviour. The gateway tests in
# test_gateway.py (`test_expected_fields_electrode_*`) are the layer where
# that resolution is actually observable.


# --- SetValues: the atomic multi-path write behind CSV import ---


def test_set_values_applies_every_update_non_destructively():
    raw = {"Validation": {"Run": {"Time [s]": [0], "Voltage [V]": [4.2]}}}
    result = command_service.execute(
        raw,
        SetValues(
            (
                (("Validation", "Run", "Time [s]"), [0, 1]),
                (("Validation", "Run", "Voltage [V]"), [4.2, 4.1]),
            ),
            label="Import CSV",
        ),
    )
    assert result.raw["Validation"]["Run"]["Time [s]"] == [0, 1]
    assert result.raw["Validation"]["Run"]["Voltage [V]"] == [4.2, 4.1]
    assert result.label == "Import CSV"
    # Selection lands on the FIRST update: callers put the active parameter first.
    assert result.select_parameter_path == ("Validation", "Run", "Time [s]")
    assert result.select_path == ("Validation", "Run")
    assert raw["Validation"]["Run"]["Time [s]"] == [0]  # source untouched


def test_set_values_is_all_or_nothing():
    """A bad path anywhere in the batch must leave the document untouched --
    a half-applied CSV import would desynchronise the four experiment arrays."""
    raw = {"Header": {"Title": "a"}}
    with pytest.raises(editing.EditError):
        command_service.execute(
            raw,
            SetValues(
                (
                    (("Header", "Title"), "b"),
                    (("Nope", "Missing"), 1),
                )
            ),
        )
    assert raw == {"Header": {"Title": "a"}}


def test_set_values_empty_batch_is_an_error():
    with pytest.raises(CommandError):
        command_service.execute({"Header": {}}, SetValues(()))


def test_set_values_preview_lists_every_path():
    preview = command_service.preview(
        {},
        SetValues(((("A", "x"), 1), (("A", "y"), 2)), label="Import CSV"),
    )
    assert preview.label == "Import CSV"
    assert preview.changed_paths == (("A", "x"), ("A", "y"))


def test_set_values_is_one_undo_step():
    """Four arrays filled by one import revert together with a single undo."""
    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    session.execute_command(AddSection((), "Validation"))
    session.execute_command(AddSection(("Validation",), "Run"))
    session.execute_command(
        SetValues(
            (
                (("Validation", "Run", "Time [s]"), [0, 1]),
                (("Validation", "Run", "Current [A]"), [0.1, 0.2]),
            ),
            label="Import CSV",
        )
    )
    run = session.document.raw["Validation"]["Run"]
    assert run["Time [s]"] == [0, 1] and run["Current [A]"] == [0.1, 0.2]
    session.undo()
    assert session.document.raw["Validation"]["Run"] == {}


def test_remove_protected_section_raises():
    raw = {"Header": {}, "Parameterisation": {}}
    with pytest.raises(CommandError):
        command_service.execute(raw, RemoveSection(("Header",)))


def test_document_session_create_then_undo():
    from state.document_session import DocumentSession
    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    assert session.document is not None
    session.execute_command(AddSection(("Parameterisation",), "Extra"))
    assert "Extra" in session.document.raw["Parameterisation"]
    session.undo()
    assert "Extra" not in session.document.raw["Parameterisation"]


# --- AddParameter / RemoveParameter (shared add-parameter command spine) ---


def test_add_parameter_writes_honest_empty_value():
    """The initial value on Add must be an honest 'absent' marker (None), never
    a fabricated number. None classifies as ParameterKind.UNKNOWN, matching the
    existing valueless-parameter convention (see core.parameter_types.classify)."""
    raw = {"Header": {}}
    result = command_service.execute(raw, AddParameter(("Header",), "CustomAlias", None))
    assert result.raw["Header"]["CustomAlias"] is None
    assert result.label == "Add parameter"
    assert result.select_path == ("Header",)
    assert result.select_parameter_path == ("Header", "CustomAlias")
    # Source dict is untouched (non-destructive, like every other command).
    assert "CustomAlias" not in raw["Header"]


def test_add_parameter_overwrites_existing_alias():
    """Adding over an existing key overwrites, consistent with AddSection /
    SetValue: commands never silently refuse based on prior state."""
    raw = {"Header": {"CustomAlias": 5}}
    result = command_service.execute(raw, AddParameter(("Header",), "CustomAlias", None))
    assert result.raw["Header"]["CustomAlias"] is None


def test_remove_parameter_captures_prior_value_and_result():
    raw = {"Header": {"CustomAlias": 42}}
    result = command_service.execute(raw, RemoveParameter(("Header", "CustomAlias")))
    assert "CustomAlias" not in result.raw["Header"]
    assert result.label == "Remove parameter"
    assert result.select_path == ("Header",)


def test_remove_parameter_missing_alias_is_a_noop():
    """Removing an already-absent alias does not raise, consistent with
    editing.remove_parameter's idempotent pop (same convention as
    remove_section)."""
    raw = {"Header": {}}
    result = command_service.execute(raw, RemoveParameter(("Header", "Missing")))
    assert result.raw == raw


def test_add_parameter_then_undo_removes_it():
    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    session.execute_command(AddParameter(("Header",), "CustomAlias", None))
    assert session.document.raw["Header"]["CustomAlias"] is None
    session.undo()
    assert "CustomAlias" not in session.document.raw["Header"]


def test_remove_parameter_then_undo_restores_exact_prior_value():
    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    session.execute_command(AddParameter(("Header",), "CustomAlias", 3.14))
    session.execute_command(RemoveParameter(("Header", "CustomAlias")))
    assert "CustomAlias" not in session.document.raw["Header"]
    session.undo()
    assert session.document.raw["Header"]["CustomAlias"] == 3.14


def test_add_parameter_export_roundtrip_has_no_fabricated_content():
    """Export dumps ``raw`` verbatim (core.export), so the honest empty value
    (None -> JSON null) round-trips with no invented scientific value and no
    authoring-only metadata."""
    import json

    raw = document_factory.create("DFN", "Demo")
    added = editing.add_parameter(raw, ("Header",), "CustomAlias", None)
    data = export.to_bytes(added, "json")
    reloaded = json.loads(data)
    assert reloaded["Header"]["CustomAlias"] is None
    assert set(reloaded["Header"]) == set(added["Header"])


# --- PullParameter / PullSection: comparison "Copy up" (multi-file track M3) ---


def test_pull_parameter_sets_an_existing_value_verbatim():
    raw = {"Header": {"Title": "mine"}}
    result = command_service.execute(raw, PullParameter(("Header", "Title"), "theirs"))
    assert result.raw["Header"]["Title"] == "theirs"
    assert result.label == 'Use "Title"'
    assert result.select_path == ("Header",)
    assert result.select_parameter_path == ("Header", "Title")
    assert raw["Header"]["Title"] == "mine"  # source untouched


def test_pull_parameter_with_source_label_names_the_source_in_the_undo_label():
    """A named source produces `Use "<key>" from <source>` instead of the
    plain `Use "<key>"`."""
    raw = {"Header": {"Title": "mine"}}
    result = command_service.execute(
        raw, PullParameter(("Header", "Title"), "theirs", source_label="Chen2020")
    )
    assert result.label == 'Use "Title" from Chen2020'


def test_pull_parameter_adds_a_missing_key():
    raw = {"Header": {}}
    result = command_service.execute(raw, PullParameter(("Header", "Title"), "theirs"))
    assert result.raw["Header"]["Title"] == "theirs"
    assert "Title" not in raw["Header"]


def test_pull_parameter_creates_missing_ancestors_in_a_deep_chain():
    """A reference-only parameter several sections deep: every missing
    ancestor is created empty, parents-first, in the same command."""
    raw = {"Header": {}}
    path = ("Parameterisation", "Positive electrode", "Particle", "Primary", "Radius [m]")
    result = command_service.execute(raw, PullParameter(path, 1e-6))
    parameterisation = result.raw["Parameterisation"]
    assert parameterisation["Positive electrode"]["Particle"]["Primary"] == {
        "Radius [m]": 1e-6
    }
    # Nothing invented beyond the empty ancestors + the pulled leaf.
    assert set(parameterisation) == {"Positive electrode"}
    assert set(parameterisation["Positive electrode"]) == {"Particle"}
    assert set(parameterisation["Positive electrode"]["Particle"]) == {"Primary"}
    assert "Parameterisation" not in raw  # source untouched


def test_pull_parameter_leaves_an_existing_ancestor_untouched():
    """A sibling already inside a partially-existing ancestor chain survives
    the pull -- only the missing leaf is added."""
    raw = {"Parameterisation": {"Cell": {"Other [m]": 1}}}
    result = command_service.execute(
        raw, PullParameter(("Parameterisation", "Cell", "Thickness [m]"), 2)
    )
    assert result.raw["Parameterisation"]["Cell"] == {"Other [m]": 1, "Thickness [m]": 2}


def test_pull_parameter_deepcopies_the_value_no_aliasing():
    """The pulled value is a fresh copy: mutating the main document's copy
    afterwards must never mutate the reference's original object."""
    ref_value = {"nested": [1, 2, 3]}
    raw = {"Header": {}}
    result = command_service.execute(raw, PullParameter(("Header", "Custom"), ref_value))
    result.raw["Header"]["Custom"]["nested"].append(4)
    assert ref_value == {"nested": [1, 2, 3]}


def test_pull_parameter_shape_change_scalar_over_table_is_verbatim():
    """A same-key pull with a different shape copies verbatim -- no coercion,
    whatever the destination previously held."""
    raw = {"Header": {"Custom": {"x": [1, 2], "y": [3, 4]}}}
    result = command_service.execute(raw, PullParameter(("Header", "Custom"), 42))
    assert result.raw["Header"]["Custom"] == 42


def test_pull_parameter_is_one_undo_step_including_created_ancestors():
    """Ctrl+Z reverts the whole pull, including any structure it created, as
    a single step -- the ancestors it added disappear along with the value."""
    import copy

    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("Partial", "T"))
    before = copy.deepcopy(session.document.raw)
    path = ("Parameterisation", "Positive electrode", "Radius [m]")
    session.execute_command(PullParameter(path, 5e-6))
    assert session.document.raw["Parameterisation"]["Positive electrode"] == {
        "Radius [m]": 5e-6
    }
    session.undo()
    assert session.document.raw == before
    assert "Positive electrode" not in session.document.raw["Parameterisation"]
    session.redo()
    assert session.document.raw["Parameterisation"]["Positive electrode"] == {
        "Radius [m]": 5e-6
    }


def test_pull_section_sets_the_whole_subtree_verbatim():
    raw = {"Parameterisation": {"Cell": {"a": 1}}}
    ref_section = {"b": 2, "c": {"d": 3}}
    result = command_service.execute(
        raw, PullSection(("Parameterisation", "Cell"), ref_section)
    )
    assert result.raw["Parameterisation"]["Cell"] == ref_section
    assert result.raw["Parameterisation"]["Cell"] is not ref_section
    assert result.label == 'Use "Cell"'
    assert result.select_path == ("Parameterisation", "Cell")


def test_pull_section_with_source_label_names_the_source_in_the_undo_label():
    raw = {"Parameterisation": {"Cell": {"a": 1}}}
    result = command_service.execute(
        raw,
        PullSection(("Parameterisation", "Cell"), {"b": 2}, source_label="Chen2020"),
    )
    assert result.label == 'Use "Cell" from Chen2020'


def test_pull_section_creates_missing_ancestors_and_the_section_itself():
    raw = {"Header": {}}
    ref_section = {"Thickness [m]": 1e-5}
    result = command_service.execute(
        raw, PullSection(("Parameterisation", "Separator"), ref_section)
    )
    assert result.raw["Parameterisation"]["Separator"] == ref_section
    assert "Separator" not in raw.get("Parameterisation", {})


def test_pull_section_round_trip_is_one_undo_step():
    import copy

    from state.document_session import DocumentSession

    session = DocumentSession()
    session.execute_command(CreateDocument("Partial", "T"))
    before = copy.deepcopy(session.document.raw)
    ref_section = {"Thickness [m]": 1e-5, "Porosity": 0.5}
    session.execute_command(PullSection(("Parameterisation", "Separator"), ref_section))
    assert session.document.raw["Parameterisation"]["Separator"] == ref_section
    session.undo()
    assert session.document.raw == before
    assert "Separator" not in session.document.raw["Parameterisation"]
    session.redo()
    assert session.document.raw["Parameterisation"]["Separator"] == ref_section
