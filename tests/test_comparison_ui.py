"""Editor UI half of the multi-file track's second milestone (M2): the
comparison strip, parameter-list row decoration + ghost rows, tree section
marks, and the Inspector's reference block / ghost card.

Core diff engine tests live in test_compare.py; this file covers only the
UI layer built on top of it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from PySide6.QtCore import Qt

import ui_qt.main_window as main_window_module
from core.compare import ComparisonResult, RowDiff, RowState, SectionDiff, compare
from core.tree_model import build_path_map, build_tree
from state.reference_snapshot import ReferenceSnapshot
from ui_qt import parameter_row, style, tree_model
from ui_qt.parameter_list import ParameterListPanel
from ui_qt.tree_model import BpxTreeModel

APP_DIR = Path(__file__).resolve().parents[1] / "app"
_ABOUT_ENERGY = APP_DIR / "data" / "example_documents" / "about_energy"

_CELL_PATH = ("Parameterisation", "Cell")

_MAIN_CELL = {
    "Reference temperature [K]": 298.15,
    "Nominal cell capacity [A.h]": 5.0,
    "Lower voltage cut-off [V]": None,
    "Density [kg.m-3]": 1000.0,
}
_REF_CELL = {
    "Reference temperature [K]": 298.15,
    "Nominal cell capacity [A.h]": 6.0,
    "Lower voltage cut-off [V]": 3.0,
    "Electrode area [m2]": 1.0,
}


def _document(cell: dict) -> dict:
    # Header is identical everywhere (files are told apart by filename, not
    # Title) so the intended Cell-only diffs are the *only* diffs -- a
    # differing Title would otherwise add its own DIFFERS row at Header.
    return {
        "Header": {"BPX": "0.1.0", "Title": "Test cell", "Model": "SPM"},
        "Parameterisation": {"Cell": dict(cell)},
    }


MAIN_RAW = _document(_MAIN_CELL)
REF_RAW = _document(_REF_CELL)
MATCHING_REF_RAW = _document(_MAIN_CELL)
MATCHING_MAIN_RAW = _document(_REF_CELL)


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


@pytest.fixture
def main_and_ref(tmp_path) -> tuple[Path, Path]:
    main_path = tmp_path / "main.json"
    main_path.write_text(json.dumps(MAIN_RAW), encoding="utf-8")
    ref_path = tmp_path / "reference.json"
    ref_path.write_text(json.dumps(REF_RAW), encoding="utf-8")
    return main_path, ref_path


def _dock_reference(app_driver, ref_path, monkeypatch) -> None:
    _stub_open_dialog(monkeypatch, ref_path)
    app_driver.click_workspace_open_reference()


# ---------------------------------------------------------------------------
# Panel-level unit tests (no MainWindow): strip counts, row tint, ghost rows,
# the merge rule, the "no comparison" baseline.
# ---------------------------------------------------------------------------


def _cell_node(raw: dict):
    return build_path_map(build_tree(raw))[_CELL_PATH]


def _reference_snapshot(raw: dict, filename: str = "reference.json", model: str = "SPM") -> ReferenceSnapshot:
    return ReferenceSnapshot(
        raw=raw,
        path=Path(filename),
        filename=filename,
        model=model,
        error_count=0,
        warning_count=0,
        section_count=0,
        parameter_count=0,
        mtime=0.0,
    )


@pytest.fixture
def panel(qtbot) -> ParameterListPanel:
    p = ParameterListPanel()
    qtbot.addWidget(p)
    qtbot.addWidget(p._popup)
    return p


def _ghost_items(panel):
    lst = panel._list
    return [
        lst.item(i) for i in range(lst.count()) if lst.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "ghost"
    ]


def _real_item(panel, label: str):
    lst = panel._list
    for i in range(lst.count()):
        item = lst.item(i)
        if item.data(256) is not None and item.text().startswith(label):
            return item
    raise AssertionError(f"No real row starting with {label!r}")


def test_no_comparison_renders_no_decoration_at_all(panel):
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")

    assert _ghost_items(panel) == []
    for label in ("Reference temperature", "Nominal cell capacity", "Density"):
        assert _real_item(panel, label).data(parameter_row.REF_BAR_ROLE) is None
    assert panel._strip.isHidden()


def test_row_bar_variant_per_row_state(panel):
    """DIFFERS and FILLABLE carry the solid "differs" bar, EQUAL the pale
    "equal" bar, MAIN_ONLY no bar at all: "same" and "not in the reference"
    are distinguishable at a glance."""
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(compare(MAIN_RAW, REF_RAW), _reference_snapshot(REF_RAW))

    assert _real_item(panel, "Nominal cell capacity").data(parameter_row.REF_BAR_ROLE) == "differs"
    assert _real_item(panel, "Lower voltage cut-off").data(parameter_row.REF_BAR_ROLE) == "differs"
    assert _real_item(panel, "Reference temperature").data(parameter_row.REF_BAR_ROLE) == "equal"
    assert _real_item(panel, "Density").data(parameter_row.REF_BAR_ROLE) is None


def test_differs_row_tooltip_carries_the_reference_value(panel):
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(compare(MAIN_RAW, REF_RAW), _reference_snapshot(REF_RAW))

    differs_tip = _real_item(panel, "Nominal cell capacity").toolTip()
    assert differs_tip.endswith("Reference: 6.0")
    assert differs_tip.startswith("5.0")  # main value line stays first
    # FILLABLE: no main value line, the reference line alone.
    assert _real_item(panel, "Lower voltage cut-off").toolTip() == "Reference: 3.0"
    # EQUAL: no reference line, the main value tooltip exactly as today.
    assert _real_item(panel, "Reference temperature").toolTip() == "298.15"


def test_ghost_row_rendered_read_only_and_selectable(panel):
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(compare(MAIN_RAW, REF_RAW), _reference_snapshot(REF_RAW))

    ghosts = _ghost_items(panel)
    assert len(ghosts) == 1
    ghost = ghosts[0]
    assert ghost.data(panel._GHOST_KEY_ROLE) == "Electrode area [m2]"
    assert ghost.data(256) is None  # not a real parameter row
    assert ghost.data(parameter_row.REF_BAR_ROLE) == "ref_only"
    assert ghost.data(parameter_row.VALUE_GHOST_ROLE) is True  # italic, even for a plain scalar
    html = ghost.data(parameter_row.HTML_ROLE)
    assert html.startswith("<i>") and html.endswith("</i>")  # ghosted end to end
    assert style.GHOST_TEXT in html

    # Selectable: clicking emits ghost_selected, never parameter_selected.
    received: list = []
    panel.ghost_selected.connect(lambda path, key: received.append((path, key)))
    panel.parameter_selected.connect(lambda path: received.append(("parameter_selected", path)))
    panel._list.setCurrentItem(ghost)
    panel._list.itemClicked.emit(ghost)
    assert received == [(_CELL_PATH, "Electrode area [m2]")]

    # Read-only everywhere: no context menu, no removal, no Enter-to-activate.
    pos = panel._list.visualItemRect(ghost).center()
    panel._on_context_menu_requested(pos)  # must not raise or open a menu
    panel._list.setCurrentItem(ghost)
    panel._remove_current_parameter()
    assert len(_ghost_items(panel)) == 1  # unchanged
    received.clear()
    panel._on_activate_current()  # Enter/Return on the current (ghost) row
    assert received == []


def test_merge_rule_ghost_key_excluded_from_fields_to_add(panel):
    node = _cell_node(MAIN_RAW)
    panel.set_comparison(compare(MAIN_RAW, REF_RAW), _reference_snapshot(REF_RAW))
    panel._expanded[node.path] = True
    panel.show_node(node, "SPM")

    aliases = [
        panel._list.item(i).data(panel._GROUP_ROW_ALIAS_ROLE)
        for i in range(panel._list.count())
        if panel._list.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
    ]
    assert "Electrode area [m2]" not in aliases  # ghost-covered: ghost row only
    assert "Upper voltage cut-off [V]" in aliases  # missing from both: still a suggestion


def test_merge_rule_with_no_reference_docked_matches_todays_behaviour(panel):
    node = _cell_node(MAIN_RAW)
    panel._expanded[node.path] = True
    panel.show_node(node, "SPM")

    aliases = [
        panel._list.item(i).data(panel._GROUP_ROW_ALIAS_ROLE)
        for i in range(panel._list.count())
        if panel._list.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
    ]
    assert "Electrode area [m2]" in aliases
    assert _ghost_items(panel) == []


def test_strip_counts_text_variations(panel):
    reference = _reference_snapshot(REF_RAW)

    panel.set_comparison(compare(MAIN_RAW, REF_RAW), reference)
    assert panel._strip._counts.text() == "2 differ · 1 ref only"

    one_differ = ComparisonResult(
        sections={
            _CELL_PATH: SectionDiff(
                path=_CELL_PATH,
                in_main=True,
                in_reference=True,
                rows={"A": RowDiff(RowState.DIFFERS, 1)},
            )
        }
    )
    panel.set_comparison(one_differ, reference)
    assert panel._strip._counts.text() == "1 differs"

    no_diff = ComparisonResult(sections={_CELL_PATH: SectionDiff(_CELL_PATH, True, True, {})})
    panel.set_comparison(no_diff, reference)
    assert panel._strip._counts.text() == "no differences"


def test_strip_invisible_with_no_reference_docked(panel):
    panel.set_comparison(None, None)
    assert panel._strip.isHidden()


# ---------------------------------------------------------------------------
# Tree section marks (gutter bar + differ count, BpxTreeModel unit level)
# ---------------------------------------------------------------------------


def _comparison_with_differ_count(path: tuple[str, ...], count: int) -> ComparisonResult:
    rows = {f"k{i}": RowDiff(RowState.DIFFERS, i) for i in range(count)}
    return ComparisonResult(sections={path: SectionDiff(path, True, True, rows)})


def _tree_with_cell():
    """A minimal tree: BPX File > Parameterisation > Cell, plus a sibling
    Header section -- enough to exercise both leaf and container nodes."""
    from core.tree_model import TreeNode

    cell = TreeNode(label="Cell", path=_CELL_PATH)
    parameterisation = TreeNode(label="Parameterisation", path=("Parameterisation",), children=[cell])
    header = TreeNode(label="Header", path=("Header",))
    root = TreeNode(label="BPX File", path=(), children=[header, parameterisation])
    return root, header, parameterisation, cell


def test_tree_display_text_carries_no_differ_suffix():
    """The old text-appended "≠ N" label suffix is gone -- the mark is now
    the gutter bar + REF_COUNT_ROLE, painted, not text."""
    root, _header, _parameterisation, cell = _tree_with_cell()
    model = BpxTreeModel(root, comparison=_comparison_with_differ_count(_CELL_PATH, 3))
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, Qt.DisplayRole) == "Cell"


def test_tree_ref_bar_and_count_for_differing_section():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root,
        is_expanded=lambda _index: True,
        comparison=_comparison_with_differ_count(_CELL_PATH, 3),
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "differs"
    assert model.data(cell_index, tree_model.REF_COUNT_ROLE) == 3


def test_tree_ref_bar_for_all_equal_section():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    equal_rows = {"k": RowDiff(RowState.EQUAL, 1)}
    comparison = ComparisonResult(sections={_CELL_PATH: SectionDiff(_CELL_PATH, True, True, equal_rows)})
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparison=comparison)
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "equal"
    assert model.data(cell_index, tree_model.REF_COUNT_ROLE) is None


def test_tree_ref_bar_absent_for_main_only_section():
    """A section entirely absent from the reference gets no bar -- it isn't
    "compared" in any meaningful sense, so it stays undecorated."""
    root, _header, _parameterisation, _cell = _tree_with_cell()
    main_only_rows = {"k": RowDiff(RowState.MAIN_ONLY)}
    comparison = ComparisonResult(
        sections={_CELL_PATH: SectionDiff(_CELL_PATH, in_main=True, in_reference=False, rows=main_only_rows)}
    )
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparison=comparison)
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) is None
    assert model.data(cell_index, tree_model.REF_COUNT_ROLE) is None


def test_tree_ref_bar_absent_for_pure_container_with_no_rows_of_its_own():
    """Parameterisation owns no leaf rows of its own (Cell does) -- a bar
    there would be meaningless noise, not a real comparison result."""
    root, _header, _parameterisation, _cell = _tree_with_cell()
    comparison = ComparisonResult(
        sections={
            ("Parameterisation",): SectionDiff(("Parameterisation",), True, True, {}),
            _CELL_PATH: SectionDiff(_CELL_PATH, True, True, {"k": RowDiff(RowState.DIFFERS, 1)}),
        }
    )
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparison=comparison)
    parameterisation_index = model.index(1, 0)

    assert model.data(parameterisation_index, parameter_row.REF_BAR_ROLE) is None
    assert model.data(parameterisation_index, tree_model.REF_COUNT_ROLE) is None


def test_tree_collapsed_parent_rolls_up_differing_descendant():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    comparison = ComparisonResult(
        sections={
            ("Parameterisation",): SectionDiff(("Parameterisation",), True, True, {}),
            _CELL_PATH: SectionDiff(_CELL_PATH, True, True, {"k": RowDiff(RowState.DIFFERS, 1)}),
        }
    )
    model = BpxTreeModel(root, is_expanded=lambda _index: False, comparison=comparison)
    parameterisation_index = model.index(1, 0)

    assert model.data(parameterisation_index, parameter_row.REF_BAR_ROLE) == "differs"
    assert model.data(parameterisation_index, tree_model.REF_COUNT_ROLE) == 1


def test_tree_expanded_parent_shows_no_bar_for_its_own_empty_section():
    """Expanded rows read own-state only -- Cell's differing rows do not
    leak up onto the expanded Parameterisation row (the collapsed-only
    rollup test above covers the opposite state)."""
    root, _header, _parameterisation, _cell = _tree_with_cell()
    comparison = ComparisonResult(
        sections={
            ("Parameterisation",): SectionDiff(("Parameterisation",), True, True, {}),
            _CELL_PATH: SectionDiff(_CELL_PATH, True, True, {"k": RowDiff(RowState.DIFFERS, 1)}),
        }
    )
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparison=comparison)
    parameterisation_index = model.index(1, 0)

    assert model.data(parameterisation_index, parameter_row.REF_BAR_ROLE) is None
    assert model.data(parameterisation_index, tree_model.REF_COUNT_ROLE) is None


def test_tree_ref_bar_and_count_absent_with_no_comparison_docked():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(root)
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) is None
    assert model.data(cell_index, tree_model.REF_COUNT_ROLE) is None


def test_tree_ref_bar_updates_live_and_clears():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root, is_expanded=lambda _index: True, comparison=_comparison_with_differ_count(_CELL_PATH, 2)
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "differs"
    model.set_comparison(None)
    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) is None


# ---------------------------------------------------------------------------
# Full-app tests (AppDriver / MainWindow)
# ---------------------------------------------------------------------------


def test_strip_appears_with_correct_counts_after_docking(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    assert not app_driver.comparison_strip_visible()

    _dock_reference(app_driver, ref_path, monkeypatch)

    assert app_driver.comparison_strip_visible()
    assert app_driver.comparison_strip_identity_text() == f"Reference · {ref_path.name} · SPM"
    assert app_driver.comparison_strip_counts_text() == "2 differ · 1 ref only"


def test_row_bar_end_to_end(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))

    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "differs"
    assert app_driver.parameter_row_ref_bar("Lower voltage cut-off") == "differs"
    assert app_driver.parameter_row_ref_bar("Reference temperature") == "equal"
    assert app_driver.parameter_row_ref_bar("Density") is None


def test_row_bar_actually_renders_real_pixels(app_driver, main_and_ref, monkeypatch):
    """Pixel-level pin (not just the REF_BAR_ROLE data): the DIFFERS row's
    left-edge bar must genuinely paint reference purple, the EQUAL row's the
    pale lilac, and both rows' backgrounds must stay plain white -- see
    ``test_parameter_row.py``'s dedicated regression test for why a
    data-only check is not enough here."""
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))

    lst = app_driver._w._params._list
    labels = [lst.item(i).text() for i in range(lst.count())]
    differs_index = next(i for i, t in enumerate(labels) if t.startswith("Nominal cell capacity"))
    equal_index = next(i for i, t in enumerate(labels) if t.startswith("Reference temperature"))

    # dx=1 hits the 3px bar's interior at mid-row height; dx=6 sits between
    # the bar (3px) and the text padding (8px), i.e. the row background.
    assert app_driver.parameter_list_row_painted_colour(differs_index, dx=1, dy=12) == style.REFERENCE
    assert app_driver.parameter_list_row_painted_colour(equal_index, dx=1, dy=12) == style.REFERENCE_BORDER
    assert app_driver.parameter_list_row_painted_colour(differs_index, dx=6, dy=12) == "#ffffff"
    assert app_driver.parameter_list_row_painted_colour(equal_index, dx=6, dy=12) == "#ffffff"


def test_tree_bar_actually_renders_real_pixels(app_driver, main_and_ref, monkeypatch, tmp_path):
    """Pixel-level pin for the tree's own gutter bar (not just the
    REF_BAR_ROLE data), mirroring the parameter list's own pin above: the
    differing Cell section's left-edge rail paints reference purple; once a
    fully-matching reference is docked the same rail turns pale lilac."""
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    assert app_driver.tree_row_painted_colour(_CELL_PATH, dx=1, dy=12) == style.REFERENCE

    matching_ref_path = tmp_path / "matches_main.json"
    matching_ref_path.write_text(json.dumps(MATCHING_REF_RAW), encoding="utf-8")
    _dock_reference(app_driver, matching_ref_path, monkeypatch)

    assert app_driver.tree_row_painted_colour(_CELL_PATH, dx=1, dy=12) == style.REFERENCE_BORDER


def test_tree_differ_count_actually_paints(app_driver, main_and_ref, monkeypatch):
    """The right-aligned differ count must genuinely paint pixels, not just
    carry REF_COUNT_ROLE data -- the numeric successor to the old
    text-appended "≠ N" label suffix."""
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    assert app_driver.tree_node_ref_count(_CELL_PATH) == 2
    assert app_driver.tree_row_right_band_shows_reference_colour(_CELL_PATH)


def test_merge_rule_end_to_end_both_ways(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.toggle_fields_to_add_group()

    aliases = app_driver.fields_to_add_suggestion_aliases()
    assert "Electrode area [m2]" not in aliases
    assert "Upper voltage cut-off [V]" in aliases
    assert "Electrode area [m2]" in app_driver.ghost_row_keys()


def test_no_reference_docked_fields_to_add_exactly_as_today(app_driver, main_and_ref):
    main_path, _ = main_and_ref
    app_driver.open(main_path)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.toggle_fields_to_add_group()

    assert "Electrode area [m2]" in app_driver.fields_to_add_suggestion_aliases()
    assert app_driver.ghost_row_keys() == []


def test_tree_ref_bar_switches_from_differs_to_equal_when_reference_matches(
    app_driver, main_and_ref, monkeypatch, tmp_path
):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    assert app_driver.tree_node_ref_bar(_CELL_PATH) == "differs"
    assert app_driver.tree_node_ref_count(_CELL_PATH) == 2

    matching_ref_path = tmp_path / "matches_main.json"
    matching_ref_path.write_text(json.dumps(MATCHING_REF_RAW), encoding="utf-8")
    _dock_reference(app_driver, matching_ref_path, monkeypatch)

    assert app_driver.tree_node_ref_bar(_CELL_PATH) == "equal"
    assert app_driver.tree_node_ref_count(_CELL_PATH) is None


def test_reference_block_shows_differing_value(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    assert app_driver.reference_block_visible()
    assert app_driver.main_file_heading_visible()
    assert app_driver.main_file_heading_text() == "Main file"
    assert app_driver.reference_file_heading_text() == "Reference file"
    assert app_driver.reference_value_text() == "6.0"
    assert app_driver.reference_unit_text() == "A.h"
    assert not app_driver.reference_block_is_same()
    assert app_driver.copy_up_visible()
    assert app_driver.copy_up_enabled()


def test_reference_block_faint_and_copy_up_disabled_for_equal_value(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Reference temperature [K]"))

    assert app_driver.reference_block_visible()
    assert app_driver.reference_value_text() == "298.15 · same"
    assert app_driver.reference_block_is_same()
    assert not app_driver.copy_up_enabled()


def test_reference_block_copy_up_enabled_for_fillable_value(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Lower voltage cut-off [V]"))

    assert app_driver.reference_block_visible()
    assert not app_driver.reference_block_is_same()
    assert app_driver.copy_up_enabled()


def test_reference_block_absent_for_main_only_parameter(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Density [kg.m-3]"))

    assert not app_driver.reference_block_visible()
    assert not app_driver.main_file_heading_visible()


def test_no_reference_docked_shows_no_main_file_heading(app_driver, main_and_ref):
    main_path, _ = main_and_ref
    app_driver.open(main_path)

    app_driver.go_to(("Parameterisation", "Cell", "Density [kg.m-3]"))

    assert not app_driver.main_file_heading_visible()
    assert not app_driver.reference_block_visible()


def test_clicking_copy_up_emits_signal_and_does_not_dirty_the_card(app_driver, main_and_ref, monkeypatch):
    """Multi-file track M3: Copy up is now wired (see the "Copy up" section
    below for full coverage) -- this pins the signal itself still fires and
    the card the pull rebuilds is never left holding a draft."""
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    received: list = []
    app_driver._w._inspector._card.copy_up_requested.connect(lambda: received.append(True))

    app_driver.click_copy_up()

    assert received == [True]
    assert not app_driver.card_is_dirty()
    assert app_driver.field_value() == 6.0  # the reference value, now pulled in


def test_docking_reference_then_selecting_differing_parameter_leaves_card_untouched(
    app_driver, main_and_ref, monkeypatch
):
    """The _touched regression pin (known Qt pitfall): populating the
    reference block must never mark the card touched, so a bare Enter after
    selection does not commit."""
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.reference_block_visible()
    assert not app_driver.card_is_dirty()

    app_driver.commit()  # bare Enter, no edit

    assert app_driver.field_value() == 5.0  # unchanged: no spurious commit


def test_ghost_row_selection_shows_ghost_card_with_no_input_widget(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))

    app_driver.select_ghost_row("Electrode area [m2]")

    assert app_driver.ghost_card_shown()
    assert app_driver.ghost_card_heading_text() == "Not in the main file"
    assert "Electrode area" in app_driver.ghost_card_title_text()
    assert not app_driver.ghost_card_has_input_widget()
    assert app_driver.reference_file_heading_text() == "Reference file"
    assert app_driver.reference_value_text() == "1.0"
    assert app_driver.reference_unit_text() == "m2"
    assert app_driver.copy_up_visible()
    assert app_driver.copy_up_enabled()

    app_driver.press_delete_in_parameter_list()
    assert "Electrode area [m2]" in app_driver.ghost_row_keys()


def test_ghost_card_copy_up_emits_signal(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.select_ghost_row("Electrode area [m2]")

    received: list = []
    app_driver._w._inspector._card.copy_up_requested.connect(lambda: received.append(True))

    app_driver.click_copy_up()

    assert received == [True]


def test_removing_reference_clears_everything_immediately(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.reference_block_visible()
    assert app_driver.comparison_strip_visible()

    app_driver.click_reference_remove()

    assert not app_driver.comparison_strip_visible()
    assert app_driver.ghost_row_keys() == []
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") is None
    assert not app_driver.reference_block_visible()
    assert app_driver.tree_node_ref_bar(_CELL_PATH) is None
    assert app_driver.tree_node_ref_count(_CELL_PATH) is None


def test_replacing_the_main_document_with_reference_docked_refreshes(
    app_driver, main_and_ref, monkeypatch, tmp_path
):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    assert app_driver.comparison_strip_counts_text() == "2 differ · 1 ref only"

    matching_main_path = tmp_path / "matches_reference.json"
    matching_main_path.write_text(json.dumps(MATCHING_MAIN_RAW), encoding="utf-8")
    monkeypatch.setattr(
        app_driver._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    _stub_open_dialog(monkeypatch, matching_main_path)
    app_driver.click_workspace_open()

    assert app_driver.comparison_strip_counts_text() == "no differences"
    app_driver.go_to(("Parameterisation", "Cell"))
    assert app_driver.ghost_row_keys() == []


def test_no_reference_docked_is_structurally_todays_editor(app_driver, main_and_ref):
    main_path, _ = main_and_ref
    app_driver.open(main_path)
    app_driver.go_to(("Parameterisation", "Cell"))

    assert not app_driver.comparison_strip_visible()
    assert app_driver.ghost_row_keys() == []
    for label in ("Reference temperature", "Nominal cell capacity", "Lower voltage cut-off", "Density"):
        assert app_driver.parameter_row_ref_bar(label) is None
    assert app_driver.tree_node_ref_bar(_CELL_PATH) is None
    assert app_driver.tree_node_ref_count(_CELL_PATH) is None

    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert not app_driver.reference_block_visible()



# ---------------------------------------------------------------------------
# "Copy up" (multi-file track M3): PullParameter/PullSection wired to the
# comparison cards' Copy up buttons. Core command behaviour (ancestor
# creation, one undo entry, deepcopy) is covered in test_command_service.py;
# this file covers only the end-to-end UI wiring.
# ---------------------------------------------------------------------------


def test_copy_up_on_differs_row_pulls_value_retints_and_disables(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "differs"

    app_driver.click_copy_up()

    assert app_driver.field_value() == 6.0
    assert app_driver.reference_block_is_same()
    assert not app_driver.copy_up_enabled()
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "equal"

    app_driver.undo()

    assert app_driver.field_value() == 5.0
    assert not app_driver.reference_block_is_same()
    assert app_driver.copy_up_enabled()
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "differs"


def test_copy_up_on_fillable_row_pulls_the_reference_value(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Lower voltage cut-off [V]"))
    assert app_driver.copy_up_enabled()

    app_driver.click_copy_up()

    assert app_driver.field_value() == 3.0
    assert app_driver.reference_block_is_same()


def test_ghost_row_copy_up_adds_and_selects_the_real_parameter(app_driver, main_and_ref, monkeypatch):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.select_ghost_row("Electrode area [m2]")
    assert app_driver.ghost_card_shown()

    app_driver.click_copy_up()

    assert not app_driver.ghost_card_shown()
    assert app_driver.shown_parameter_path() == ("Parameterisation", "Cell", "Electrode area [m2]")
    assert app_driver.field_value() == 1.0
    assert "Electrode area [m2]" not in app_driver.ghost_row_keys()


def test_copy_up_supersedes_a_dirty_draft_and_undo_restores_the_prior_value(
    app_driver, main_and_ref, monkeypatch
):
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    app_driver.edit_field(7.0)
    assert app_driver.card_is_dirty()

    app_driver.click_copy_up()

    assert app_driver.field_value() == 6.0  # the reference value, not the discarded draft
    assert not app_driver.card_is_dirty()

    app_driver.undo()

    assert app_driver.field_value() == 5.0  # one undo restores the prior committed value
    assert not app_driver.card_is_dirty()


def test_bare_enter_after_a_pull_commits_nothing(app_driver, main_and_ref, monkeypatch):
    """The _touched pin (known Qt pitfall): the card the pull's own refresh
    rebuilds must not read as dirty, so a bare Enter afterwards is a no-op --
    a single undo still reverts the pull alone, not a phantom second commit."""
    main_path, ref_path = main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    app_driver.click_copy_up()
    assert app_driver.field_value() == 6.0
    assert not app_driver.card_is_dirty()

    app_driver.commit()  # bare Enter, no edit

    assert app_driver.field_value() == 6.0  # unchanged: no spurious commit

    app_driver.undo()

    assert app_driver.field_value() == 5.0  # the pull was the only thing to revert


_SHAPE_MAIN = {
    "Header": {"BPX": "0.1.0", "Title": "Shape cell", "Model": "SPM", "Custom Note": 5.0},
    "Parameterisation": {"Cell": {}},
}
_SHAPE_REF = {
    "Header": {
        "BPX": "0.1.0",
        "Title": "Shape cell",
        "Model": "SPM",
        "Custom Note": {"x": [0, 1], "y": [2, 3]},
    },
    "Parameterisation": {"Cell": {}},
}


@pytest.fixture
def shape_change_main_and_ref(tmp_path) -> tuple[Path, Path]:
    main_path = tmp_path / "shape_main.json"
    main_path.write_text(json.dumps(_SHAPE_MAIN), encoding="utf-8")
    ref_path = tmp_path / "shape_reference.json"
    ref_path.write_text(json.dumps(_SHAPE_REF), encoding="utf-8")
    return main_path, ref_path


def test_copy_up_shape_change_scalar_to_table_reclassifies_the_card(
    app_driver, shape_change_main_and_ref, monkeypatch
):
    """"Custom Note" carries no schema metadata (an undeclared alias), so its
    kind follows the stored value's shape -- a same-key pull that changes
    shape is copied verbatim, and the card re-classifies to match."""
    main_path, ref_path = shape_change_main_and_ref
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Header", "Custom Note"))
    assert type(app_driver._w._inspector._card._editor).__name__ == "ScalarCard"

    app_driver.click_copy_up()

    assert app_driver.field_value() == {"x": [0, 1], "y": [2, 3]}
    assert type(app_driver._w._inspector._card._editor).__name__ == "TableCard"


def test_end_to_end_with_bundled_about_energy_examples(app_driver, monkeypatch):
    """Real files, not fixtures, for realism (per the M2 brief) -- the LFP
    file's legacy-shape conversion is expected structural noise, not pinned
    here; only that the comparison is visibly non-trivial."""
    main_path = _ABOUT_ENERGY / "nmc_pouch_cell.json"
    ref_path = _ABOUT_ENERGY / "lfp_18650_cell.json"
    app_driver.open(main_path)
    _dock_reference(app_driver, ref_path, monkeypatch)

    assert app_driver.comparison_strip_visible()
    assert app_driver.comparison_strip_identity_text().startswith(f"Reference · {ref_path.name}")
    assert app_driver.comparison_strip_counts_text() != "no differences"
