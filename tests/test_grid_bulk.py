"""NumericGrid bulk affordances: expand toggle, clipboard paste, CSV import.

The paste *dialog* and the CSV mapping dialog are not exercised here (both are
modal): paste parsing is tested in ``test_paste.py``, the CSV parser and
mapping dialog in ``test_csv_import.py``. What lives here is what a bug would
silently corrupt or drop -- ``apply_paste`` and ``import_csv``'s write path,
with the dialog stubbed so it never blocks.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")

from PySide6.QtWidgets import QApplication

import ui_qt.cards.grid as grid_module
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


# ----------------------------------------------------------------------
# import_csv: opt-in, gated by the constructor's csv_import flag
# ----------------------------------------------------------------------


def test_csv_import_button_only_exists_when_opted_in():
    assert NumericGrid(("x", "y"))._import_button is None
    assert NumericGrid(("x", "y"), csv_import=True)._import_button is not None


class _StubCsvDialog:
    """Replaces the real (modal) CsvImportDialog for a test: records the
    constructor arguments it was built with and returns a canned choice
    without ever calling exec(), which would block headless."""

    #: The most recently constructed stub, for assertions on how it was built.
    last: "_StubCsvDialog | None" = None

    def __init__(self, data, targets, parent=None, **kwargs):
        self.data = data
        self.targets = targets
        self.kwargs = kwargs
        self.accepted_mapping = None
        self.accepted_mode = None
        _StubCsvDialog.last = self

    def exec(self) -> None:
        pass


def _stub_dialog(monkeypatch, mapping, mode=None):
    """Patch ``CsvImportDialog`` in the grid module to return *mapping*/*mode*
    as if the user had already confirmed them."""

    class _Configured(_StubCsvDialog):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.accepted_mapping = mapping
            self.accepted_mode = mode

    monkeypatch.setattr(grid_module, "CsvImportDialog", _Configured)


def _stub_file_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        grid_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


def test_import_csv_fills_the_grid_and_emits_changed(monkeypatch, tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("x,y\n0,1\n2,3\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, path)
    _stub_dialog(monkeypatch, mapping=(0, 1), mode=PastePreviewResult.REPLACE)

    grid = NumericGrid(("x", "y"), csv_import=True)
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.import_csv()

    assert grid.values() == [[0, 1], [2, 3]]
    assert fired == [1]


def test_import_csv_proposes_positional_columns_and_requires_all_targets(
    monkeypatch, tmp_path
):
    """Headed "Capacity,Voltage": a hostile header where ``auto_map(("x", "y"))``
    would propose ``(None, 0)`` -- "y" is a substring of "capacity", so y would
    be filled from the x column and x left unmapped. This only passes if the
    grid genuinely proposes :func:`~.csv_import.positional_map` and never
    falls back to ``auto_map``.
    """
    path = tmp_path / "table.csv"
    path.write_text("Capacity,Voltage\n0,1\n2,3\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, path)
    _stub_dialog(monkeypatch, mapping=(0, 1), mode=PastePreviewResult.REPLACE)

    grid = NumericGrid(("x", "y"), csv_import=True)
    grid.import_csv()

    built = _StubCsvDialog.last
    assert built.targets == ("x", "y")
    assert built.kwargs["proposed"] == (0, 1)  # positional_map, not auto_map
    assert built.kwargs["require_all_targets"] is True
    assert built.kwargs["offer_append"] is True


def test_import_csv_append_adds_to_the_existing_rows(monkeypatch, tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("x,y\n4,5\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, path)
    _stub_dialog(monkeypatch, mapping=(0, 1), mode=PastePreviewResult.APPEND)

    grid = NumericGrid(("x", "y"), csv_import=True)
    grid.set_values([[0, 1]])

    grid.import_csv()

    assert grid.values() == [[0, 1], [4, 5]]


def test_import_csv_replace_overwrites_the_existing_rows(monkeypatch, tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("x,y\n4,5\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, path)
    _stub_dialog(monkeypatch, mapping=(0, 1), mode=PastePreviewResult.REPLACE)

    grid = NumericGrid(("x", "y"), csv_import=True)
    grid.set_values([[0, 1], [2, 3]])

    grid.import_csv()

    assert grid.values() == [[4, 5]]


def test_import_csv_non_numeric_cells_survive_as_text_never_zero(monkeypatch, tmp_path):
    path = tmp_path / "table.csv"
    path.write_text("x,y\noops,1\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, path)
    _stub_dialog(monkeypatch, mapping=(0, 1), mode=PastePreviewResult.REPLACE)

    grid = NumericGrid(("x", "y"), csv_import=True)
    grid.import_csv()

    assert grid.values() == [["oops", 1]]


def test_import_csv_three_column_file_proposes_the_first_two_and_honours_an_override(
    monkeypatch, tmp_path
):
    """A 3-column file proposes columns 1 and 2 (positionally); overriding
    the mapping to column 3 for ``y`` is what actually gets written."""
    path = tmp_path / "table.csv"
    path.write_text("0,1,2\n3,4,5\n", encoding="utf-8")
    _stub_file_dialog(monkeypatch, path)
    _stub_dialog(monkeypatch, mapping=(0, 2), mode=PastePreviewResult.REPLACE)

    grid = NumericGrid(("x", "y"), csv_import=True)
    grid.import_csv()

    built = _StubCsvDialog.last
    assert built.kwargs["proposed"] == (0, 1)  # the proposal, before the override
    assert grid.values() == [[0, 2], [3, 5]]  # the override actually written


def test_import_csv_no_file_chosen_is_a_no_op(monkeypatch):
    monkeypatch.setattr(
        grid_module.QFileDialog, "getOpenFileName", lambda *a, **k: ("", "")
    )
    grid = NumericGrid(("x", "y"), csv_import=True)
    fired = []
    grid.changed.connect(lambda: fired.append(1))

    grid.import_csv()

    assert grid.values() == []
    assert fired == []
