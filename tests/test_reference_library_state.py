"""State-layer contract for library-set references: ``ReferenceSnapshot.
from_library`` and ``AppState.pin_reference_set``.

A library snapshot is judged identically to a file snapshot (same
``BPXDocument`` derivation -- expectations below are read back from the
catalog/snapshot, never hand-written), its origin fields are mutually
exclusive (``path``/``mtime`` None, ``set_id`` set), and every path-based
flow (dedupe, reload, new-from-file) treats a path-less snapshot as a
guarded case rather than crashing on it. Pinning appends (multi-reference
Phase 1): sets and files pin side by side, never replacing each other.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.reference_library import list_reference_sets
from state.app_state import REFERENCE_PIN_CAP, AppState, PinReferenceOutcome
from state.reference_snapshot import ReferenceSnapshot

_CHEN = "pybamm/chen2020"
_PRADA = "pybamm/prada2013"
_AI = "pybamm/ai2020"
_MOHTAT = "pybamm/mohtat2020"

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
    # The Workspace pin detail's extra fields: the citation comes from the
    # file's own Header.References (the catalog reads the same field), the
    # BPX version from the same identity derivation as the model.
    assert snapshot.citation == entry.references
    assert snapshot.bpx_version
    # Bundled sets are pinned bpx-valid (test_reference_library.py); the
    # snapshot derives the same verdict through the same BPXDocument path.
    assert snapshot.error_count == 0
    assert snapshot.section_count > 0
    assert snapshot.parameter_count > 0


def test_file_snapshot_carries_no_citation():
    snapshot = ReferenceSnapshot.load(_SPM)
    assert snapshot.citation == ""
    assert snapshot.bpx_version


def test_from_library_rejects_an_unknown_id():
    with pytest.raises(KeyError):
        ReferenceSnapshot.from_library("pybamm/does_not_exist")
    with pytest.raises(KeyError):
        ReferenceSnapshot.from_library("liiondb/chen2020")


def test_pin_reference_set_pins_and_dedupes_by_set_id():
    state = AppState()

    assert state.pin_reference_set(_CHEN) is PinReferenceOutcome.PINNED
    pinned = state.references[0]
    assert pinned.set_id == _CHEN

    # Same set again: quiet no-op, the pinned snapshot is kept as-is.
    assert state.pin_reference_set(_CHEN) is PinReferenceOutcome.ALREADY_PINNED
    assert state.references == [pinned]


def test_pin_reference_set_appends_beside_another_set():
    state = AppState()
    state.pin_reference_set(_CHEN)

    assert state.pin_reference_set(_PRADA) is PinReferenceOutcome.PINNED
    assert [r.set_id for r in state.references] == [_CHEN, _PRADA]


def test_sets_and_files_pin_side_by_side():
    state = AppState()
    assert state.pin_reference(_SPM) is PinReferenceOutcome.PINNED

    # Library set beside the file reference -- the path dedupe must not
    # trip over the path-less snapshot (the guard, not a new behaviour).
    assert state.pin_reference_set(_CHEN) is PinReferenceOutcome.PINNED
    assert state.pin_reference(_SPM) is PinReferenceOutcome.ALREADY_PINNED
    assert [r.set_id for r in state.references] == [None, _CHEN]


def test_fifth_set_pin_is_rejected_at_cap():
    state = AppState()
    for set_id in (_CHEN, _PRADA, _AI, _MOHTAT):
        assert state.pin_reference_set(set_id) is PinReferenceOutcome.PINNED
    assert len(state.references) == REFERENCE_PIN_CAP

    assert state.pin_reference(_SPM) is PinReferenceOutcome.AT_CAP
    assert len(state.references) == REFERENCE_PIN_CAP


def test_reload_is_a_quiet_noop_for_a_first_pinned_library_set():
    state = AppState()
    state.pin_reference_set(_CHEN)
    pinned = state.references[0]

    state.reload_reference()

    assert state.references[0] is pinned


def test_new_from_file_pins_beside_a_pinned_library_set():
    state = AppState()
    state.pin_reference_set(_CHEN)

    outcome = state.new_from_file(_SPM)

    # The origin file pins alongside the library set -- pinning appends,
    # nothing is evicted; the path dedupe never crashed on the path-less
    # snapshot.
    assert outcome is PinReferenceOutcome.PINNED
    assert [r.set_id for r in state.references] == [_CHEN, None]
    assert state.references[1].path == _SPM
    assert state.active is not None and state.active.dirty
