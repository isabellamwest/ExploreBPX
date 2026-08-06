"""State-layer contract for library-set references: ``ReferenceSnapshot.
from_library`` and ``AppState.pin_reference_set``.

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
from state.app_state import AppState, PinReferenceOutcome
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
    # The one record shape: a bundled set carries a load record too -- no
    # disk facts (nothing backs it on disk) and never a comment fact.
    assert snapshot.record is not None
    assert snapshot.record.fmt == "json"
    assert snapshot.record.has_yaml_comments is False
    assert snapshot.record.size_bytes is None
    assert snapshot.record.mtime is None


def test_from_library_rejects_an_unknown_id():
    with pytest.raises(KeyError):
        ReferenceSnapshot.from_library("pybamm/does_not_exist")
    with pytest.raises(KeyError):
        ReferenceSnapshot.from_library("liiondb/chen2020")


def test_pin_reference_set_pins_and_dedupes_by_set_id():
    state = AppState()

    assert state.pin_reference_set(_CHEN) is PinReferenceOutcome.ADDED
    pinned = state.reference
    assert pinned is not None and pinned.set_id == _CHEN

    # Same set again: quiet no-op, the pinned snapshot is kept as-is.
    assert state.pin_reference_set(_CHEN) is PinReferenceOutcome.ALREADY_REFERENCE
    assert state.references == [pinned]


def test_pin_reference_set_appends_another_set():
    state = AppState()
    state.pin_reference_set(_CHEN)

    assert state.pin_reference_set(_PRADA) is PinReferenceOutcome.ADDED
    assert [reference.set_id for reference in state.references] == [_CHEN, _PRADA]


def test_library_sets_and_file_references_pin_side_by_side():
    state = AppState()
    assert state.pin_reference(_SPM) is PinReferenceOutcome.ADDED

    assert state.pin_reference_set(_CHEN) is PinReferenceOutcome.ADDED

    # The path dedupe must not trip over the path-less snapshot -- this is
    # the guard, not a new behaviour.
    assert state.pin_reference(_SPM) is PinReferenceOutcome.ALREADY_REFERENCE
    assert [reference.path for reference in state.references] == [_SPM, None]


def test_reload_is_a_quiet_noop_for_a_library_set():
    state = AppState()
    state.pin_reference_set(_CHEN)
    pinned = state.reference

    state.reload_reference()

    assert state.reference is pinned


def test_new_from_file_appends_beside_a_pinned_library_set():
    state = AppState()
    state.pin_reference_set(_CHEN)

    assert state.new_from_file(_SPM) is PinReferenceOutcome.ADDED

    # The origin file is pinned after the library set, which survives; the
    # guard means the path dedupe never crashed on the path-less snapshot.
    assert [reference.set_id for reference in state.references] == [_CHEN, None]
    assert state.references[1].path == _SPM
    assert state.active is not None and state.active.dirty
