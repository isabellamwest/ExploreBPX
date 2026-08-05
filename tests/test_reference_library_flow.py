"""Workspace-page workflows for the bundled reference library: the
References section's empty-state front door, pinning a bundled set, sets
and files pinned side by side, and the path-less guards (no stale band) --
all in domain terms via ``AppDriver``.

The modal dialog itself is covered in ``test_reference_library_dialog.py``;
here its ``exec``/``selected_set_id`` are stubbed at the class the window
constructs, so the click-through wiring is exercised without a blocking
modal loop (the ``_ask_open_intent`` idiom).
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module
from core.reference_library import list_reference_sets

_CHEN = "pybamm/chen2020"
_PRADA = "pybamm/prada2013"


def _entry(set_id: str):
    return next(s for s in list_reference_sets() if s.id == set_id)


def _stub_library_dialog(monkeypatch, accepted: bool, set_id: str = _CHEN) -> None:
    result = (
        main_window_module.QDialog.Accepted
        if accepted
        else main_window_module.QDialog.Rejected
    )
    monkeypatch.setattr(
        main_window_module.ReferenceLibraryDialog, "exec", lambda self: result
    )
    monkeypatch.setattr(
        main_window_module.ReferenceLibraryDialog,
        "selected_set_id",
        lambda self: set_id,
    )


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def test_library_button_pins_the_accepted_set(app_driver, monkeypatch):
    d = app_driver
    _stub_library_dialog(monkeypatch, accepted=True, set_id=_CHEN)

    d.click_reference_from_library()

    entry = _entry(_CHEN)
    assert d.reference_pin_count() == 1
    header = d.reference_pin_header_texts()[0]
    # The pin row shows the chip-length display name (the short title's
    # cell parenthetical dropped) and the model.
    assert entry.short_title.split(" (")[0] in header
    assert header.endswith(entry.model)
    assert d.toast_text() == f"{entry.short_title} · pinned as reference"


def test_cancelling_the_dialog_pins_nothing(app_driver, monkeypatch):
    d = app_driver
    _stub_library_dialog(monkeypatch, accepted=False)

    d.click_reference_from_library()

    assert d.reference_pin_count() == 0
    assert d.reference_empty_state_visible()
    assert d._w._state.references == []


def test_pinned_library_set_detail_shows_origin_and_citation(app_driver):
    d = app_driver
    d.pin_library_reference(_CHEN)

    d.toggle_reference_pin(0)

    detail = d.reference_pin_detail_text(0)
    entry = _entry(_CHEN)
    assert "Origin: Reference library · PyBaMM" in detail
    assert "Validity: Valid" in detail
    # A library set has no file path row; its citation row carries the
    # file's own Header.References verbatim.
    assert "File path:" not in detail
    if entry.references:
        assert f"Citation: {entry.references}" in detail

    d.click_reference_remove(0)

    assert d.reference_pin_count() == 0
    assert d.reference_empty_state_visible()
    assert d._w._state.references == []


def test_pinning_the_same_set_again_is_a_quiet_noop(app_driver):
    d = app_driver
    d.pin_library_reference(_CHEN)

    d.pin_library_reference(_CHEN)

    assert d.toast_text() == "Already pinned as reference"
    assert [r.set_id for r in d._w._state.references] == [_CHEN]


def test_sets_and_files_pin_side_by_side(app_driver, valid_spm_path, monkeypatch):
    """A library set beside a file reference -- pinning appends, no silent
    replace in either direction (the single-reference swap died with
    Phase 1)."""
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()

    d.pin_library_reference(_PRADA)

    assert d.reference_pin_count() == 2
    headers = d.reference_pin_header_texts()
    assert valid_spm_path.stem in headers[0]
    assert _entry(_PRADA).short_title.split(" (")[0] in headers[1]


def test_library_reference_powers_the_source_page_comparison(
    app_driver, valid_spm_path
):
    """The pinned set is an ordinary reference downstream: the Source page
    goes two-pane, headed by the set's display title, with no stale band
    (nothing on disk to go stale against)."""
    d = app_driver
    d.open(valid_spm_path)

    d.pin_library_reference(_CHEN)

    headers = d.source_pane_headers()
    assert headers is not None
    assert _entry(_CHEN).short_title in headers[1]
    assert headers[1].startswith("Reference")
    assert not d.source_stale_band_visible()
