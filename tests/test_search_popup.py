"""Focused tests for the SearchPopup navigation surface.

These exercise the search box's own behaviour — indexing objects and
parameters, name-over-path results, keyboard selection, staged Escape and
activation — in isolation from the rest of the window. End-to-end navigation
through the window is covered in ``test_workflows_ui.py``.
"""

from __future__ import annotations

import pytest

pytest.importorskip("PySide6")

from core.document import BPXDocument
from ui_qt.search import SearchBar

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
_CELL = ("Parameterisation", "Cell")


@pytest.fixture
def search(qtbot, valid_spm_bytes):
    bar = SearchBar()
    qtbot.addWidget(bar)
    bar.index_document(BPXDocument.from_bytes(valid_spm_bytes, "spm.json"))
    return bar


def test_index_covers_objects_and_parameters(search):
    kinds = {entry.kind for entry in search._entries}
    assert kinds == {"object", "parameter"}
    paths = {entry.path for entry in search._entries}
    assert _CELL in paths  # a navigable object
    assert _CAPACITY in paths  # a direct parameter


def test_results_show_name_over_path(search):
    search.setText("Nominal cell capacity")
    popup = search._popup
    assert popup.count() >= 1
    text = popup.item(0).text()
    assert "Nominal cell capacity [A.h]" in text
    assert "Parameterisation → Cell" in text


def test_path_matches_as_well_as_name(search):
    search.setText("Parameterisation → Cell")
    assert search._popup.count() >= 1


def test_arrow_keys_cycle_selection(search):
    search.setText("e")  # broad query -> several matches
    popup = search._popup
    assert popup.count() > 1
    assert popup.currentRow() == 0
    search._move_selection(1)
    assert popup.currentRow() == 1
    search._move_selection(-1)
    assert popup.currentRow() == 0
    # Cycling past the top wraps to the last row.
    search._move_selection(-1)
    assert popup.currentRow() == popup.count() - 1


def test_activation_emits_navigation_and_clears(search, qtbot):
    search.setText("Nominal cell capacity")
    item = search._popup.item(0)
    with qtbot.waitSignal(search.navigation_requested) as blocker:
        search._activate(item)
    assert blocker.args[0] == _CAPACITY
    assert search.text() == ""


def test_staged_escape_closes_then_clears_then_dismisses(search, qtbot):
    search.setText("Cell")
    assert search._popup.count() >= 1

    # First Escape closes the popup.
    search._on_escape(popup_open=True)
    assert search._popup.isVisible() is False

    # Second Escape (popup already closed) clears the text.
    search._on_escape(popup_open=False)
    assert search.text() == ""

    # Third Escape (empty) asks to leave the search entirely.
    with qtbot.waitSignal(search.dismissed):
        search._on_escape(popup_open=False)


def test_empty_query_hides_popup(search):
    search.setText("Cell")
    assert search._popup.count() >= 1
    search.setText("")
    assert search._popup.isVisible() is False
