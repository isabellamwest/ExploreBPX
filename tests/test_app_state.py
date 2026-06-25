"""Tests for the two-tier object/parameter selection in AppState."""

from __future__ import annotations

from state.app_state import AppState


def _loaded_state(valid_spm_bytes) -> AppState:
    state = AppState()
    state.load(valid_spm_bytes, "spm_example_valid.json")
    return state


def test_selecting_object_shows_parameter_list(valid_spm_bytes):
    state = _loaded_state(valid_spm_bytes)
    state.select(("Parameterisation", "Cell"))

    node = state.selected_node()
    assert node is not None
    assert node.path == ("Parameterisation", "Cell")
    # No parameter selected -> object's parameter list is the active body.
    assert state.selected_parameter() is None
    assert node.parameters


def test_selecting_parameter_shows_detail(valid_spm_bytes):
    state = _loaded_state(valid_spm_bytes)
    state.select(("Parameterisation", "Cell"))
    state.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )

    parameter = state.selected_parameter()
    assert parameter is not None
    assert parameter.label == "Nominal cell capacity [A.h]"
    # The owning object stays selected so the breadcrumb resolves.
    assert state.selected_node() is not None
    assert state.selected_node().path == ("Parameterisation", "Cell")


def test_breadcrumb_object_click_clears_parameter(valid_spm_bytes):
    state = _loaded_state(valid_spm_bytes)
    state.select(("Parameterisation", "Cell"))
    state.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )
    # Re-selecting an object (e.g. clicking a breadcrumb segment) drops the
    # parameter detail and returns to the parameter list.
    state.select(("Parameterisation", "Cell"))
    assert state.selected_parameter() is None


def test_loading_new_file_resets_selection(valid_spm_bytes):
    state = _loaded_state(valid_spm_bytes)
    state.select(("Parameterisation", "Cell"))
    state.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )
    state.load(valid_spm_bytes, "spm_example_valid.json")
    assert state.selected_path is None
    assert state.selected_parameter_path is None
