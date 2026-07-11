"""Tests for the command/structure/factory backend layer."""

from __future__ import annotations

from core import command_service, document_factory, editing, export, structure
from core.command_service import CommandError
from core.commands import (
    AddParameter,
    AddSection,
    CreateDocument,
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


def test_protected_top_level_cannot_be_removed():
    assert not structure.can_remove(("Header",))
    assert not structure.can_remove(("Parameterisation",))
    assert structure.can_remove(("State",))


def test_set_value_is_non_destructive():
    raw = {"Header": {"Title": "a"}}
    result = command_service.execute(raw, SetValue(("Header", "Title"), "b"))
    assert result.raw["Header"]["Title"] == "b"
    assert raw["Header"]["Title"] == "a"


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


# --- structure queries behind the tree's context menu ---


def test_can_rename_only_materials_and_runs():
    assert structure.can_rename(("Validation", "C/20 discharge"))
    assert structure.can_rename(
        ("Parameterisation", "Negative electrode", "Particle", "Primary")
    )
    assert not structure.can_rename(("Header",))
    assert not structure.can_rename(("Parameterisation", "Cell"))
    assert not structure.can_rename(("Validation",))


def test_named_child_noun_for_the_two_dict_keyed_containers():
    assert structure.named_child_noun(("Validation",)) == "experiment"
    assert (
        structure.named_child_noun(("Parameterisation", "Positive electrode", "Particle"))
        == "material"
    )
    assert structure.named_child_noun(("Parameterisation",)) is None


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


def test_addable_child_sections_degrade_to_empty_for_the_electrode_union():
    """The electrode's single/blended union has no single schema definition;
    offering nothing beats guessing."""
    assert (
        structure.addable_child_sections(
            ("Parameterisation", "Positive electrode"), {"Particle": {}}
        )
        == ()
    )


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


# --- C1: AddParameter / RemoveParameter (shared add-parameter command spine) ---


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
