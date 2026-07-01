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


def test_opening_new_file_resets_selection(valid_spm_path):
    state = AppState()
    state.open(valid_spm_path)
    state.active.select(("Parameterisation", "Cell"))
    state.active.select_parameter(
        ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )
    # Opening a new file creates a fresh DocumentSession; selection is reset.
    state.open(valid_spm_path)
    assert state.active.selected_path is None
    assert state.active.selected_parameter_path is None


# ---------------------------------------------------------------------------
# Dirty tracking and save
# ---------------------------------------------------------------------------

def test_session_starts_clean(valid_spm_bytes):
    """A freshly created session has dirty=False."""
    session = _loaded_session(valid_spm_bytes)
    assert not session.dirty


def test_apply_value_marks_dirty(valid_spm_bytes):
    """Committing an edit via apply_value marks the session dirty."""
    session = _loaded_session(valid_spm_bytes)
    session.apply_value(("Header", "Model"), "DFN")
    assert session.dirty


def test_execute_command_marks_dirty(valid_spm_bytes):
    """Running a command marks the session dirty."""
    from core.commands import SetValue
    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    assert session.dirty


def test_undo_marks_dirty(valid_spm_bytes):
    """Undo marks the session dirty regardless of the resulting state."""
    from core.commands import SetValue
    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    session.dirty = False  # simulate a save at this point
    session.undo()
    assert session.dirty


def test_save_clears_dirty(valid_spm_bytes, tmp_path):
    """save() writes to backing_file and clears dirty."""
    out = tmp_path / "test.json"
    session = _loaded_session(valid_spm_bytes)
    session.backing_file = out
    session.apply_value(("Header", "Model"), "DFN")
    assert session.dirty
    session.save()
    assert not session.dirty
    assert out.exists()


def test_save_writes_correct_content(valid_spm_bytes, tmp_path):
    """save() persists the current raw document to disk."""
    import json
    out = tmp_path / "test.json"
    session = _loaded_session(valid_spm_bytes)
    session.backing_file = out
    session.apply_value(("Header", "Model"), "DFN")
    session.save()
    assert json.loads(out.read_text("utf-8"))["Header"]["Model"] == "DFN"


def test_app_state_open_sets_backing_file(valid_spm_path):
    """AppState.open() records the opened path as backing_file."""
    state = AppState()
    state.open(valid_spm_path)
    assert state.active.backing_file == valid_spm_path


def test_app_state_open_starts_clean(valid_spm_path):
    """A freshly opened session has dirty=False."""
    state = AppState()
    state.open(valid_spm_path)
    assert not state.active.dirty
