"""Tests for the command/structure/factory backend layer."""

from __future__ import annotations

from core import command_service, document_factory, structure
from core.command_service import CommandError
from core.commands import (
    AddSection,
    CreateDocument,
    RemoveSection,
    SetValue,
)


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
    try:
        command_service.execute(raw, RemoveSection(("Header",)))
        assert False
    except CommandError:
        pass


def test_document_session_create_then_undo():
    from state.document_session import DocumentSession
    session = DocumentSession()
    session.execute_command(CreateDocument("SPM", "T"))
    assert session.document is not None
    session.execute_command(AddSection(("Parameterisation",), "Extra"))
    assert "Extra" in session.document.raw["Parameterisation"]
    session.undo()
    assert "Extra" not in session.document.raw["Parameterisation"]
