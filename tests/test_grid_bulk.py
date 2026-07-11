"""NumericGrid bulk affordances: expand toggle and clipboard paste.

The paste *dialog* is not exercised here (it is modal); the parsing is tested in
``test_paste.py`` and the write path -- ``apply_paste`` -- is tested directly,
which is where a bug would silently corrupt or drop data.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

from ui_qt.cards.grid import NumericGrid
from ui_qt.cards.paste_dialog import PastePreviewResult


@pytest.fixture(autouse=True)
def _qapp():
    yield QApplication.instance() or QApplication([])


def test_bulk_grid_has_expand_and_paste_affordances():
    """Paste has no button: it lives in the grid's right-click menu, and the
    same action's WidgetShortcut is what makes Ctrl+V work. Expand is a text
    action, matching the app's named-action convention."""
    grid = NumericGrid(("x", "y"))
    assert grid._expand_button is not None
    assert grid._expand_button.text() == "Expand"
    actions = [a.text() for a in grid._view.actions()]
    assert actions == ["Paste", "Add row", "Remove row"]


def test_non_bulk_grid_has_no_expand_or_paste():
    """The material map (bulk=False) is a tiny key/value grid: no expand, no
    paste in its context menu."""
    grid = NumericGrid(("Material", "Value"), text_columns=frozenset({0}), bulk=False)
    assert grid._expand_button is None
    assert grid._view.actions() == []


def test_expand_toggle_emits_and_relabels():
    grid = NumericGrid(("x", "y"))
    seen = []
    grid.expand_toggled.connect(seen.append)
    grid._toggle_expanded()
    assert seen == [True]
    assert grid.is_expanded is True
    assert grid._expand_button.text() == "Collapse"
    grid._toggle_expanded()
    assert seen == [True, False]
    assert grid.is_expanded is False
    assert grid._expand_button.text() == "Expand"


def test_apply_paste_replace_and_append_emit_changed():
    grid = NumericGrid(("x", "y"))
    grid.set_values([[0.0, 1.0]])
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.apply_paste([[2.0, 3.0], [4.0, 5.0]], PastePreviewResult.REPLACE)
    assert grid.values() == [[2.0, 3.0], [4.0, 5.0]]
    assert fired == [1]  # a paste is a user edit -> marks the card dirty

    grid.apply_paste([[6.0, 7.0]], PastePreviewResult.APPEND)
    assert grid.values() == [[2.0, 3.0], [4.0, 5.0], [6.0, 7.0]]
    assert fired == [1, 1]


def test_apply_paste_keeps_non_numeric_cells_verbatim():
    grid = NumericGrid(("x", "y"))
    grid.apply_paste([[0.0, "oops"]], PastePreviewResult.REPLACE)
    assert grid.values() == [[0.0, "oops"]]  # never coerced to 0


def test_set_expanded_is_reversible():
    grid = NumericGrid(("x",))
    compact = grid._view.maximumHeight()
    grid.set_expanded(True)
    assert grid._view.maximumHeight() > compact
    grid.set_expanded(False)
    assert grid._view.maximumHeight() == compact
