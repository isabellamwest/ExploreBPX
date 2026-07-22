"""The Source page (multi-file track M5): rail entry, single-pane raw-JSON
rendering, folding, live re-render, and the no-edit invariant.

The aligned row model itself is covered in test_source_rows.py; this file
covers the page widget and its MainWindow wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module
from ui_qt.source_page import SourcePage

_DOC = {
    "Header": {"BPX": "0.1.0", "Title": "Test cell", "Model": "SPM"},
    "Parameterisation": {
        "Cell": {
            "Reference temperature [K]": 298.15,
            "Nominal cell capacity [A.h]": 5.0,
        },
    },
}


def _write(tmp_path: Path, name: str, raw: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


# ---------------------------------------------------------------------------
# Page-level unit tests (no MainWindow).
# ---------------------------------------------------------------------------


def test_lines_follow_document_order(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(_DOC)

    texts = page._view.line_texts()
    assert texts == [
        "Header  ·  3 parameters",
        '"BPX": "0.1.0"',
        '"Title": "Test cell"',
        '"Model": "SPM"',
        "Parameterisation  ·  2 parameters",
        "Cell  ·  2 parameters",
        '"Reference temperature [K]": 298.15',
        '"Nominal cell capacity [A.h]": 5.0',
    ]


def test_section_fold_hides_children_and_unfold_restores(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)

    page._view.toggle_fold(("Header",))
    folded = page._view.line_texts()
    assert "Header  ·  3 parameters" in folded
    assert '"BPX": "0.1.0"' not in folded

    page._view.toggle_fold(("Header",))
    assert '"BPX": "0.1.0"' in page._view.line_texts()


def test_folding_a_parent_hides_nested_sections_too(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)

    page._view.toggle_fold(("Parameterisation",))
    texts = page._view.line_texts()
    assert "Cell  ·  2 parameters" not in texts
    assert '"Reference temperature [K]": 298.15' not in texts


def test_table_renders_whole_and_closes_to_summary(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    raw = {
        "Section": {
            "T": {"x": [1.0, 2.0], "y": [3.0, 4.0]},
        },
    }

    page.refresh(raw)
    open_texts = page._view.line_texts()
    assert '"T": {' in open_texts
    assert any("1.0" in text for text in open_texts)

    page._view.toggle_fold(("Section", "T"))
    closed_texts = page._view.line_texts()
    assert '"T": table' in closed_texts
    assert not any("1.0" in text for text in closed_texts)


def test_fold_state_survives_refresh_but_prunes_removed_paths(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)
    page._view.toggle_fold(("Header",))

    # A re-render (same shape) keeps the fold.
    page.refresh(_DOC)
    assert '"BPX": "0.1.0"' not in page._view.line_texts()

    # The folded section disappearing prunes its entry: when it comes back
    # it renders open, not haunted by stale state.
    page.refresh({"Other": {"K": 1}})
    page.refresh(_DOC)
    assert '"BPX": "0.1.0"' in page._view.line_texts()


def test_no_document_renders_nothing(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)

    page.refresh(None)

    assert page._view.line_texts() == []
    assert page._hint.isHidden()


def test_hint_visible_only_with_document_and_no_reference(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(_DOC, reference=None)
    assert not page._hint.isHidden()

    page.refresh(_DOC, reference=object())
    assert page._hint.isHidden()


def test_page_contains_no_input_widget(qtbot):
    from PySide6.QtWidgets import (
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QPlainTextEdit,
        QTextEdit,
    )

    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)

    assert not page.findChildren(QLineEdit)
    assert not page.findChildren(QComboBox)
    assert not page.findChildren(QAbstractSpinBox)
    assert not page.findChildren(QTextEdit)
    assert not page.findChildren(QPlainTextEdit)


# ---------------------------------------------------------------------------
# MainWindow wiring, through the driver.
# ---------------------------------------------------------------------------


def test_source_rail_entry_gated_on_open_document(app_driver, tmp_path):
    assert app_driver.source_rail_enabled() is False

    app_driver.open(_write(tmp_path, "main.json", _DOC))
    assert app_driver.source_rail_enabled() is True

    app_driver.show_view("Source")
    assert app_driver.current_view_name() == "Source"


def test_source_page_renders_open_document(app_driver, tmp_path):
    app_driver.open(_write(tmp_path, "main.json", _DOC)).show_view("Source")

    texts = app_driver.source_line_texts()
    assert '"Title": "Test cell"' in texts
    assert "Cell  ·  2 parameters" in texts
    assert app_driver.source_has_input_widget() is False


def test_source_page_rerenders_on_edit_and_undo(app_driver, tmp_path):
    app_driver.open(_write(tmp_path, "main.json", _DOC))
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    app_driver.edit_field("6.5").commit()

    app_driver.show_view("Source")
    assert '"Nominal cell capacity [A.h]": 6.5' in app_driver.source_line_texts()

    app_driver.undo()
    assert '"Nominal cell capacity [A.h]": 5.0' in app_driver.source_line_texts()


def test_source_hint_clears_when_reference_docks(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC)).show_view("Source")
    assert app_driver.source_hint_visible() is True

    _stub_open_dialog(monkeypatch, _write(tmp_path, "reference.json", _DOC))
    app_driver.show_view("Workspace").click_workspace_open_reference()

    assert app_driver.source_hint_visible() is False

    app_driver.click_reference_remove()
    assert app_driver.source_hint_visible() is True
