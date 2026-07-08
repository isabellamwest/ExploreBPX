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
    SetValue,
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
