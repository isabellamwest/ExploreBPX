"""Workspace-page workflows for the bundled reference library: the reference
card's empty-state front door, docking a bundled set, silent replace in
both directions, and the path-less guards (no Make main, no stale band) --
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


def test_library_button_docks_the_accepted_set(app_driver, monkeypatch):
    d = app_driver
    _stub_library_dialog(monkeypatch, accepted=True, set_id=_CHEN)

    d.click_reference_from_library()

    entry = _entry(_CHEN)
    assert d.reference_tile_visible()
    text = d.reference_tile_text()
    assert entry.short_title in text
    assert "Read-only" in text
    assert f"Model: {entry.model}" in text
    assert "Checked: Complete · Valid" in text
    assert d.toast_text() == f"{entry.short_title} · pinned as reference"


def test_cancelling_the_dialog_docks_nothing(app_driver, monkeypatch):
    d = app_driver
    _stub_library_dialog(monkeypatch, accepted=False)

    d.click_reference_from_library()

    assert not d.reference_tile_visible()
    assert d.reference_empty_state_visible()
    assert d._w._state.reference is None


def test_a_pinned_library_set_can_be_removed(app_driver):
    d = app_driver
    d.dock_library_reference(_CHEN)

    assert d.reference_tile_visible()

    d.click_reference_remove()

    assert not d.reference_tile_visible()
    assert d.reference_empty_state_visible()
    assert d._w._state.references == []


def test_pinning_the_same_set_again_is_a_quiet_noop(app_driver):
    d = app_driver
    d.dock_library_reference(_CHEN)

    d.dock_library_reference(_CHEN)

    assert d.toast_text() == "Already pinned as reference"
    assert [reference.set_id for reference in d._w._state.references] == [_CHEN]


def test_library_sets_and_file_references_pin_side_by_side(
    app_driver, valid_spm_path, monkeypatch
):
    """A file reference and a library set coexist -- pinning appends, so
    neither evicts the other."""
    d = app_driver
    _stub_open_dialog(monkeypatch, valid_spm_path)
    d.click_workspace_open_reference()

    d.dock_library_reference(_PRADA)

    assert d.pinned_reference_names() == [valid_spm_path.name, _entry(_PRADA).short_title]


def test_library_reference_powers_the_source_page_comparison(
    app_driver, valid_spm_path
):
    """The docked set is an ordinary reference downstream: the Source page
    goes two-pane, headed by the set's display title, with no stale band
    (nothing on disk to go stale against) and no ⇄ Make main."""
    d = app_driver
    d.open(valid_spm_path)

    d.dock_library_reference(_CHEN)

    headers = d.source_pane_headers()
    assert headers is not None
    assert _entry(_CHEN).short_title in headers[1]
    assert headers[1].startswith("Reference")
    assert not d.source_stale_band_visible()
