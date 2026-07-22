"""The Source page (multi-file track M5): rail entry, single-pane raw-JSON
rendering, folding, live re-render, the aligned two-pane comparison
(alignment, gaps, shared folding, per-state text styling), and the no-edit
invariant.

The aligned row model itself is covered in test_source_rows.py; this file
covers the page widget and its MainWindow wiring.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module
from ui_qt import style
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


class _RefStub:
    """The slice of ``ReferenceSnapshot`` the Source page consumes."""

    def __init__(self, raw, filename="reference.json", model="SPM"):
        self.raw = raw
        self.filename = filename
        self.model = model


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

    page.refresh(_DOC, reference=_RefStub(_DOC))
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
# Two-pane mode (step 3): keyed alignment, gaps, shared folding, styling.
# ---------------------------------------------------------------------------

_REF = {
    "Header": {"BPX": "0.1.0", "Title": "Ref cell", "Model": "SPM"},
    "Parameterisation": {
        "Cell": {
            "Reference temperature [K]": 298.15,
            "Nominal cell capacity [A.h]": 4.0,
            "Lower voltage cut-off [V]": 2.5,
        },
    },
}

_DOC_MAIN_ONLY = {
    "Header": dict(_DOC["Header"]),
    "Parameterisation": {
        "Cell": {
            "Reference temperature [K]": 298.15,
            "Nominal cell capacity [A.h]": 5.0,
            "Upper voltage cut-off [V]": 4.2,
        },
    },
}


def _two_pane(qtbot, main_raw, ref_raw):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(main_raw, reference=_RefStub(ref_raw))
    return page


def test_two_pane_alignment_with_gaps(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    assert len(main_texts) == len(ref_texts)

    # Equal and differing rows sit side by side at the same index.
    index = main_texts.index('"Nominal cell capacity [A.h]": 5.0')
    assert ref_texts[index] == '"Nominal cell capacity [A.h]": 4.0'

    # Ref-only slots in after the nearest preceding shared key, with a gap
    # (empty text) on the main side; main-only leaves the gap on the ref side.
    ref_only = ref_texts.index('"Lower voltage cut-off [V]": 2.5')
    assert ref_only == index + 1
    assert main_texts[ref_only] == ""
    main_only = main_texts.index('"Upper voltage cut-off [V]": 4.2')
    assert ref_texts[main_only] == ""


def test_two_pane_section_headers_count_their_own_side(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    index = main_texts.index("Cell  ·  3 parameters")
    assert ref_texts[index] == "Cell  ·  3 parameters"
    assert main_texts[0] == "Header  ·  3 parameters"


def test_fillable_renders_grey_key_without_value(qtbot):
    main = {"Parameterisation": {"Cell": {"Capacity": None}}}
    ref = {"Parameterisation": {"Cell": {"Capacity": 28700}}}
    page = _two_pane(qtbot, main, ref)

    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    index = main_texts.index('"Capacity":')
    assert ref_texts[index] == '"Capacity": 28700'
    line = page._view._lines[index]
    assert line.main.segments[0].color == style.GHOST_TEXT


def test_ref_only_rows_render_in_reference_purple(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    ref_texts = page._view.ref_line_texts()
    index = ref_texts.index('"Lower voltage cut-off [V]": 2.5')
    line = page._view._lines[index]
    assert line.main.gap is True
    assert line.ref.segments[0].color == style.REFERENCE


def test_ref_only_section_gaps_the_whole_main_side(qtbot):
    ref = dict(_REF)
    ref["State"] = {"SOC": 1.0}
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, ref)

    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    header = ref_texts.index("State  ·  1 parameter")
    child = ref_texts.index('"SOC": 1.0')
    assert main_texts[header] == ""
    assert main_texts[child] == ""
    header_line = page._view._lines[header]
    assert header_line.ref.segments[0].color == style.REFERENCE


def test_shared_fold_folds_both_panes(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    page._view.toggle_fold(("Header",))
    assert '"BPX": "0.1.0"' not in page._view.line_texts()
    assert '"BPX": "0.1.0"' not in page._view.ref_line_texts()

    page._view.toggle_fold(("Header",))
    assert '"BPX": "0.1.0"' in page._view.ref_line_texts()


def test_two_pane_table_pads_shorter_side_with_gaps(qtbot):
    main = {"Section": {"T": {"x": [1.0, 2.0], "y": [3.0, 4.0]}}}
    ref = {"Section": {"T": {"x": [1.0, 2.0, 9.0], "y": [3.0, 4.0, 5.0]}}}
    page = _two_pane(qtbot, main, ref)

    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    assert len(main_texts) == len(ref_texts)
    # The reference table is two JSON lines longer; the main side carries
    # exactly that many gap lines, each beside the extra entry itself
    # (inside the table), so shared lines like "]" stay paired.
    assert main_texts.count("") == 2
    assert ref_texts.count("") == 0
    gaps = [i for i, text in enumerate(main_texts) if text == ""]
    assert [ref_texts[i] for i in gaps] == ["9.0", "5.0"]


def test_two_pane_closed_table_summarises_both_sides(qtbot):
    main = {"Section": {"T": {"x": [1.0], "y": [2.0]}}}
    ref = {"Section": {"T": {"x": [1.0], "y": [3.0]}}}
    page = _two_pane(qtbot, main, ref)

    page._view.toggle_fold(("Section", "T"))
    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    index = main_texts.index('"T": table')
    assert ref_texts[index] == '"T": table'


def test_pane_headers_show_roles_names_and_models(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(_DOC, reference=None)
    assert page._pane_head.isHidden()

    page.refresh(
        _DOC,
        reference=_RefStub(_REF, filename="lfp.json", model="SPMe"),
        main_name="nmc.json",
        main_model="DFN",
    )
    assert not page._pane_head.isHidden()
    assert page._main_head.text() == "Main  ·  nmc.json  ·  DFN"
    assert page._ref_head.text() == "◇ Reference  ·  lfp.json  ·  SPMe"


def test_two_pane_page_still_has_no_input_widget(qtbot):
    from PySide6.QtWidgets import (
        QAbstractSpinBox,
        QComboBox,
        QLineEdit,
        QPlainTextEdit,
        QTextEdit,
    )

    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    assert not page.findChildren(QLineEdit)
    assert not page.findChildren(QComboBox)
    assert not page.findChildren(QAbstractSpinBox)
    assert not page.findChildren(QTextEdit)
    assert not page.findChildren(QPlainTextEdit)


# ---------------------------------------------------------------------------
# Value chips (step 4): chip placement per state, values only.
# ---------------------------------------------------------------------------


def test_differs_chips_the_value_on_both_sides(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    chips = page._view.chipped_texts()
    index = page._view.line_texts().index('"Nominal cell capacity [A.h]": 5.0')
    assert (index, "main", "5.0") in chips
    assert (index, "ref", "4.0") in chips
    # Values only -- no chip ever contains a key.
    assert not any("Nominal" in text for _, _, text in chips)


def test_equal_main_only_and_ref_only_rows_carry_no_chip(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    chip_lines = {index for index, _, _ in page._view.chipped_texts()}
    main_texts = page._view.line_texts()
    ref_texts = page._view.ref_line_texts()
    assert main_texts.index('"Reference temperature [K]": 298.15') not in chip_lines
    assert main_texts.index('"Upper voltage cut-off [V]": 4.2') not in chip_lines
    assert ref_texts.index('"Lower voltage cut-off [V]": 2.5') not in chip_lines


def test_fillable_chips_the_reference_side_value_only(qtbot):
    main = {"Parameterisation": {"Cell": {"Capacity": None}}}
    ref = {"Parameterisation": {"Cell": {"Capacity": 28700}}}
    page = _two_pane(qtbot, main, ref)

    assert [
        (side, text) for _, side, text in page._view.chipped_texts()
    ] == [("ref", "28700")]


def test_function_string_chips_only_the_differing_tokens(qtbot):
    main = {"Parameterisation": {"Cell": {"D": "8.3e-4 * exp(-4300 / T)"}}}
    ref = {"Parameterisation": {"Cell": {"D": "6.1e-4 * exp(-4300 / T)"}}}
    page = _two_pane(qtbot, main, ref)

    chips = page._view.chipped_texts()
    assert [(side, text) for _, side, text in chips] == [
        ("main", "8.3e-4"),
        ("ref", "6.1e-4"),
    ]
    # The full line still reads as the whole JSON value.
    index = chips[0][0]
    assert page._view.line_texts()[index] == '"D": "8.3e-4 * exp(-4300 / T)"'


def test_open_table_chips_changed_entries_not_extras(qtbot):
    main = {"Section": {"T": {"x": [1.0, 2.0], "y": [3.0, 4.0]}}}
    ref = {"Section": {"T": {"x": [1.0, 2.0], "y": [3.5, 4.0, 5.0]}}}
    page = _two_pane(qtbot, main, ref)

    chips = page._view.chipped_texts()
    texts = {(side, text) for _, side, text in chips}
    # The changed entry chips on both sides; the trailing-comma pair
    # ("4.0" vs "4.0,") and the extra entry facing a gap do not.
    assert ("main", "3.0,") in texts
    assert ("ref", "3.5,") in texts
    assert not any("4.0" in text for text in [t for _, t in texts])
    assert not any("5.0" in text for text in [t for _, t in texts])


def test_closed_table_chips_the_table_word_when_it_differs(qtbot):
    main = {"Section": {"T": {"x": [1.0], "y": [2.0]}}}
    ref = {"Section": {"T": {"x": [1.0], "y": [3.0]}}}
    page = _two_pane(qtbot, main, ref)
    page._view.toggle_fold(("Section", "T"))

    chips = page._view.chipped_texts()
    index = page._view.line_texts().index('"T": table')
    assert (index, "main", "table") in chips
    assert (index, "ref", "table") in chips


def test_closed_equal_table_stays_plain(qtbot):
    same = {"Section": {"T": {"x": [1.0], "y": [2.0]}}}
    page = _two_pane(qtbot, same, {"Section": {"T": {"x": [1.0], "y": [2.0]}}})
    page._view.toggle_fold(("Section", "T"))

    assert page._view.chipped_texts() == []


def test_collapsed_section_with_differences_chips_its_dots(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    page._view.toggle_fold(("Parameterisation",))

    chips = page._view.chipped_texts()
    main_texts = page._view.line_texts()
    index = next(
        i for i, text in enumerate(main_texts)
        if text.startswith("Parameterisation  ·  3 parameters")
    )
    assert main_texts[index].endswith("⋯")
    assert (index, "main", "⋯") in chips
    assert (index, "ref", "⋯") in chips

    # An equal collapsed section stays plain: Header differs only in Title
    # here, so build an equal one explicitly.
    equal = {"Header": dict(_DOC["Header"])}
    page2 = _two_pane(qtbot, equal, {"Header": dict(_DOC["Header"])})
    page2._view.toggle_fold(("Header",))
    assert page2._view.chipped_texts() == []


def test_ref_only_section_header_carries_no_dots_chip(qtbot):
    ref = dict(_REF)
    ref["State"] = {"SOC": 1.0}
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, ref)

    ref_texts = page._view.ref_line_texts()
    header = ref_texts.index("State  ·  1 parameter")
    page._view.toggle_fold(("State",))
    chips = page._view.chipped_texts()
    assert not any(index == header and text == "⋯" for index, _, text in chips)


def test_single_pane_never_chips(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)

    assert page._view.chipped_texts() == []


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


def test_source_two_pane_follows_reference_dock(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY)).show_view("Source")
    assert app_driver.source_ref_line_texts() == []
    assert app_driver.source_pane_headers() is None

    _stub_open_dialog(monkeypatch, _write(tmp_path, "reference.json", _REF))
    app_driver.show_view("Workspace").click_workspace_open_reference()
    app_driver.show_view("Source")

    ref_texts = app_driver.source_ref_line_texts()
    assert '"Nominal cell capacity [A.h]": 4.0' in ref_texts
    assert len(ref_texts) == len(app_driver.source_line_texts())
    headers = app_driver.source_pane_headers()
    assert headers is not None
    assert headers[0].startswith("Main")
    assert "reference.json" in headers[1]

    app_driver.click_reference_remove()
    assert app_driver.source_ref_line_texts() == []
    assert app_driver.source_pane_headers() is None
