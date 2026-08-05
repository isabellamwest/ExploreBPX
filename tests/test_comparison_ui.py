"""Editor UI for the multi-reference comparison (Phase 1): the identity-chip
comparison strip, parameter-list row decoration + ghost rows, tree section
marks (differs-from-any), and the Inspector's Card Ledger / ghost card.

Core diff engine and grouping tests live in test_compare.py; badge-identity
purity in test_reference_identity.py; this file covers only the UI layer
built on top of them.
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
from ui_qt import parameter_row, style
from ui_qt.parameter_list import ParameterListPanel
from ui_qt.reference_identity import build_pins
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
#: First pinned reference ("alpha"): equal RT, differing NCC, fillable LVC,
#: ref-only Electrode area 1.0.
_ALPHA_CELL = {
    "Reference temperature [K]": 298.15,
    "Nominal cell capacity [A.h]": 6.0,
    "Lower voltage cut-off [V]": 3.0,
    "Electrode area [m2]": 1.0,
}
#: Second pinned reference ("bravo"): differing RT, NCC *identical to
#: alpha's* (the grouping case), no LVC, ref-only Electrode area 2.0 (a
#: second distinct ghost value).
_BRAVO_CELL = {
    "Reference temperature [K]": 300.0,
    "Nominal cell capacity [A.h]": 6.0,
    "Electrode area [m2]": 2.0,
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
ALPHA_RAW = _document(_ALPHA_CELL)
BRAVO_RAW = _document(_BRAVO_CELL)
MATCHING_REF_RAW = _document(_MAIN_CELL)
MATCHING_MAIN_RAW = _document(_ALPHA_CELL)


def _stub_open_dialog(monkeypatch, path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )


@pytest.fixture
def main_and_refs(tmp_path) -> tuple[Path, Path, Path]:
    """The main document plus two pinnable references, "alpha" (first pin)
    and "bravo" (second) -- names chosen so badge letters read Al/Br."""
    main_path = tmp_path / "main.json"
    main_path.write_text(json.dumps(MAIN_RAW), encoding="utf-8")
    alpha_path = tmp_path / "alpha.json"
    alpha_path.write_text(json.dumps(ALPHA_RAW), encoding="utf-8")
    bravo_path = tmp_path / "bravo.json"
    bravo_path.write_text(json.dumps(BRAVO_RAW), encoding="utf-8")
    return main_path, alpha_path, bravo_path


def _pin_reference(app_driver, ref_path, monkeypatch) -> None:
    _stub_open_dialog(monkeypatch, ref_path)
    app_driver.click_workspace_open_reference()


# ---------------------------------------------------------------------------
# Panel-level unit tests (no MainWindow): strip chips, row bars, ghost rows,
# the merge rule, the "no comparison" baseline.
# ---------------------------------------------------------------------------


def _cell_node(raw: dict):
    return build_path_map(build_tree(raw))[_CELL_PATH]


def _reference_snapshot(raw: dict, filename: str = "alpha.json", model: str = "SPM") -> ReferenceSnapshot:
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


def _pins_for(main_raw: dict, *refs: tuple[dict, str]):
    """ReferencePins for *refs* ((raw, filename) each) against *main_raw*
    -- the same ``build_pins`` derivation MainWindow itself runs."""
    snapshots = [_reference_snapshot(raw, filename) for raw, filename in refs]
    comparisons = [compare(main_raw, snapshot.raw) for snapshot in snapshots]
    return build_pins(snapshots, comparisons)


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


def test_row_bar_variant_per_row_state_single_reference(panel):
    """DIFFERS and FILLABLE carry the solid "differs" bar, EQUAL the pale
    "equal" bar, MAIN_ONLY no bar at all: "same" and "not in the reference"
    are distinguishable at a glance."""
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(_pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json")))

    assert _real_item(panel, "Nominal cell capacity").data(parameter_row.REF_BAR_ROLE) == "differs"
    assert _real_item(panel, "Lower voltage cut-off").data(parameter_row.REF_BAR_ROLE) == "differs"
    assert _real_item(panel, "Reference temperature").data(parameter_row.REF_BAR_ROLE) == "equal"
    assert _real_item(panel, "Density").data(parameter_row.REF_BAR_ROLE) is None


def test_row_bar_lights_when_any_pinned_reference_differs(panel):
    """Design rule 6's row-level twin: alpha matches RT but bravo differs
    there, so the row's bar is the solid "differs" -- one disagreeing pin
    is enough."""
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(
        _pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json"), (BRAVO_RAW, "bravo.json"))
    )

    assert _real_item(panel, "Reference temperature").data(parameter_row.REF_BAR_ROLE) == "differs"
    # LVC exists only in alpha (fillable there, absent from bravo): differs.
    assert _real_item(panel, "Lower voltage cut-off").data(parameter_row.REF_BAR_ROLE) == "differs"
    # In no pin at all: still bare.
    assert _real_item(panel, "Density").data(parameter_row.REF_BAR_ROLE) is None


def test_differs_row_tooltip_names_each_differing_pin(panel):
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(
        _pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json"), (BRAVO_RAW, "bravo.json"))
    )

    differs_tip = _real_item(panel, "Nominal cell capacity").toolTip()
    assert differs_tip.startswith("5.0")  # main value line stays first
    assert "alpha: 6.0" in differs_tip
    assert "bravo: 6.0" in differs_tip
    # RT: only bravo's line appears -- alpha matches and is not "from what".
    rt_tip = _real_item(panel, "Reference temperature").toolTip()
    assert "bravo: 300.0" in rt_tip
    assert "alpha" not in rt_tip


def test_ghost_row_rendered_read_only_and_selectable(panel):
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(_pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json")))

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


def test_ghost_rows_union_across_pins_one_row_per_key(panel):
    """A key REF_ONLY in both pins still renders exactly one ghost row,
    previewing the first-pinned holder's value."""
    node = _cell_node(MAIN_RAW)
    panel.show_node(node, "SPM")
    panel.set_comparison(
        _pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json"), (BRAVO_RAW, "bravo.json"))
    )

    ghosts = _ghost_items(panel)
    assert [g.data(panel._GHOST_KEY_ROLE) for g in ghosts] == ["Electrode area [m2]"]
    assert ghosts[0].data(parameter_row.VALUE_ROLE) == "1.0"  # alpha's, first pinned


def test_merge_rule_ghost_key_excluded_from_fields_to_add(panel):
    node = _cell_node(MAIN_RAW)
    panel.set_comparison(
        _pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json"), (BRAVO_RAW, "bravo.json"))
    )
    panel._expanded[node.path] = True
    panel.show_node(node, "SPM")

    aliases = [
        panel._list.item(i).data(panel._GROUP_ROW_ALIAS_ROLE)
        for i in range(panel._list.count())
        if panel._list.item(i).data(panel._GROUP_ROW_KIND_ROLE) == "suggestion"
    ]
    assert "Electrode area [m2]" not in aliases  # ghost-covered: ghost row only
    assert "Upper voltage cut-off [V]" in aliases  # missing from all: still a suggestion


def test_merge_rule_with_no_reference_pinned_matches_todays_behaviour(panel):
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


def test_strip_shows_one_chip_per_pin_with_counts_in_the_tooltip(panel):
    """Design rule 2: the strip is fully quiet -- identity chips only, in
    pin order; each pin's own whole-file counts live in its tooltip."""
    panel.set_comparison(
        _pins_for(MAIN_RAW, (ALPHA_RAW, "alpha.json"), (BRAVO_RAW, "bravo.json"))
    )

    strip = panel._strip
    assert not strip.isHidden()
    assert [chip._name.text() for chip in strip._chips] == ["alpha", "bravo"]
    assert [chip.toolTip() for chip in strip._chips] == [
        "alpha · SPM · 2 differ · 1 ref only",
        "bravo · SPM · 2 differ · 1 ref only",
    ]


def test_strip_chip_tooltip_count_variations(panel):
    reference = _reference_snapshot(ALPHA_RAW)

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
    panel.set_comparison(build_pins([reference], [one_differ]))
    assert panel._strip._chips[0].toolTip() == "alpha · SPM · 1 differs"

    no_diff = ComparisonResult(sections={_CELL_PATH: SectionDiff(_CELL_PATH, True, True, {})})
    panel.set_comparison(build_pins([reference], [no_diff]))
    assert panel._strip._chips[0].toolTip() == "alpha · SPM · no differences"


def test_strip_invisible_with_no_reference_pinned(panel):
    panel.set_comparison([])
    assert panel._strip.isHidden()


# ---------------------------------------------------------------------------
# Tree section marks (gutter bar, BpxTreeModel unit level)
# ---------------------------------------------------------------------------


def _comparison_with_differ_count(path: tuple[str, ...], count: int) -> ComparisonResult:
    rows = {f"k{i}": RowDiff(RowState.DIFFERS, i) for i in range(count)}
    return ComparisonResult(sections={path: SectionDiff(path, True, True, rows)})


def _equal_comparison(path: tuple[str, ...]) -> ComparisonResult:
    rows = {"k": RowDiff(RowState.EQUAL, 1)}
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
    """The old text-appended "≠ N" label suffix is gone -- the mark is the
    painted gutter bar alone (the differ count died with Phase 1: a single
    number is meaningless against N references)."""
    root, _header, _parameterisation, cell = _tree_with_cell()
    model = BpxTreeModel(root, comparisons=[_comparison_with_differ_count(_CELL_PATH, 3)])
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, Qt.DisplayRole) == "Cell"


def test_tree_ref_bar_for_differing_section():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root,
        is_expanded=lambda _index: True,
        comparisons=[_comparison_with_differ_count(_CELL_PATH, 3)],
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "differs"


def test_tree_ref_bar_for_all_equal_section():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root, is_expanded=lambda _index: True, comparisons=[_equal_comparison(_CELL_PATH)]
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "equal"


def test_tree_ref_bar_differs_when_any_pinned_reference_disagrees():
    """Design rule 6: one all-equal comparison plus one differing one --
    the bar is "differs", because at least one pin disagrees within."""
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root,
        is_expanded=lambda _index: True,
        comparisons=[_equal_comparison(_CELL_PATH), _comparison_with_differ_count(_CELL_PATH, 1)],
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "differs"


def test_tree_ref_bar_equal_when_every_pin_matches():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root,
        is_expanded=lambda _index: True,
        comparisons=[_equal_comparison(_CELL_PATH), _equal_comparison(_CELL_PATH)],
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "equal"


def test_tree_ref_bar_absent_for_main_only_section():
    """A section entirely absent from every reference gets no bar -- it
    isn't "compared" in any meaningful sense, so it stays undecorated."""
    root, _header, _parameterisation, _cell = _tree_with_cell()
    main_only_rows = {"k": RowDiff(RowState.MAIN_ONLY)}
    comparison = ComparisonResult(
        sections={_CELL_PATH: SectionDiff(_CELL_PATH, in_main=True, in_reference=False, rows=main_only_rows)}
    )
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparisons=[comparison])
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) is None


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
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparisons=[comparison])
    parameterisation_index = model.index(1, 0)

    assert model.data(parameterisation_index, parameter_row.REF_BAR_ROLE) is None


def test_tree_collapsed_parent_rolls_up_differing_descendant():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    comparison = ComparisonResult(
        sections={
            ("Parameterisation",): SectionDiff(("Parameterisation",), True, True, {}),
            _CELL_PATH: SectionDiff(_CELL_PATH, True, True, {"k": RowDiff(RowState.DIFFERS, 1)}),
        }
    )
    model = BpxTreeModel(root, is_expanded=lambda _index: False, comparisons=[comparison])
    parameterisation_index = model.index(1, 0)

    assert model.data(parameterisation_index, parameter_row.REF_BAR_ROLE) == "differs"


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
    model = BpxTreeModel(root, is_expanded=lambda _index: True, comparisons=[comparison])
    parameterisation_index = model.index(1, 0)

    assert model.data(parameterisation_index, parameter_row.REF_BAR_ROLE) is None


def test_tree_ref_bar_absent_with_no_comparison_docked():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(root)
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) is None


def test_tree_ref_bar_updates_live_and_clears():
    root, _header, _parameterisation, _cell = _tree_with_cell()
    model = BpxTreeModel(
        root, is_expanded=lambda _index: True, comparisons=[_comparison_with_differ_count(_CELL_PATH, 2)]
    )
    cell_index = model.index(0, 0, model.index(1, 0))

    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) == "differs"
    model.set_comparison([])
    assert model.data(cell_index, parameter_row.REF_BAR_ROLE) is None


# ---------------------------------------------------------------------------
# Full-app tests (AppDriver / MainWindow)
# ---------------------------------------------------------------------------


def test_strip_appears_with_identity_chips_after_pinning(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    assert not app_driver.comparison_strip_visible()

    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)

    assert app_driver.comparison_strip_visible()
    assert app_driver.comparison_strip_chip_names() == ["alpha", "bravo"]
    assert app_driver.comparison_strip_chip_tooltips() == [
        "alpha · SPM · 2 differ · 1 ref only",
        "bravo · SPM · 2 differ · 1 ref only",
    ]


def test_row_bar_end_to_end(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))

    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "differs"
    assert app_driver.parameter_row_ref_bar("Lower voltage cut-off") == "differs"
    assert app_driver.parameter_row_ref_bar("Reference temperature") == "equal"
    assert app_driver.parameter_row_ref_bar("Density") is None

    # Pinning bravo flips RT to differs: one disagreeing pin is enough.
    _pin_reference(app_driver, bravo_path, monkeypatch)
    assert app_driver.parameter_row_ref_bar("Reference temperature") == "differs"


def test_row_bar_actually_renders_real_pixels(app_driver, main_and_refs, monkeypatch):
    """Pixel-level pin (not just the REF_BAR_ROLE data): the DIFFERS row's
    left-edge bar must genuinely paint reference purple, the EQUAL row's the
    pale lilac, and both rows' backgrounds must stay plain white -- see
    ``test_parameter_row.py``'s dedicated regression test for why a
    data-only check is not enough here."""
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
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


def test_tree_bar_actually_renders_real_pixels(app_driver, main_and_refs, monkeypatch, tmp_path):
    """Pixel-level pin for the tree's own gutter bar (not just the
    REF_BAR_ROLE data), mirroring the parameter list's own pin above: the
    differing Cell section's left-edge rail paints reference purple; with
    only a fully-matching reference pinned the same rail turns pale lilac.
    The old right-aligned differ count must NOT paint any more."""
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)

    assert app_driver.tree_row_painted_colour(_CELL_PATH, dx=1, dy=12) == style.REFERENCE
    assert not app_driver.tree_row_right_band_shows_reference_colour(_CELL_PATH)

    app_driver.click_reference_remove(0)
    matching_ref_path = tmp_path / "matches_main.json"
    matching_ref_path.write_text(json.dumps(MATCHING_REF_RAW), encoding="utf-8")
    _pin_reference(app_driver, matching_ref_path, monkeypatch)

    assert app_driver.tree_row_painted_colour(_CELL_PATH, dx=1, dy=12) == style.REFERENCE_BORDER


def test_merge_rule_end_to_end_both_ways(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.toggle_fields_to_add_group()

    aliases = app_driver.fields_to_add_suggestion_aliases()
    assert "Electrode area [m2]" not in aliases
    assert "Upper voltage cut-off [V]" in aliases
    assert app_driver.ghost_row_keys() == ["Electrode area [m2]"]  # one row, unioned


def test_no_reference_pinned_fields_to_add_exactly_as_today(app_driver, main_and_refs):
    main_path, _alpha, _bravo = main_and_refs
    app_driver.open(main_path)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.toggle_fields_to_add_group()

    assert "Electrode area [m2]" in app_driver.fields_to_add_suggestion_aliases()
    assert app_driver.ghost_row_keys() == []


def test_tree_ref_bar_switches_from_differs_to_equal_when_reference_matches(
    app_driver, main_and_refs, monkeypatch, tmp_path
):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)

    assert app_driver.tree_node_ref_bar(_CELL_PATH) == "differs"

    app_driver.click_reference_remove(0)
    matching_ref_path = tmp_path / "matches_main.json"
    matching_ref_path.write_text(json.dumps(MATCHING_REF_RAW), encoding="utf-8")
    _pin_reference(app_driver, matching_ref_path, monkeypatch)

    assert app_driver.tree_node_ref_bar(_CELL_PATH) == "equal"


# ---------------------------------------------------------------------------
# Card Ledger (design rule 3): one row per distinct reference value, stacked
# badges, "same"/Pull, and the source-named pull commands.
# ---------------------------------------------------------------------------


def test_ledger_groups_identical_values_into_one_row(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    assert app_driver.ledger_visible()
    assert app_driver.main_file_heading_visible()
    assert app_driver.main_file_heading_text() == "Main"
    # Both pins hold 6.0: one row, a stacked badge cluster, one Pull.
    assert app_driver.ledger_row_count() == 1
    assert app_driver.ledger_row_badges(0) == ["Al", "Br"]
    assert app_driver.ledger_row_value_text(0) == "6.0"
    assert app_driver.ledger_row_unit_text(0) == "A.h"
    assert not app_driver.ledger_row_is_same(0)


def test_ledger_splits_same_and_differs_rows(app_driver, main_and_refs, monkeypatch):
    """RT: alpha equals main (muted "same", no Pull), bravo differs (its
    own row with Pull) -- rows in first-pinned order."""
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Reference temperature [K]"))

    assert app_driver.ledger_row_count() == 2
    assert app_driver.ledger_row_badges(0) == ["Al"]
    assert app_driver.ledger_row_is_same(0)
    assert app_driver.ledger_row_badges(1) == ["Br"]
    assert not app_driver.ledger_row_is_same(1)
    assert app_driver.ledger_row_value_text(1) == "300.0"


def test_ledger_absent_key_means_no_row(app_driver, main_and_refs, monkeypatch):
    """LVC exists only in alpha: one row, alpha's badge alone -- bravo
    contributes nothing (MAIN_ONLY = no row, design rule 3)."""
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Lower voltage cut-off [V]"))

    assert app_driver.ledger_row_count() == 1
    assert app_driver.ledger_row_badges(0) == ["Al"]
    assert not app_driver.ledger_row_is_same(0)


def test_ledger_hidden_when_no_pin_has_the_key(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Density [kg.m-3]"))

    assert not app_driver.ledger_visible()
    assert not app_driver.main_file_heading_visible()


def test_no_reference_pinned_shows_no_ledger_or_heading(app_driver, main_and_refs):
    main_path, _alpha, _bravo = main_and_refs
    app_driver.open(main_path)

    app_driver.go_to(("Parameterisation", "Cell", "Density [kg.m-3]"))

    assert not app_driver.main_file_heading_visible()
    assert not app_driver.ledger_visible()


def test_pull_takes_the_group_value_and_names_the_first_pinned_source(
    app_driver, main_and_refs, monkeypatch
):
    """The grouped Pull executes one source-named PullParameter: the value
    is the group's shared one, the source the group's first-pinned member
    (`Pull "<key>" from <source>` -- wording itself is pinned in
    test_command_service.py)."""
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    session = app_driver._w._state.active
    executed = []
    original = session.execute_command

    def capture(command):
        executed.append(command)
        return original(command)

    monkeypatch.setattr(session, "execute_command", capture)

    app_driver.click_ledger_pull(0)

    assert len(executed) == 1
    assert executed[0].value == 6.0
    assert executed[0].source_label == "alpha"
    assert app_driver.field_value() == 6.0
    # The pulled value now equals main: the whole (grouped) row reads same.
    assert app_driver.ledger_row_count() == 1
    assert app_driver.ledger_row_is_same(0)

    app_driver.undo()

    assert app_driver.field_value() == 5.0
    assert not app_driver.ledger_row_is_same(0)


def test_pull_on_fillable_row_pulls_the_reference_value(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Lower voltage cut-off [V]"))
    assert not app_driver.ledger_row_is_same(0)

    app_driver.click_ledger_pull(0)

    assert app_driver.field_value() == 3.0
    assert app_driver.ledger_row_is_same(0)


def test_pull_row_retints_the_list_and_undo_restores(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "differs"

    app_driver.click_ledger_pull(0)

    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "equal"

    app_driver.undo()

    assert app_driver.field_value() == 5.0
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") == "differs"


def test_pull_supersedes_a_dirty_draft_and_undo_restores_the_prior_value(
    app_driver, main_and_refs, monkeypatch
):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    app_driver.edit_field(7.0)
    assert app_driver.card_is_dirty()

    app_driver.click_ledger_pull(0)

    assert app_driver.field_value() == 6.0  # the reference value, not the discarded draft
    assert not app_driver.card_is_dirty()

    app_driver.undo()

    assert app_driver.field_value() == 5.0  # one undo restores the prior committed value
    assert not app_driver.card_is_dirty()


def test_bare_enter_after_a_pull_commits_nothing(app_driver, main_and_refs, monkeypatch):
    """The _touched pin (known Qt pitfall): the card the pull's own refresh
    rebuilds must not read as dirty, so a bare Enter afterwards is a no-op --
    a single undo still reverts the pull alone, not a phantom second commit."""
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))

    app_driver.click_ledger_pull(0)
    assert app_driver.field_value() == 6.0
    assert not app_driver.card_is_dirty()

    app_driver.commit()  # bare Enter, no edit

    assert app_driver.field_value() == 6.0  # unchanged: no spurious commit

    app_driver.undo()

    assert app_driver.field_value() == 5.0  # the pull was the only thing to revert


def test_pinning_then_selecting_differing_parameter_leaves_card_untouched(
    app_driver, main_and_refs, monkeypatch
):
    """The _touched regression pin (known Qt pitfall): populating the
    ledger must never mark the card touched, so a bare Enter after
    selection does not commit."""
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)

    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.ledger_visible()
    assert not app_driver.card_is_dirty()

    app_driver.commit()  # bare Enter, no edit

    assert app_driver.field_value() == 5.0  # unchanged: no spurious commit


# ---------------------------------------------------------------------------
# Ghost card: REF_ONLY keys, grouped per distinct value across pins.
# ---------------------------------------------------------------------------


def test_ghost_row_selection_shows_ghost_card_with_no_input_widget(
    app_driver, main_and_refs, monkeypatch
):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))

    app_driver.select_ghost_row("Electrode area [m2]")

    assert app_driver.ghost_card_shown()
    assert app_driver.ghost_card_heading_text() == "Not in the main file"
    assert "Electrode area" in app_driver.ghost_card_title_text()
    assert not app_driver.ghost_card_has_input_widget()
    assert app_driver.ledger_row_count() == 1
    assert app_driver.ledger_row_value_text(0) == "1.0"
    assert app_driver.ledger_row_unit_text(0) == "m2"
    assert not app_driver.ledger_row_is_same(0)

    app_driver.press_delete_in_parameter_list()
    assert "Electrode area [m2]" in app_driver.ghost_row_keys()


def test_ghost_card_groups_distinct_values_per_pin(app_driver, main_and_refs, monkeypatch):
    """Alpha holds 1.0 and bravo 2.0 for the same REF_ONLY key: two ledger
    rows, one badge each, both pullable."""
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))

    app_driver.select_ghost_row("Electrode area [m2]")

    assert app_driver.ghost_card_shown()
    assert app_driver.ledger_row_count() == 2
    assert app_driver.ledger_row_badges(0) == ["Al"]
    assert app_driver.ledger_row_value_text(0) == "1.0"
    assert app_driver.ledger_row_badges(1) == ["Br"]
    assert app_driver.ledger_row_value_text(1) == "2.0"


def test_ghost_pull_adds_and_selects_the_real_parameter(app_driver, main_and_refs, monkeypatch):
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell"))
    app_driver.select_ghost_row("Electrode area [m2]")
    assert app_driver.ghost_card_shown()

    app_driver.click_ledger_pull(1)  # bravo's row: the second distinct value

    assert not app_driver.ghost_card_shown()
    assert app_driver.shown_parameter_path() == ("Parameterisation", "Cell", "Electrode area [m2]")
    assert app_driver.field_value() == 2.0
    assert "Electrode area [m2]" not in app_driver.ghost_row_keys()


# ---------------------------------------------------------------------------
# Lifecycle: unpinning, replacing the main, the no-reference baseline.
# ---------------------------------------------------------------------------


def test_removing_the_last_reference_clears_everything_immediately(
    app_driver, main_and_refs, monkeypatch
):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.ledger_visible()
    assert app_driver.comparison_strip_visible()

    app_driver.click_reference_remove(0)

    assert not app_driver.comparison_strip_visible()
    assert app_driver.ghost_row_keys() == []
    assert app_driver.parameter_row_ref_bar("Nominal cell capacity") is None
    assert not app_driver.ledger_visible()
    assert app_driver.tree_node_ref_bar(_CELL_PATH) is None


def test_removing_one_of_two_references_keeps_the_other(app_driver, main_and_refs, monkeypatch):
    """Unpinning alpha promotes bravo to first (decision D1: identity is
    the current list index -- its badge colour shifts, its letters stay
    derived from its own name)."""
    main_path, alpha_path, bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    _pin_reference(app_driver, bravo_path, monkeypatch)
    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert app_driver.ledger_row_badges(0) == ["Al", "Br"]

    app_driver.click_reference_remove(0)

    assert app_driver.comparison_strip_chip_names() == ["bravo"]
    assert app_driver.ledger_row_count() == 1
    assert app_driver.ledger_row_badges(0) == ["Br"]
    # RT reverts to bravo-only state: differs (bravo disagrees).
    assert app_driver.parameter_row_ref_bar("Reference temperature") == "differs"


def test_replacing_the_main_document_with_reference_pinned_refreshes(
    app_driver, main_and_refs, monkeypatch, tmp_path
):
    main_path, alpha_path, _bravo_path = main_and_refs
    app_driver.open(main_path)
    _pin_reference(app_driver, alpha_path, monkeypatch)
    assert app_driver.comparison_strip_chip_tooltips() == ["alpha · SPM · 2 differ · 1 ref only"]

    matching_main_path = tmp_path / "matches_reference.json"
    matching_main_path.write_text(json.dumps(MATCHING_MAIN_RAW), encoding="utf-8")
    monkeypatch.setattr(
        app_driver._w, "_ask_open_intent", lambda filename: main_window_module.OpenIntent.REPLACE_MAIN
    )
    _stub_open_dialog(monkeypatch, matching_main_path)
    app_driver.click_workspace_open()

    assert app_driver.comparison_strip_chip_tooltips() == ["alpha · SPM · no differences"]
    app_driver.go_to(("Parameterisation", "Cell"))
    assert app_driver.ghost_row_keys() == []


def test_no_reference_pinned_is_structurally_todays_editor(app_driver, main_and_refs):
    main_path, _alpha, _bravo = main_and_refs
    app_driver.open(main_path)
    app_driver.go_to(("Parameterisation", "Cell"))

    assert not app_driver.comparison_strip_visible()
    assert app_driver.ghost_row_keys() == []
    for label in ("Reference temperature", "Nominal cell capacity", "Lower voltage cut-off", "Density"):
        assert app_driver.parameter_row_ref_bar(label) is None
    assert app_driver.tree_node_ref_bar(_CELL_PATH) is None

    app_driver.go_to(("Parameterisation", "Cell", "Nominal cell capacity [A.h]"))
    assert not app_driver.ledger_visible()


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


def test_pull_shape_change_scalar_to_table_reclassifies_the_card(
    app_driver, shape_change_main_and_ref, monkeypatch
):
    """"Custom Note" carries no schema metadata (an undeclared alias), so its
    kind follows the stored value's shape -- a same-key pull that changes
    shape is copied verbatim, and the card re-classifies to match."""
    main_path, ref_path = shape_change_main_and_ref
    app_driver.open(main_path)
    _pin_reference(app_driver, ref_path, monkeypatch)
    app_driver.go_to(("Header", "Custom Note"))
    assert type(app_driver._w._inspector._card._editor).__name__ == "ScalarCard"

    app_driver.click_ledger_pull(0)

    assert app_driver.field_value() == {"x": [0, 1], "y": [2, 3]}
    assert type(app_driver._w._inspector._card._editor).__name__ == "TableCard"


def test_end_to_end_with_bundled_about_energy_examples(app_driver, monkeypatch):
    """Real files, not fixtures, for realism (per the M2 brief) -- the LFP
    file's legacy-shape conversion is expected structural noise, not pinned
    here; only that the comparison is visibly non-trivial."""
    main_path = _ABOUT_ENERGY / "nmc_pouch_cell.json"
    ref_path = _ABOUT_ENERGY / "lfp_18650_cell.json"
    app_driver.open(main_path)
    _pin_reference(app_driver, ref_path, monkeypatch)

    assert app_driver.comparison_strip_visible()
    assert app_driver.comparison_strip_chip_names() == [ref_path.stem]
    tooltip = app_driver.comparison_strip_chip_tooltips()[0]
    assert tooltip.startswith(ref_path.stem)
    assert "no differences" not in tooltip
