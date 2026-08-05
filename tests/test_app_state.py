"""Tests for per-document selection state in DocumentSession."""

from __future__ import annotations

import shutil

from core.document import BPXDocument
from state.app_state import REFERENCE_PIN_CAP, AppState, PinReferenceOutcome
from state.document_session import DocumentSession


def _copies(source, tmp_path, count: int) -> list:
    """Distinct on-disk copies of *source* -- path-deduped pins need
    genuinely different resolved paths."""
    paths = []
    for index in range(count):
        target = tmp_path / f"copy_{index}.json"
        shutil.copy(source, target)
        paths.append(target)
    return paths


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


def test_undo_away_from_save_point_marks_dirty(valid_spm_bytes):
    """Undoing PAST the save point is dirty: the document on screen (the
    pre-edit state) is no longer what was saved (the post-edit state)."""
    from core.commands import SetValue
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
    from core.commands import SetValue
    session = _loaded_session(valid_spm_bytes)
    session.execute_command(SetValue(("Header", "Model"), "DFN"))
    assert session.dirty
    session.undo()
    assert not session.dirty


def test_redo_back_to_save_point_is_clean(valid_spm_bytes):
    """Save mid-history, undo past it (dirty), redo back onto it (clean)."""
    from core.commands import SetValue
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
    from core import document_factory

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
    with pytest.raises(ValueError):
        state.new_document("NotAModel")
    assert state.active is None


def test_new_document_unknown_model_leaves_previous_session_intact(valid_spm_path):
    """A failed new_document() call must not disturb the previous session."""
    import pytest

    state = AppState()
    state.open(valid_spm_path)
    first_session = state.active
    with pytest.raises(ValueError):
        state.new_document("NotAModel")
    assert state.active is first_session


# ---------------------------------------------------------------------------
# pin_reference / remove_reference (multi-reference Phase 1: append + cap)
# ---------------------------------------------------------------------------

def test_pin_reference_pins_a_snapshot(nmc_pouch_cell_path):
    state = AppState()

    outcome = state.pin_reference(nmc_pouch_cell_path)

    assert outcome is PinReferenceOutcome.PINNED
    assert len(state.references) == 1
    assert state.references[0].filename == nmc_pouch_cell_path.name
    assert state.references[0].model == "DFN"


def test_pin_reference_with_no_main_document_is_allowed(nmc_pouch_cell_path):
    """A reference-only workspace is a legal state (no main document open)."""
    state = AppState()
    assert state.active is None

    outcome = state.pin_reference(nmc_pouch_cell_path)

    assert outcome is PinReferenceOutcome.PINNED
    assert state.active is None
    assert state.references


def test_pin_reference_appends_in_pin_order(nmc_pouch_cell_path, valid_spm_path):
    """Pinning a second reference appends -- the silent replace died with
    the single-reference design."""
    state = AppState()
    state.pin_reference(nmc_pouch_cell_path)

    outcome = state.pin_reference(valid_spm_path)

    assert outcome is PinReferenceOutcome.PINNED
    assert [r.filename for r in state.references] == [
        nmc_pouch_cell_path.name,
        valid_spm_path.name,
    ]


def test_pin_reference_same_path_again_is_already_pinned(nmc_pouch_cell_path):
    state = AppState()
    state.pin_reference(nmc_pouch_cell_path)

    outcome = state.pin_reference(nmc_pouch_cell_path)

    assert outcome is PinReferenceOutcome.ALREADY_PINNED
    assert len(state.references) == 1  # unchanged


def test_pin_reference_matching_the_main_file_is_is_main(valid_spm_path):
    state = AppState()
    state.open(valid_spm_path)

    outcome = state.pin_reference(valid_spm_path)

    assert outcome is PinReferenceOutcome.IS_MAIN
    assert state.references == []  # nothing pinned


def test_fifth_pin_is_rejected_at_cap(valid_spm_path, tmp_path):
    state = AppState()
    paths = _copies(valid_spm_path, tmp_path, REFERENCE_PIN_CAP + 1)
    for path in paths[:REFERENCE_PIN_CAP]:
        assert state.pin_reference(path) is PinReferenceOutcome.PINNED
    assert state.at_reference_cap

    outcome = state.pin_reference(paths[REFERENCE_PIN_CAP])

    assert outcome is PinReferenceOutcome.AT_CAP
    assert len(state.references) == REFERENCE_PIN_CAP
    assert [r.path for r in state.references] == paths[:REFERENCE_PIN_CAP]


def test_repinning_an_already_pinned_path_at_cap_stays_already_pinned(
    valid_spm_path, tmp_path
):
    """Dedupe outranks the cap: re-pinning an existing pin at 4/4 is the
    quiet ALREADY_PINNED no-op, never a misleading AT_CAP."""
    state = AppState()
    paths = _copies(valid_spm_path, tmp_path, REFERENCE_PIN_CAP)
    for path in paths:
        state.pin_reference(path)

    assert state.pin_reference(paths[0]) is PinReferenceOutcome.ALREADY_PINNED


def test_close_leaves_the_references_untouched(valid_spm_path, nmc_pouch_cell_path):
    state = AppState()
    state.open(valid_spm_path)
    state.pin_reference(nmc_pouch_cell_path)

    state.close()

    assert state.active is None
    assert len(state.references) == 1
    assert state.references[0].filename == nmc_pouch_cell_path.name


def test_opening_a_new_main_leaves_the_references_untouched(
    valid_spm_path, nmc_pouch_cell_path, tmp_path
):
    state = AppState()
    state.open(valid_spm_path)
    state.pin_reference(nmc_pouch_cell_path)

    other = tmp_path / "other.json"
    shutil.copy(valid_spm_path, other)
    state.open(other)

    assert state.active.backing_file == other
    assert len(state.references) == 1
    assert state.references[0].filename == nmc_pouch_cell_path.name


def test_remove_reference_removes_exactly_that_pin(
    valid_spm_path, nmc_pouch_cell_path, tmp_path
):
    """Removing a middle pin shifts later pins up (decision D1: identity
    follows the current list index) and touches nothing else."""
    state = AppState()
    other = tmp_path / "other.json"
    shutil.copy(valid_spm_path, other)
    state.pin_reference(nmc_pouch_cell_path)
    state.pin_reference(valid_spm_path)
    state.pin_reference(other)
    middle = state.references[1]

    state.remove_reference(middle)

    assert [r.filename for r in state.references] == [
        nmc_pouch_cell_path.name,
        other.name,
    ]


def test_remove_reference_unknown_pin_is_a_quiet_noop(
    valid_spm_path, nmc_pouch_cell_path
):
    state = AppState()
    state.pin_reference(nmc_pouch_cell_path)
    stale = state.references[0]
    state.remove_reference(stale)

    state.remove_reference(stale)  # second click on an already-removed row

    assert state.references == []


def test_remove_reference_frees_a_cap_slot(valid_spm_path, tmp_path):
    state = AppState()
    paths = _copies(valid_spm_path, tmp_path, REFERENCE_PIN_CAP + 1)
    for path in paths[:REFERENCE_PIN_CAP]:
        state.pin_reference(path)
    state.remove_reference(state.references[0])

    assert state.pin_reference(paths[REFERENCE_PIN_CAP]) is PinReferenceOutcome.PINNED
    assert len(state.references) == REFERENCE_PIN_CAP


def test_reload_reference_keeps_the_other_pins_and_the_order(
    valid_spm_path, nmc_pouch_cell_path, tmp_path
):
    """The Source page's Reload re-snapshots the first pin in place --
    every other pin (and with it every badge identity) must survive."""
    state = AppState()
    first = tmp_path / "first.json"
    shutil.copy(valid_spm_path, first)
    state.pin_reference(first)
    state.pin_reference(nmc_pouch_cell_path)
    before = list(state.references)

    state.reload_reference()

    assert [r.filename for r in state.references] == [
        first.name,
        nmc_pouch_cell_path.name,
    ]
    assert state.references[0] is not before[0]  # genuinely re-snapshotted
    assert state.references[1] is before[1]  # untouched
