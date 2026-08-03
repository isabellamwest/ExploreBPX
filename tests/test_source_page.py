"""The Source page: rail entry, single-pane raw-JSON rendering, folding,
live re-render, the aligned two-pane comparison (alignment, gaps, shared
folding, per-state text styling), and the no-edit invariant.

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

    def __init__(self, raw, filename="reference.json", model="SPM", path=Path("reference.json")):
        self.raw = raw
        self.filename = filename
        self.model = model
        # A file-backed reference by default; pass ``path=None`` to stand in
        # for a bundled library set, which hides ⇄ Make main.
        self.path = path


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
# Two-pane mode: keyed alignment, gaps, shared folding, styling.
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
    assert page._ref_head.text() == "Reference  ·  lfp.json  ·  SPMe"


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
# Value chips: chip placement per state, values only.
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
# ← gutter pulls: presence per state, hit-testing, no page edits.
# ---------------------------------------------------------------------------


def test_pull_chip_presence_follows_the_frames_rules(qtbot):
    main = {
        "Header": {"BPX": "0.1.0", "Model": "SPM"},
        "Parameterisation": {
            "Cell": {
                "Equal": 1.0,
                "Differs": 5.0,
                "Fillable": None,
                "Main only": 4.2,
            },
            "T": {"x": [1.0], "y": [2.0]},
        },
    }
    ref = {
        "Header": {"BPX": "0.1.0", "Model": "SPM"},
        "Parameterisation": {
            "Cell": {
                "Equal": 1.0,
                "Differs": 4.0,
                "Fillable": 2.0,
                "Ref only": 2.5,
            },
            "T": {"x": [1.0], "y": [3.0]},
        },
        "State": {"SOC": 1.0},
    }
    page = _two_pane(qtbot, main, ref)

    pulls = {path: is_section for _, path, is_section in page._view.pull_lines()}
    cell = ("Parameterisation", "Cell")
    assert pulls[cell + ("Differs",)] is False
    assert pulls[cell + ("Fillable",)] is False
    assert pulls[cell + ("Ref only",)] is False
    # A differing table pulls whole from its key line -- exactly one chip.
    assert pulls[("Parameterisation", "T")] is False
    assert [p for _, p, _ in page._view.pull_lines()].count(("Parameterisation", "T")) == 1
    # A ref-only section pulls whole from its header.
    assert pulls[("State",)] is True
    assert pulls[("State", "SOC")] is False
    # Absent entirely on equal and main-only rows, and on shared headers.
    assert cell + ("Equal",) not in pulls
    assert cell + ("Main only",) not in pulls
    assert cell not in pulls
    assert ("Header",) not in pulls


def test_single_pane_shows_no_pull_chips(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC)

    assert page._view.pull_lines() == []


def test_gutter_click_emits_pull_and_pane_click_does_not(qtbot):
    from PySide6.QtCore import QPoint, Qt
    from PySide6.QtTest import QTest

    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    view = page._view
    view.resize(600, 400)

    received = []
    view.pull_requested.connect(lambda path, is_section: received.append((path, is_section)))

    index, path, _ = next(
        entry for entry in view.pull_lines()
        if entry[1] == ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
    )
    line_height = view._line_height()
    y = index * line_height + line_height // 2
    gutter_x = view._pane_width() + 5

    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(gutter_x, y))
    assert received == [(path, False)]

    # Inside the main pane the same line is not a pull; and the gutter on
    # an equal row does nothing at all.
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(30, y))
    equal_index = view.line_texts().index('"Reference temperature [K]": 298.15')
    equal_y = equal_index * line_height + line_height // 2
    QTest.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(gutter_x, equal_y))
    assert received == [(path, False)]


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


def _dock_reference(app_driver, tmp_path, monkeypatch, ref_raw):
    _stub_open_dialog(monkeypatch, _write(tmp_path, "reference.json", ref_raw))
    app_driver.show_view("Workspace").click_workspace_open_reference()
    return app_driver.show_view("Source")


def test_source_pull_copies_value_and_shares_the_undo_stack(
    app_driver, tmp_path, monkeypatch
):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)
    path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")

    app_driver.source_pull(path)

    # The pull landed verbatim; the row is now equal, so its chip and its
    # ← are both gone -- the page re-rendered live through the same
    # fan-out as any edit.
    texts = app_driver.source_line_texts()
    assert '"Nominal cell capacity [A.h]": 4.0' in texts
    assert path not in [p for p, _ in app_driver.source_pull_paths()]
    pulled_line = texts.index('"Nominal cell capacity [A.h]": 4.0')
    assert not any(
        index == pulled_line for index, _, _ in app_driver.source_chipped_texts()
    )

    # One undo entry, on the same stack every page shares.
    app_driver.undo()
    assert '"Nominal cell capacity [A.h]": 5.0' in app_driver.source_line_texts()
    assert path in [p for p, _ in app_driver.source_pull_paths()]


def test_source_section_pull_is_one_undo_entry(app_driver, tmp_path, monkeypatch):
    ref = dict(_REF)
    ref["State"] = {"SOC": 1.0, "Temperature [K]": 298.15}
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, ref)

    app_driver.source_pull(("State",))

    texts = app_driver.source_line_texts()
    assert "State  ·  2 parameters" in texts
    assert '"SOC": 1.0' in texts
    assert '"Temperature [K]": 298.15' in texts

    # The whole section arrives -- and leaves -- as one undo entry.
    app_driver.undo()
    texts = app_driver.source_line_texts()
    assert '"SOC": 1.0' not in texts
    assert ("State",) in [p for p, _ in app_driver.source_pull_paths()]


def test_source_pull_of_missing_path_is_impossible(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    with pytest.raises(AssertionError):
        app_driver.source_pull(("Parameterisation", "Cell", "Upper voltage cut-off [V]"))


def test_source_pull_stays_on_the_source_page(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)
    path = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")

    app_driver.source_pull(path)

    # The page's rhythm is next ›, pull, next ›, pull -- confirmation
    # happens in place (the row's transient "Pulled" tag), never a page
    # switch. The Editor is opt-in: the toast's action, or a double-click.
    assert app_driver.current_view_name() == "Source"
    assert app_driver.source_flash_path() == path


def test_source_pull_toast_offers_the_editor(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    app_driver.source_pull(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    assert app_driver.toast_text() == "Pulled Nominal cell capacity [A.h]"
    assert app_driver.toast_action_text() == "Show in Editor"

    # The action is the one deliberate road to the Editor -- and it lands
    # on the pulled parameter, exactly where the old forced jump did.
    app_driver.toast_click_action()
    assert app_driver.current_view_name() == "Editor"
    assert app_driver.inspector_title() == "Nominal cell capacity [A.h]"


def test_enter_pulls_the_selected_difference(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    app_driver.source_step(+1)
    selected = app_driver.source_selected_path()
    assert selected in [p for p, _ in app_driver.source_pull_paths()]

    app_driver.source_press_key("enter")

    # The keyboard counterpart of the ← chip: the value landed, the chip
    # is gone, and the page stayed put for the next › / Enter.
    assert app_driver.current_view_name() == "Source"
    assert selected not in [p for p, _ in app_driver.source_pull_paths()]
    assert app_driver.source_flash_path() == selected

    # Enter on the now-equal row is inert -- equal rows stay as impossible
    # to pull from the keyboard as from the gutter.
    before = app_driver.source_pull_paths()
    app_driver.source_press_key("enter")
    assert app_driver.source_pull_paths() == before


# ---------------------------------------------------------------------------
# Toolbar (‹ › stepper, ⇄ Make main, single-pane label) + stale band.
# ---------------------------------------------------------------------------

_CAPACITY = ("Parameterisation", "Cell", "Nominal cell capacity [A.h]")
_LOWER_CUTOFF = ("Parameterisation", "Cell", "Lower voltage cut-off [V]")


def test_toolbar_single_pane_shows_label_and_hint_only(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(_DOC, main_name="main.json", main_model="SPM")

    assert not page._file_label.isHidden()
    assert page._file_label.text() == "main.json  ·  SPM"
    assert not page._hint.isHidden()
    assert page._prev_button.isHidden()
    assert page._next_button.isHidden()
    assert page._toolbar_sep.isHidden()
    assert page._make_main_button.isHidden()


def test_toolbar_two_pane_shows_stepper_and_make_main_only(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)

    assert page._file_label.isHidden()
    assert page._hint.isHidden()
    assert not page._prev_button.isHidden()
    assert not page._next_button.isHidden()
    assert not page._toolbar_sep.isHidden()
    assert not page._make_main_button.isHidden()
    assert page._make_main_button.text() == "⇄ Make main"


def test_toolbar_hides_make_main_for_a_library_reference(qtbot):
    """A bundled library-set reference has no file on disk to promote, so
    ⇄ Make main hides rather than sit as a dead control; the stepper is
    unaffected."""
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC_MAIN_ONLY, reference=_RefStub(_REF, path=None))

    assert page._make_main_button.isHidden()
    assert not page._prev_button.isHidden()
    assert not page._next_button.isHidden()


def test_toolbar_empty_without_a_document(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(None)

    assert page._file_label.isHidden()
    assert page._hint.isHidden()
    assert page._prev_button.isHidden()
    assert page._make_main_button.isHidden()


def test_single_pane_label_omits_a_missing_model(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(_DOC, main_name="main.json", main_model=None)

    assert page._file_label.text() == "main.json"


def test_stepper_disabled_not_hidden_without_differences(qtbot):
    # Identical files keep the ‹ › buttons in place, greyed.
    page = _two_pane(qtbot, _DOC, _DOC)

    assert not page._prev_button.isHidden()
    assert not page._next_button.isHidden()
    assert not page._prev_button.isEnabled()
    assert not page._next_button.isEnabled()

    # Still visible, and no page ever steps: a disabled click is inert.
    page._next_button.click()
    assert page._view.selected_path() is None


def test_stepper_walks_differences_in_file_order_and_wraps(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    view = page._view

    assert page._next_button.isEnabled()
    page._next_button.click()
    assert view.selected_path() == ("Header", "Title")
    page._next_button.click()
    assert view.selected_path() == _CAPACITY
    page._next_button.click()
    assert view.selected_path() == _LOWER_CUTOFF
    page._next_button.click()  # wraps to the first difference
    assert view.selected_path() == ("Header", "Title")
    page._prev_button.click()  # and backwards off the front, to the last
    assert view.selected_path() == _LOWER_CUTOFF


def test_stepper_steps_into_a_collapsed_section(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    view = page._view

    view.toggle_fold(("Parameterisation", "Cell"))
    assert '"Nominal cell capacity [A.h]": 5.0' not in view.line_texts()

    page._next_button.click()  # Title
    page._next_button.click()  # capacity -- inside the folded Cell
    assert view.selected_path() == _CAPACITY
    assert '"Nominal cell capacity [A.h]": 5.0' in view.line_texts()


def test_pane_click_places_the_selection(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    view = page._view
    view.resize(900, 500)

    # Line 2 is '"Title": …' (0 Header, 1 BPX, 2 Title); click its main pane.
    from PySide6.QtCore import QPoint, Qt

    y = 2 * view._line_height() + 2
    qtbot.mouseClick(view.viewport(), Qt.LeftButton, pos=QPoint(120, y))

    assert view.selected_path() == ("Header", "Title")

    # Stepping continues from the clicked row, not from the top.
    page._next_button.click()
    assert view.selected_path() == _CAPACITY


def test_selection_prunes_when_its_row_vanishes(qtbot):
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    page._view.reveal(("Header", "Title"))
    assert page._view.selected_path() == ("Header", "Title")

    without_title = {
        "Header": {"BPX": "0.1.0", "Model": "SPM"},
        "Parameterisation": _DOC_MAIN_ONLY["Parameterisation"],
    }
    page.refresh(without_title, reference=_RefStub(without_title))

    assert page._view.selected_path() is None


def test_selection_paint_smoke(qtbot):
    # Offscreen render with a selection outline must not crash (the text
    # readers cannot disprove paint-path bugs).
    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    page.resize(900, 500)
    page._view.reveal(("Header", "Title"))
    page.grab()


def test_set_stale_needs_a_docked_reference(qtbot):
    page = SourcePage()
    qtbot.addWidget(page)

    page.refresh(_DOC, main_name="main.json")
    page.set_stale(True)
    assert page._stale_band.isHidden()

    page.refresh(_DOC, reference=_RefStub(_REF))
    page.set_stale(True)
    assert not page._stale_band.isHidden()

    # Undocking takes the band with it.
    page.refresh(_DOC, main_name="main.json")
    assert page._stale_band.isHidden()


# -- MainWindow wiring (driver level) ---------------------------------------


def test_stepper_disables_once_pulls_remove_every_difference(
    app_driver, tmp_path, monkeypatch
):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    assert app_driver.source_stepper_visible() is True
    assert app_driver.source_stepper_enabled() is True

    app_driver.source_pull(("Header", "Title"))
    app_driver.source_pull(_CAPACITY)
    assert app_driver.source_stepper_enabled() is True
    app_driver.source_pull(_LOWER_CUTOFF)

    # Three pulls, one visit: the page never navigated away between them
    # (the whole point of the stay-put pull).
    assert app_driver.current_view_name() == "Source"
    # Only the main-only row differs now -- not a target (frames rule).
    assert app_driver.source_stepper_enabled() is False


def test_source_make_main_runs_the_full_swap(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)
    assert app_driver.source_make_main_visible() is True

    app_driver.source_make_main()

    headers = app_driver.source_pane_headers()
    assert headers is not None
    assert "reference.json" in headers[0]  # promoted to Main
    assert "main.json" in headers[1]  # demoted to the reference pane


def _bump_on_disk(path: Path, raw: dict) -> None:
    """Rewrite *path* with *raw* and force a visibly newer mtime (coarse
    filesystem timestamps must not make the change invisible)."""
    import os

    path.write_text(json.dumps(raw), encoding="utf-8")
    stamp = path.stat().st_mtime + 10
    os.utime(path, (stamp, stamp))


def test_stale_band_appears_on_page_entry_and_reload_resnapshots(
    app_driver, tmp_path, monkeypatch
):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)
    assert app_driver.source_stale_band_visible() is False

    changed = {
        "Header": dict(_REF["Header"]),
        "Parameterisation": {
            "Cell": dict(
                _REF["Parameterisation"]["Cell"],
                **{"Nominal cell capacity [A.h]": 3.5},
            ),
        },
    }
    _bump_on_disk(tmp_path / "reference.json", changed)

    # No watcher: nothing notices until the page is (re-)entered.
    assert app_driver.source_stale_band_visible() is False
    app_driver.show_view("Workspace")
    app_driver.show_view("Source")
    assert app_driver.source_stale_band_visible() is True

    # The panes still show the docked snapshot until Reload is chosen.
    assert '"Nominal cell capacity [A.h]": 4.0' in app_driver.source_ref_line_texts()

    app_driver.source_reload()
    assert app_driver.source_stale_band_visible() is False
    assert '"Nominal cell capacity [A.h]": 3.5' in app_driver.source_ref_line_texts()


def test_window_activation_is_a_stale_notice_point(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    _bump_on_disk(tmp_path / "reference.json", _REF)
    assert app_driver.source_stale_band_visible() is False

    app_driver.notice_window_activation()
    assert app_driver.source_stale_band_visible() is True


def test_reload_failure_keeps_snapshot_and_band(app_driver, tmp_path, monkeypatch):
    # An unreadable file at Reload surfaces the standard error; nothing
    # mutates.
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    ref_path = tmp_path / "reference.json"
    _bump_on_disk(ref_path, _REF)
    app_driver.notice_window_activation()
    assert app_driver.source_stale_band_visible() is True

    ref_path.unlink()
    errors = []
    monkeypatch.setattr(
        main_window_module.QMessageBox,
        "critical",
        lambda *args, **kwargs: errors.append(args),
    )
    app_driver.source_reload()

    assert errors, "the standard Cannot-open-file error must surface"
    assert app_driver.source_stale_band_visible() is True
    assert '"Nominal cell capacity [A.h]": 4.0' in app_driver.source_ref_line_texts()


def test_vanished_file_never_conjures_a_band(app_driver, tmp_path, monkeypatch):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    (tmp_path / "reference.json").unlink()
    app_driver.show_view("Workspace")
    app_driver.show_view("Source")
    app_driver.notice_window_activation()

    assert app_driver.source_stale_band_visible() is False


# ---------------------------------------------------------------------------
# Up/Down row navigation + double-click Editor jump.
# ---------------------------------------------------------------------------


def _key(view, key) -> None:
    from PySide6.QtTest import QTest

    QTest.keyClick(view, key)


def test_arrows_walk_visible_rows_and_stop_at_the_ends(qtbot):
    from PySide6.QtCore import Qt

    page = _two_pane(qtbot, _DOC_MAIN_ONLY, _REF)
    view = page._view

    _key(view, Qt.Key_Down)
    assert view.selected_path() == ("Header",)
    _key(view, Qt.Key_Up)  # top: stays, no wrap
    assert view.selected_path() == ("Header",)

    for _ in range(3):
        _key(view, Qt.Key_Down)
    assert view.selected_path() == ("Header", "Model")

    # Walk to the very end: ref-only and main-only rows are rows too.
    for _ in range(20):
        _key(view, Qt.Key_Down)
    assert view.selected_path() == (
        "Parameterisation",
        "Cell",
        "Upper voltage cut-off [V]",
    )
    _key(view, Qt.Key_Down)  # bottom: stays, no wrap
    assert view.selected_path() == (
        "Parameterisation",
        "Cell",
        "Upper voltage cut-off [V]",
    )


def test_arrows_skip_folded_children_and_continuation_lines(qtbot):
    from PySide6.QtCore import Qt

    raw = {
        "Section": {
            "A": 1.0,
            "T": {"x": [1.0, 2.0], "y": [3.0, 4.0]},
            "B": 2.0,
        },
    }
    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(raw)
    view = page._view

    # The open table renders several lines; Down from its key line lands
    # on the next parameter, never inside the entries.
    view.reveal(("Section", "T"))
    _key(view, Qt.Key_Down)
    assert view.selected_path() == ("Section", "B")

    # A folded section's children are not visited.
    view.toggle_fold(("Section",))
    view.reveal(("Section",))
    _key(view, Qt.Key_Down)
    assert view.selected_path() == ("Section",)


def test_arrows_work_in_single_pane_mode(qtbot):
    from PySide6.QtCore import Qt

    page = SourcePage()
    qtbot.addWidget(page)
    page.refresh(_DOC, main_name="main.json", main_model="SPM")
    view = page._view

    _key(view, Qt.Key_Down)
    _key(view, Qt.Key_Down)
    assert view.selected_path() == ("Header", "BPX")


def test_double_click_jumps_to_the_parameter_in_the_editor(
    app_driver, tmp_path, monkeypatch
):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    app_driver.source_double_click(_CAPACITY)

    assert app_driver.current_view_name() == "Editor"
    assert app_driver.inspector_title() == "Nominal cell capacity [A.h]"


def test_double_click_works_without_a_reference(app_driver, tmp_path):
    app_driver.open(_write(tmp_path, "main.json", _DOC)).show_view("Source")

    app_driver.source_double_click(("Header", "Title"))

    assert app_driver.current_view_name() == "Editor"
    assert app_driver.inspector_title() == "Title"


def test_double_click_on_a_ref_only_row_stays_on_source(
    app_driver, tmp_path, monkeypatch
):
    app_driver.open(_write(tmp_path, "main.json", _DOC_MAIN_ONLY))
    _dock_reference(app_driver, tmp_path, monkeypatch, _REF)

    app_driver.source_double_click(_LOWER_CUTOFF)

    assert app_driver.current_view_name() == "Source"


def test_arrow_keys_reach_the_view_on_page_entry(app_driver, tmp_path):
    # `show_view` focuses the raw view, so Up/Down work without a click.
    app_driver.open(_write(tmp_path, "main.json", _DOC)).show_view("Source")

    app_driver.source_press_key("down")

    assert app_driver.source_selected_path() == ("Header",)
