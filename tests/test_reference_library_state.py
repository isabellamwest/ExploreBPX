"""State-layer contract for library-set references: ``ReferenceSnapshot.
from_library`` and ``AppState.open_reference_set``.

A library snapshot is judged identically to a file snapshot (same
``BPXDocument`` derivation -- expectations below are read back from the
catalog/snapshot, never hand-written), its origin fields are mutually
exclusive (``path``/``mtime`` None, ``set_id`` set), and every path-based
flow (dedupe, reload, new-from-file) treats a path-less snapshot as a
guarded case rather than crashing on it.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.reference_library import list_reference_sets
from state.app_state import AppState, OpenReferenceOutcome
from state.reference_snapshot import ReferenceSnapshot

_CHEN = "pybamm/chen2020"
_PRADA = "pybamm/prada2013"

_SPM = Path(__file__).parent / "fixtures" / "spm_example_valid.json"


def _catalog_entry(set_id: str):
    return next(s for s in list_reference_sets() if s.id == set_id)


def test_from_library_fields_mirror_the_catalog_and_the_document():
    snapshot = ReferenceSnapshot.from_library(_CHEN)
    entry = _catalog_entry(_CHEN)

    assert snapshot.set_id == _CHEN
    assert snapshot.path is None
    assert snapshot.mtime is None
    # The display label is the curated short title, where a file reference
    # carries its file name.
    assert snapshot.filename == entry.short_title
    assert snapshot.model == entry.model
    # Bundled sets are pinned bpx-valid (test_reference_library.py); the
    # snapshot derives the same verdict through the same BPXDocument path.
    assert snapshot.error_count == 0
    assert snapshot.section_count > 0
    assert snapshot.parameter_count > 0


def test_from_library_rejects_an_unknown_id():
    with pytest.raises(KeyError):
        ReferenceSnapshot.from_library("pybamm/does_not_exist")
    with pytest.raises(KeyError):
        ReferenceSnapshot.from_library("liiondb/chen2020")


def test_open_reference_set_docks_and_dedupes_by_set_id():
    state = AppState()

    assert state.open_reference_set(_CHEN) is OpenReferenceOutcome.ADDED
    docked = state.reference
    assert docked is not None and docked.set_id == _CHEN

    # Same set again: quiet no-op, the docked snapshot is kept as-is.
    assert state.open_reference_set(_CHEN) is OpenReferenceOutcome.ALREADY_REFERENCE
    assert state.reference is docked


def test_open_reference_set_replaces_another_set_silently():
    state = AppState()
    state.open_reference_set(_CHEN)

    assert state.open_reference_set(_PRADA) is OpenReferenceOutcome.ADDED
    assert state.reference.set_id == _PRADA


def test_open_reference_set_replaces_a_file_reference_and_vice_versa():
    state = AppState()
    assert state.open_reference(_SPM) is OpenReferenceOutcome.ADDED

    # Library set over file reference: silent replace.
    assert state.open_reference_set(_CHEN) is OpenReferenceOutcome.ADDED
    assert state.reference.path is None

    # File over library set: the path dedupe must not trip over the
    # path-less snapshot -- this is the guard, not a new behaviour.
    assert state.open_reference(_SPM) is OpenReferenceOutcome.ADDED
    assert state.reference.path == _SPM


def test_reload_is_a_quiet_noop_for_a_library_set():
    state = AppState()
    state.open_reference_set(_CHEN)
    docked = state.reference

    state.reload_reference()

    assert state.reference is docked


def test_new_from_file_replaces_a_docked_library_set():
    state = AppState()
    state.open_reference_set(_CHEN)

    state.new_from_file(_SPM)

    # The origin file docks as the reference (one-reference rule), evicting
    # the library set; the guard means the path dedupe never crashed.
    assert state.reference.path == _SPM
    assert state.reference.set_id is None
    assert state.active is not None and state.active.dirty
