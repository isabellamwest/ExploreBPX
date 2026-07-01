"""Tests for per-document selection state in DocumentSession."""

from __future__ import annotations

from core.document import BPXDocument
from state.app_state import AppState
from state.document_session import DocumentSession


def _loaded_session(valid_spm_bytes) -> DocumentSession:
    doc = BPXDocument.from_bytes(valid_spm_bytes, "spm_example_valid.json")
    return DocumentSession(doc)


def test_selecting_object_shows_parameter_list(valid_spm_bytes):
    session = _loaded_session(valid_spm_bytes)
    session.select(("Parameterisation", "Cell"))

    node = session.selected_node()
    assert node is not None
    assert node.path == ("Parameterisation", "Cell")
    # No parameter selected -> object's parameter list is the active body.
    assert session.selected_parameter() is None
    assert node.parameters


def test_selecting_parameter_shows_detail(valid_spm_bytes):
    session = _loaded_session(valid_spm_bytes)
    session.select(("Parameterisation", "Cell"))
    session.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )

    parameter = session.selected_parameter()
    assert parameter is not None
    assert parameter.label == "Nominal cell capacity [A.h]"
    # The owning object stays selected so the breadcrumb resolves.
    assert session.selected_node() is not None
    assert session.selected_node().path == ("Parameterisation", "Cell")


def test_breadcrumb_object_click_clears_parameter(valid_spm_bytes):
    session = _loaded_session(valid_spm_bytes)
    session.select(("Parameterisation", "Cell"))
    session.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )
    # Re-selecting an object (e.g. clicking a breadcrumb segment) drops the
    # parameter detail and returns to the parameter list.
    session.select(("Parameterisation", "Cell"))
    assert session.selected_parameter() is None


def test_opening_new_file_resets_selection(valid_spm_bytes):
    state = AppState()
    state.open(valid_spm_bytes, "spm_example_valid.json")
    state.active.select(("Parameterisation", "Cell"))
    state.active.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )
    # Opening a new file creates a fresh DocumentSession; selection is reset.
    state.open(valid_spm_bytes, "spm_example_valid.json")
    assert state.active.selected_path is None
    assert state.active.selected_parameter_path is None
