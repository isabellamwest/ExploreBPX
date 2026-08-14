"""Tests for per-document selection state in DocumentSession."""

from __future__ import annotations

from explore_bpx.core.document import BPXDocument
from explore_bpx.state.app_state import MAX_PINNED_REFERENCES, AppState, PinReferenceOutcome
from explore_bpx.state.document_session import DocumentSession


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
    session.select_parameter(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    parameter = session.selected_parameter()
    assert parameter is not None
    assert parameter.label == "Nominal cell capacity [A.h]"
    # The owning object stays selected so the breadcrumb resolves.
    assert session.selected_node() is not None
    assert session.selected_node().path == ("Parameterisation", "Cell")


def test_breadcrumb_object_click_clears_parameter(valid_spm_bytes):
    session = _loaded_session(valid_spm_bytes)
    session.select(("Parameterisation", "Cell"))
    session.select_parameter(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    # Re-selecting an object (e.g. clicking a breadcrumb segment) drops the
    # parameter detail and returns to the parameter list.
    session.select(("Parameterisation", "Cell"))
    assert session.selected_parameter() is None


def test_open_captures_the_load_record(spm_workfile):
    """Opening captures the load-time facts once, from the same bytes the
    document was built from -- the record the file-facts group renders."""
    from explore_bpx.core.bpx_gateway import CheckReach

    state = AppState()
    state.open(spm_workfile)
    record = state.active.load_record
    assert record is not None
    assert record.fmt == "json"
    assert record.checked is CheckReach.COMPLETE
    assert record.size_bytes == spm_workfile.stat().st_size
    assert record.mtime == spm_workfile.stat().st_mtime


def test_new_document_has_no_load_record(valid_spm_path):
    """A scaffold was never loaded from source content: no record, and the
    UI states nothing about a load that did not happen."""
    state = AppState()
    state.new_document("SPM")
    assert state.active.load_record is None


def test_reference_snapshot_carries_the_record_shape(spm_workfile):
    """A pinned reference states the same facts as a main document: its
    Header identity and its own load record."""
    import json

    from explore_bpx.state.reference_snapshot import ReferenceSnapshot

    raw = json.loads(spm_workfile.read_text("utf-8"))
    raw["Header"]["Description"] = "Pouch cell"
    raw["Header"]["References"] = "Chen et al 2020"
    spm_workfile.write_text(json.dumps(raw), encoding="utf-8")
    snapshot = ReferenceSnapshot.load(spm_workfile)
    assert snapshot.description == "Pouch cell"
    assert snapshot.citation == "Chen et al 2020"
    assert snapshot.record is not None
    assert snapshot.record.fmt == "json"
    assert snapshot.record.size_bytes == spm_workfile.stat().st_size


def test_opening_new_file_resets_selection(valid_spm_path):
    state = AppState()
    state.open(valid_spm_path)
    state.active.select(("Parameterisation", "Cell"))
    state.active.select_parameter(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
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
    from explore_bpx.core.commands import SetValue

    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    assert session.dirty


def test_undo_away_from_save_point_marks_dirty(valid_spm_bytes):
    """Undoing PAST the save point is dirty: the document on screen (the
    pre-edit state) is no longer what was saved (the post-edit state)."""
    from explore_bpx.core.commands import SetValue

    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    session.dirty = False  # simulate a save at this point
    session.undo()
    assert session.dirty


def test_undo_back_to_save_point_is_clean(valid_spm_bytes):
    """Undoing back to the state that was opened (or last saved) reads clean:
    dirty means "differs from disk", never "an edit happened at some point".
    Works by identity -- undo restores the exact document object the
    transition recorded, which is the saved one."""
    from explore_bpx.core.commands import SetValue

    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    assert session.dirty
    session.undo()
    assert not session.dirty


def test_redo_back_to_save_point_is_clean(valid_spm_bytes):
    """Save mid-history, undo past it (dirty), redo back onto it (clean)."""
    from explore_bpx.core.commands import SetValue

    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    session.dirty = False  # simulate a save at this point
    session.undo()
    assert session.dirty
    session.redo()
    assert not session.dirty


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


# ---------------------------------------------------------------------------
# new_document
# ---------------------------------------------------------------------------


def test_new_document_creates_incomplete_scaffold():
    """new_document() builds a document with required fields absent.

    ``Partial`` has no required sections by design (see
    ``core.structure.required_sections``), so it validates as complete with
    an empty scaffold; the concrete models (SPM/SPMe/DFN) have required
    fields and validate as incomplete.
    """
    from explore_bpx.core import document_factory

    for model in document_factory.SUPPORTED_MODELS:
        state = AppState()
        state.new_document(model)
        assert state.active is not None
        assert state.active.document.identity.model == model
        if model != "Partial":
            assert not state.active.document.is_valid
            assert state.active.document.issues


def test_new_document_has_no_backing_file():
    """A never-saved scaffold has no backing file."""
    state = AppState()
    state.new_document("SPM")
    assert state.active.backing_file is None


def test_new_document_starts_dirty():
    """A never-saved scaffold is unsaved/modified from the outset."""
    state = AppState()
    state.new_document("SPM")
    assert state.active.dirty


def test_new_document_replaces_active_session(valid_spm_path):
    """new_document() replaces any previously-active session."""
    state = AppState()
    state.open(valid_spm_path)
    first_session = state.active
    state.new_document("DFN")
    assert state.active is not first_session
    assert state.active.document.identity.model == "DFN"


def test_new_document_unknown_model_raises():
    """An unsupported model raises ValueError and leaves no active session."""
    import pytest

    state = AppState()
    with pytest.raises(ValueError, match="Unknown model"):
        state.new_document("NotAModel")
    assert state.active is None


def test_new_document_unknown_model_leaves_previous_session_intact(valid_spm_path):
    """A failed new_document() call must not disturb the previous session."""
    import pytest

    state = AppState()
    state.open(valid_spm_path)
    first_session = state.active
    with pytest.raises(ValueError, match="Unknown model"):
        state.new_document("NotAModel")
    assert state.active is first_session


# ---------------------------------------------------------------------------
# pin_reference / remove_reference
# ---------------------------------------------------------------------------


def test_pin_reference_pins_a_snapshot(nmc_pouch_cell_path):
    state = AppState()

    outcome = state.pin_reference(nmc_pouch_cell_path)

    assert outcome is PinReferenceOutcome.ADDED
    assert state.reference is not None
    assert state.reference.filename == nmc_pouch_cell_path.name
    assert state.reference.model == "DFN"


def test_pin_reference_with_no_main_document_is_allowed(nmc_pouch_cell_path):
    """A reference-only workspace is a legal state (no main document open)."""
    state = AppState()
    assert state.active is None

    outcome = state.pin_reference(nmc_pouch_cell_path)

    assert outcome is PinReferenceOutcome.ADDED
    assert state.active is None
    assert state.reference is not None


def test_pin_reference_a_second_time_appends(nmc_pouch_cell_path, valid_spm_path):
    state = AppState()
    state.pin_reference(nmc_pouch_cell_path)

    outcome = state.pin_reference(valid_spm_path)

    assert outcome is PinReferenceOutcome.ADDED
    assert [reference.filename for reference in state.references] == [
        nmc_pouch_cell_path.name,
        valid_spm_path.name,
    ]


def test_pin_reference_same_path_again_is_already_reference(nmc_pouch_cell_path):
    state = AppState()
    state.pin_reference(nmc_pouch_cell_path)

    outcome = state.pin_reference(nmc_pouch_cell_path)

    assert outcome is PinReferenceOutcome.ALREADY_REFERENCE
    assert len(state.references) == 1  # unchanged


def test_pin_reference_matching_the_main_file_is_is_main(valid_spm_path):
    state = AppState()
    state.open(valid_spm_path)

    outcome = state.pin_reference(valid_spm_path)

    assert outcome is PinReferenceOutcome.IS_MAIN
    assert state.references == []


def test_pin_reference_beyond_the_cap_is_refused(valid_spm_path, tmp_path):
    """The fifth pin is rejected outright -- no silent replacement of an
    earlier one."""
    import shutil

    state = AppState()
    for index in range(MAX_PINNED_REFERENCES):
        copy = tmp_path / f"ref{index}.json"
        shutil.copy(valid_spm_path, copy)
        assert state.pin_reference(copy) is PinReferenceOutcome.ADDED

    one_too_many = tmp_path / "fifth.json"
    shutil.copy(valid_spm_path, one_too_many)
    outcome = state.pin_reference(one_too_many)

    assert outcome is PinReferenceOutcome.AT_CAP
    assert len(state.references) == MAX_PINNED_REFERENCES
    assert state.at_reference_cap


def test_pin_reference_already_pinned_at_the_cap_is_not_at_cap(valid_spm_path, tmp_path):
    """Re-pinning something already pinned is the harmless duplicate it is,
    even with no room left -- ALREADY_REFERENCE beats AT_CAP."""
    import shutil

    state = AppState()
    first = None
    for index in range(MAX_PINNED_REFERENCES):
        copy = tmp_path / f"ref{index}.json"
        shutil.copy(valid_spm_path, copy)
        state.pin_reference(copy)
        first = first or copy

    assert state.pin_reference(first) is PinReferenceOutcome.ALREADY_REFERENCE


def test_close_leaves_the_references_untouched(valid_spm_path, nmc_pouch_cell_path):
    state = AppState()
    state.open(valid_spm_path)
    state.pin_reference(nmc_pouch_cell_path)

    state.close()

    assert state.active is None
    assert state.reference is not None
    assert state.reference.filename == nmc_pouch_cell_path.name


def test_opening_a_new_main_leaves_the_references_untouched(valid_spm_path, nmc_pouch_cell_path, tmp_path):
    import shutil

    state = AppState()
    state.open(valid_spm_path)
    state.pin_reference(nmc_pouch_cell_path)

    other = tmp_path / "other.json"
    shutil.copy(valid_spm_path, other)
    state.open(other)

    assert state.active.backing_file == other
    assert state.reference is not None
    assert state.reference.filename == nmc_pouch_cell_path.name


def test_remove_reference_takes_only_the_named_pin(nmc_pouch_cell_path, valid_spm_path):
    state = AppState()
    state.pin_reference(nmc_pouch_cell_path)
    state.pin_reference(valid_spm_path)

    state.remove_reference(state.references[0])

    assert [reference.filename for reference in state.references] == [valid_spm_path.name]


def test_remove_reference_frees_a_slot_at_the_cap(valid_spm_path, tmp_path):
    import shutil

    state = AppState()
    for index in range(MAX_PINNED_REFERENCES):
        copy = tmp_path / f"ref{index}.json"
        shutil.copy(valid_spm_path, copy)
        state.pin_reference(copy)

    state.remove_reference(state.references[1])
    assert not state.at_reference_cap

    replacement = tmp_path / "replacement.json"
    shutil.copy(valid_spm_path, replacement)
    assert state.pin_reference(replacement) is PinReferenceOutcome.ADDED


def test_the_undo_stack_stops_growing_at_its_depth(spm_workfile):
    """Each transition pins a whole document, so an uncapped stack grew
    without limit for the length of a session. The cap drops the oldest
    step; everything within reach still undoes exactly as before."""
    from explore_bpx.core.commands import SetValue
    from explore_bpx.state.document_session import UNDO_DEPTH

    state = AppState()
    state.open(spm_workfile)
    session = state.active
    path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")

    for step in range(UNDO_DEPTH + 20):
        session.execute_command(SetValue(path, float(step)))

    assert len(session._undo_stack) == UNDO_DEPTH

    for _ in range(UNDO_DEPTH):
        session.undo()
    # Undone all the way back to the oldest step still held: that is step 20's
    # own "before", the value written by step 19.
    assert session.document.find_parameter(path).value == 19.0
    assert session._undo_stack == []
