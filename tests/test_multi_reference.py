"""Multi-reference comparison: several references pinned at once.

Covers what only appears once more than one reference exists -- the
Workspace's row-per-pin section and its cap, the strip's chips, the card
ledger's value grouping, the tree gutter's differs-from-any rule, the union
of ghost keys, and the Source page saying which of how many it is showing.
Single-reference behaviour stays in ``test_comparison_ui.py``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

import ui_qt.main_window as main_window_module
from core.commands import PullParameter
from state.app_state import MAX_PINNED_REFERENCES

_CELL_PATH = ("Parameterisation", "Cell")
_CAPACITY = _CELL_PATH + ("Nominal cell capacity [A.h]",)


def _document(cell: dict) -> dict:
    return {
        "Header": {"BPX": "1.0.0", "Title": "Test cell", "Model": "SPM"},
        "Parameterisation": {"Cell": dict(cell)},
    }


_MAIN = _document(
    {
        "Reference temperature [K]": 298.15,
        "Nominal cell capacity [A.h]": 5.0,
    }
)
#: Two references agreeing at capacity, one disagreeing -- the grouping case.
_REF_A = _document({"Reference temperature [K]": 298.15, "Nominal cell capacity [A.h]": 6.0})
_REF_B = _document({"Reference temperature [K]": 298.15, "Nominal cell capacity [A.h]": 7.0})
_REF_C = _document(
    {
        "Reference temperature [K]": 298.15,
        "Nominal cell capacity [A.h]": 6.0,
        "Electrode area [m2]": 1.0,
    }
)


def _write(tmp_path: Path, name: str, raw: dict) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(raw), encoding="utf-8")
    return path


def _strip_pins(*names: str) -> list:
    """Pins carrying only what the strip reads: identity and a comparison."""
    from state.reference_snapshot import ReferenceSnapshot
    from ui_qt.reference_identity import badge_colour, badge_letters
    from ui_qt.reference_identity import ReferencePin

    letters = badge_letters(list(names))
    return [
        ReferencePin(
            index=index,
            snapshot=ReferenceSnapshot(
                raw={},
                path=Path(name),
                filename=name,
                model="SPM",
                error_count=0,
                warning_count=0,
                section_count=0,
                parameter_count=0,
                mtime=0.0,
            ),
            comparison=None,
            letters=letters[index],
            colour=badge_colour(index),
        )
        for index, name in enumerate(names)
    ]


def _pin(app_driver, monkeypatch, path: Path) -> None:
    monkeypatch.setattr(
        main_window_module.QFileDialog, "getOpenFileName", lambda *a, **k: (str(path), "")
    )
    app_driver.click_workspace_open_reference()


@pytest.fixture
def three_pins(app_driver, tmp_path, monkeypatch):
    """A main document with chen/marquis/okane pinned, in that order."""
    app_driver.open(_write(tmp_path, "main.json", _MAIN))
    for name, raw in (("chen.json", _REF_A), ("marquis.json", _REF_B), ("okane.json", _REF_C)):
        _pin(app_driver, monkeypatch, _write(tmp_path, name, raw))
    return app_driver


# ---------------------------------------------------------------------------
# Workspace References section
# ---------------------------------------------------------------------------


def test_one_row_per_pin_in_pin_order(three_pins):
    d = three_pins
    assert d.pinned_reference_names() == ["chen.json", "marquis.json", "okane.json"]
    assert d.reference_row_badges() == ["Ch", "Ma", "Ok"]
    # The slots are the drawn cap, so "how many are left" is a count of
    # empty slots rather than a counter that has to be read.
    assert d.empty_slot_count() == MAX_PINNED_REFERENCES - 3


def test_rows_start_collapsed_and_click_expands_the_full_record(three_pins):
    d = three_pins
    assert not d.reference_row_expanded(1)

    d.click_reference_row(1)

    assert d.reference_row_expanded(1)
    detail = d.reference_row_detail_text(1)
    # The one record shape (Phase 4): identical rows to the main document,
    # read-only. Verbatim from the validator, whatever it says about this
    # fixture -- the row reports, it never judges.
    assert "Title: " in detail
    assert "Checked: " in detail
    assert "Contents: 3 sections" in detail
    # A file reference's From row names its path plus the disk facts.
    assert "From: " in detail
    assert "marquis.json" in detail
    # Expanding one row leaves the others alone.
    assert not d.reference_row_expanded(0)


def test_removing_a_pin_shifts_the_later_badges(three_pins):
    """Decision D1: colour and letters are the current pin order, so
    removing an earlier pin re-derives everything after it."""
    d = three_pins
    d.click_reference_remove(0)

    assert d.pinned_reference_names() == ["marquis.json", "okane.json"]
    assert d.reference_row_badges() == ["Ma", "Ok"]
    assert d.empty_slot_count() == MAX_PINNED_REFERENCES - 2


def test_the_last_slot_fills_and_there_is_no_plus_left_to_click(
    app_driver, tmp_path, monkeypatch
):
    """At the cap the ＋ simply is not there. Nothing has to explain itself,
    because nothing looks available -- the slots *are* the limit."""
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    for index in range(MAX_PINNED_REFERENCES):
        _pin(d, monkeypatch, _write(tmp_path, f"ref{index}.json", _REF_A))

    assert d.empty_slot_count() == 0
    assert not d.can_add_reference()

    d.click_reference_remove(0)

    assert d.can_add_reference()


def test_pinning_beyond_the_cap_is_refused_with_a_message(app_driver, tmp_path, monkeypatch):
    """The Workspace buttons already grey out at the cap, so this drives the
    handler directly -- the refusal has to hold on every route in, not only
    the one with a disabled button in front of it (drops, the Open dialog)."""
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    for index in range(MAX_PINNED_REFERENCES):
        _pin(d, monkeypatch, _write(tmp_path, f"ref{index}.json", _REF_A))

    d._w._open_reference_path(_write(tmp_path, "fifth.json", _REF_B))

    assert len(d.pinned_reference_names()) == MAX_PINNED_REFERENCES
    assert d.toast_text() == "4 already pinned · remove one first"


# ---------------------------------------------------------------------------
# Comparison strip
# ---------------------------------------------------------------------------


def test_strip_shows_a_quiet_chip_per_pin(three_pins):
    d = three_pins
    d.go_to(_CELL_PATH)

    assert d.comparison_strip_visible()
    assert d.comparison_strip_chip_names() == ["chen.json", "marquis.json", "okane.json"]
    # Counts are per reference and live only in the tooltip: okane carries an
    # extra key, so its ref-only count differs from the other two.
    tooltips = d.comparison_strip_chip_tooltips()
    assert "1 differs" in tooltips[0] and "reference only" not in tooltips[0]
    assert "1 reference only" in tooltips[2]


def test_strip_keeps_names_while_they_fit_and_drops_them_together(qtbot):
    """The strip takes whatever width the page bar has left, so whether
    names fit is a question of measured width, not a fixed breakpoint. Names
    go all-or-nothing: a row where some chips are named and some are not
    reads as an error, not as a fit."""
    from ui_qt.comparison_strip import ComparisonStrip

    strip = ComparisonStrip()
    qtbot.addWidget(strip)
    strip.set_state(_strip_pins("chen.json", "marquis.json", "okane.json"))
    strip.show()
    qtbot.waitExposed(strip)

    # setFixedWidth, not resize: the named chips give the strip's own layout
    # a minimum that resize() would be clamped to, where the real app's
    # parent layout simply hands it the column's width.
    strip.setFixedWidth(1000)
    assert all(not chip._name.isHidden() for chip in strip._chips)

    strip.setFixedWidth(200)
    assert all(chip._name.isHidden() for chip in strip._chips)

    # One reference's name fits the same width three did not.
    strip.set_state(_strip_pins("okane.json"))
    assert not strip._chips[0]._name.isHidden()


# ---------------------------------------------------------------------------
# Card ledger
# ---------------------------------------------------------------------------


def test_identical_reference_values_share_one_ledger_row(three_pins):
    """chen and okane both say 6.0; marquis says 7.0. Two rows, and the
    agreeing pair's badges cluster together."""
    d = three_pins
    d.go_to(_CAPACITY)

    assert d.ledger_row_count() == 2
    assert d.ledger_row_badges(0) == ["Ch", "Ok"]
    assert d.reference_value_text(0) == "6.0"
    assert d.ledger_row_badges(1) == ["Ma"]
    assert d.reference_value_text(1) == "7.0"


def test_all_references_agreeing_with_main_collapse_to_one_same_row(three_pins):
    d = three_pins
    d.go_to(_CELL_PATH + ("Reference temperature [K]",))

    assert d.ledger_row_count() == 1
    assert d.ledger_row_badges(0) == ["Ch", "Ma", "Ok"]
    assert d.reference_block_is_same()
    assert not d.pull_visible()


def test_a_reference_without_the_key_contributes_no_row(three_pins, tmp_path, monkeypatch):
    """Only okane has Electrode area, so its ghost card shows one row, not
    three -- an absent key is absent, never an empty placeholder."""
    d = three_pins
    d.go_to(_CELL_PATH)

    d.select_ghost_row("Electrode area [m2]")

    assert d.ghost_card_shown()
    assert d.ledger_row_count() == 1
    assert d.ledger_row_badges(0) == ["Ok"]


def test_pull_names_the_groups_first_pinned_source(three_pins, monkeypatch):
    """A grouped row pulls from the earliest-pinned member, and says so in
    the undo entry."""
    d = three_pins
    d.go_to(_CAPACITY)
    captured: list = []
    session = d._w._state.active
    original = session.execute_command
    monkeypatch.setattr(
        session,
        "execute_command",
        lambda command: (captured.append(command), original(command))[1],
    )

    d.click_pull(0)

    assert isinstance(captured[0], PullParameter)
    assert captured[0].source_label == "chen.json"
    assert captured[0].value == 6.0


# ---------------------------------------------------------------------------
# Spread scale (design rule 4)
# ---------------------------------------------------------------------------


def test_spread_scale_marks_every_distinct_value_and_the_main_one(three_pins):
    """Main 5.0, chen and okane 6.0, marquis 7.0: two ticks, the shared one
    carrying both its pins' badges, plus main's own marker."""
    d = three_pins
    d.go_to(_CAPACITY)

    assert d.spread_visible()
    assert d.spread_tick_values() == [6.0, 7.0]
    assert d.spread_tick_badges(0) == ["Ch", "Ok"]
    assert d.spread_tick_badges(1) == ["Ma"]
    assert d.spread_has_main_marker()


def test_spread_scale_hides_when_every_value_coincides(three_pins):
    """Reference temperature agrees everywhere, so the axis would be a
    picture of nothing -- and the "same" rows above already say it."""
    d = three_pins
    d.go_to(_CELL_PATH + ("Reference temperature [K]",))

    assert not d.spread_visible()


def test_spread_scale_hides_for_a_non_numeric_parameter(three_pins):
    """Gated on the kind the app already classified, never on a fresh look
    at the value: the Header's title is text, so it gets no axis."""
    d = three_pins
    d.go_to(("Header", "Title"))

    assert not d.spread_visible()


def test_spread_scale_hover_names_the_references_and_the_exact_value(three_pins):
    d = three_pins
    d.go_to(_CAPACITY)

    assert d.spread_tooltip_at_tick(0) == "chen.json, okane.json · 6.0"
    assert d.spread_tooltip_at_tick(1) == "marquis.json · 7.0"
    assert d.spread_tooltip_at_main() == "Main file · 5.0"


def test_spread_scale_names_a_linear_axis(three_pins):
    d = three_pins
    d.go_to(_CAPACITY)

    assert d.spread_axis_kind() == "linear"


def test_spread_scale_shows_labelled_divisions_not_a_caption(three_pins):
    """The redesign this covers: real division marks replace the old bare
    line's centred "log scale"/"linear scale" caption entirely -- nothing
    sets the widget's own tooltip any more, only marks do."""
    d = three_pins
    d.go_to(_CAPACITY)

    spread = d._spread()
    assert spread is not None and spread.is_active
    divisions = spread._scale.divisions
    assert len(divisions) >= 3
    assert all(division.label for division in divisions)
    assert spread.toolTip() == ""


def test_spread_scale_switches_to_log_past_two_decades(app_driver, tmp_path, monkeypatch):
    """The switch is never silent: the axis says which one it is."""
    d = app_driver
    d.open(_write(tmp_path, "main.json", _document({"Nominal cell capacity [A.h]": 1.0})))
    _pin(
        d,
        monkeypatch,
        _write(tmp_path, "big.json", _document({"Nominal cell capacity [A.h]": 5000.0})),
    )
    d.go_to(_CAPACITY)

    assert d.spread_visible()
    assert d.spread_axis_kind() == "log"


def test_spread_scale_stacks_dots_that_would_hide_each_other(qtbot):
    """Two stated values a fraction of the span apart are one dot covering
    another at any real width. They step up a level instead; only the level
    moves, never the x."""
    from core.spread import build_spread
    from ui_qt.cards.spread_scale import SpreadScaleView

    spread = SpreadScaleView()
    qtbot.addWidget(spread)
    spread.set_scale(build_spread(None, [28700.0, 28746.0, 33133.0]), _strip_pins("a", "b", "c"))
    spread.show()
    qtbot.waitExposed(spread)
    spread.setFixedWidth(280)

    placed = spread._placements()
    assert [tick.value for tick, _x, _base in placed] == [28700.0, 28746.0, 33133.0]
    assert [base for _tick, _x, base in placed] == [0, 1, 0]
    # Exact positions survive the stacking: the raised dot sits above its
    # own value, never nudged along the axis to make room.
    for tick, x, _base in placed:
        assert x == spread._x_for(tick.position)


def test_spread_scale_thins_division_labels_on_a_narrow_axis(qtbot):
    """Never let labels collide: at 30px, four decade labels ("1", "100",
    "10000", "1e+06") cannot all fit, so the visible set shrinks."""
    from core.spread import build_spread
    from PySide6.QtGui import QFontMetrics
    from ui_qt import typography
    from ui_qt.cards.spread_scale import SpreadScaleView

    scale = build_spread(None, [1.0, 1e7])
    spread = SpreadScaleView()
    qtbot.addWidget(spread)
    spread.set_scale(scale, _strip_pins("a"))
    spread.show()
    qtbot.waitExposed(spread)
    spread.setFixedWidth(30)

    metrics = QFontMetrics(typography.ui_font(typography.MICRO))
    visible = spread._visible_divisions(metrics)
    assert 1 <= len(visible) < len(scale.divisions)
    assert not spread._labels_collide(visible, metrics)


def test_spread_scale_shows_every_division_label_with_room_to_spare(qtbot):
    from core.spread import build_spread
    from PySide6.QtGui import QFontMetrics
    from ui_qt import typography
    from ui_qt.cards.spread_scale import SpreadScaleView

    scale = build_spread(None, [1.0, 1e7])
    spread = SpreadScaleView()
    qtbot.addWidget(spread)
    spread.set_scale(scale, _strip_pins("a"))
    spread.show()
    qtbot.waitExposed(spread)
    spread.setFixedWidth(1000)

    metrics = QFontMetrics(typography.ui_font(typography.MICRO))
    assert spread._visible_divisions(metrics) == list(scale.divisions)


def test_spread_scale_on_a_ghost_card_has_no_main_marker(app_driver, tmp_path, monkeypatch):
    """A key the main file lacks: the references still spread against each
    other, with nothing to anchor them to."""
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    for name, area in (("one.json", 1.0), ("two.json", 2.0)):
        raw = _document({"Nominal cell capacity [A.h]": 5.0, "Electrode area [m2]": area})
        _pin(d, monkeypatch, _write(tmp_path, name, raw))
    d.go_to(_CELL_PATH)

    d.select_ghost_row("Electrode area [m2]")

    assert d.spread_visible()
    assert d.spread_tick_values() == [1.0, 2.0]
    assert not d.spread_has_main_marker()


# ---------------------------------------------------------------------------
# Parameter list and tree gutter
# ---------------------------------------------------------------------------


def test_gutter_bar_shows_when_any_single_reference_differs(app_driver, tmp_path, monkeypatch):
    """Design rule 6: one dissenting reference is enough. A matching
    reference pinned first must not quieten the bar."""
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    _pin(d, monkeypatch, _write(tmp_path, "matches.json", _MAIN))

    assert d.tree_node_ref_bar(_CELL_PATH) == "equal"

    _pin(d, monkeypatch, _write(tmp_path, "differs.json", _REF_A))

    assert d.tree_node_ref_bar(_CELL_PATH) == "differs"


def test_row_bar_and_tooltip_name_every_distinct_reference_value(three_pins):
    d = three_pins
    d.go_to(_CELL_PATH)

    assert d.parameter_row_ref_bar("Nominal cell capacity") == "differs"
    tooltip = d.parameter_row_tooltip("Nominal cell capacity")
    # One line per distinct value, naming the references that hold it -- a
    # tooltip has no colour, so the file names carry identity there.
    assert "chen.json, okane.json: 6.0" in tooltip
    assert "marquis.json: 7.0" in tooltip


def test_ghost_rows_are_the_union_across_pins(three_pins):
    """Electrode area exists only in okane, and is still a ghost row: the
    union, not the intersection, is what the main document lacks."""
    d = three_pins
    d.go_to(_CELL_PATH)

    assert "Electrode area [m2]" in d.ghost_row_keys()


# ---------------------------------------------------------------------------
# Source page (honesty pass -- the selector itself is Phase 2)
# ---------------------------------------------------------------------------


def test_source_selector_offers_every_pin_and_starts_on_the_first(three_pins):
    d = three_pins
    d.show_view("Source")

    assert d.source_reference_badges() == ["Ch", "Ma", "Ok"]
    assert d.source_reference_badge_letters() == "Ch"
    assert "chen.json" in d.source_reference_header_text()


def test_source_selector_switches_which_reference_the_pane_shows(three_pins):
    d = three_pins
    d.show_view("Source")

    d.click_source_reference_badge(1)

    assert d.source_selected_reference_index() == 1
    assert d.source_reference_badge_letters() == "Ma"
    assert "marquis.json" in d.source_reference_header_text()


def test_source_pull_takes_the_value_from_the_selected_reference(three_pins, monkeypatch):
    """The ← arrows sit beside the reference pane, so they must pull from
    whichever reference that pane is showing."""
    d = three_pins
    d.show_view("Source")
    d.click_source_reference_badge(1)  # marquis, whose capacity is 7.0

    captured: list = []
    session = d._w._state.active
    original = session.execute_command
    monkeypatch.setattr(
        session,
        "execute_command",
        lambda command: (captured.append(command), original(command))[1],
    )

    d._w._on_source_pull(list(_CAPACITY), False)

    assert captured[0].value == 7.0
    assert captured[0].source_label == "marquis.json"


def test_source_reload_acts_on_the_selected_reference(three_pins, tmp_path):
    """Reload re-snapshots the reference being read, not merely the first
    pinned."""
    import os
    import time

    d = three_pins
    d.show_view("Source")
    d.click_source_reference_badge(1)

    changed = tmp_path / "marquis.json"
    changed.write_text(
        json.dumps(_document({"Nominal cell capacity [A.h]": 9.0})), encoding="utf-8"
    )
    os.utime(changed, (time.time() + 10, time.time() + 10))

    d._w._on_reload_reference()

    assert d._w._state.references[1].raw["Parameterisation"]["Cell"][
        "Nominal cell capacity [A.h]"
    ] == 9.0
    # The other pins are untouched by one reference's reload.
    assert d._w._state.references[0].filename == "chen.json"


def test_source_selector_is_a_single_badge_for_a_single_pin(app_driver, tmp_path, monkeypatch):
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    _pin(d, monkeypatch, _write(tmp_path, "chen.json", _REF_A))

    d.show_view("Source")

    assert d.source_reference_badges() == ["Ch"]
    assert d.source_reference_header_text().startswith("Reference  ·  chen.json")


def test_stale_band_names_a_reference_that_is_not_the_one_shown(
    three_pins, tmp_path, monkeypatch
):
    """The band watches every pin, not just the one on screen -- a reference
    going stale off screen is exactly what a first-pin-only check would miss
    in silence."""
    d = three_pins
    d.show_view("Source")
    assert not d.source_stale_band_visible()

    changed = tmp_path / "marquis.json"
    changed.write_text(json.dumps(_document({"Nominal cell capacity [A.h]": 9.0})), encoding="utf-8")
    import os
    import time

    os.utime(changed, (time.time() + 10, time.time() + 10))

    d._w._check_reference_stale()

    assert d.source_stale_band_visible()
    assert d.source_stale_band_text() == "marquis.json changed on disk"



# ---------------------------------------------------------------------------
# Phase 2: chart overlay and the reference-grid selector
# ---------------------------------------------------------------------------

_TABLE_MAIN = {
    "Header": {"BPX": "1.0.0", "Title": "T", "Model": "SPM"},
    "Parameterisation": {
        "Negative electrode": {"OCP [V]": {"x": [0.0, 0.5, 1.0], "y": [1.0, 0.5, 0.1]}}
    },
}


def _table_doc(x, y):
    return {
        "Header": {"BPX": "1.0.0", "Title": "T", "Model": "SPM"},
        "Parameterisation": {"Negative electrode": {"OCP [V]": {"x": x, "y": y}}},
    }


_OCP_PATH = ("Parameterisation", "Negative electrode", "OCP [V]")


@pytest.fixture
def table_pins(app_driver, tmp_path, monkeypatch):
    """A table-valued parameter with three references: two differing tables
    and one that matches main exactly."""
    app_driver.open(_write(tmp_path, "main.json", _TABLE_MAIN))
    for name, doc in (
        ("chen.json", _table_doc([0.0, 0.5, 1.0], [1.1, 0.6, 0.2])),
        # Stops at 0.5: its curve must end there, never be extended to meet
        # the others.
        ("marquis.json", _table_doc([0.0, 0.5], [0.9, 0.4])),
        ("okane.json", _table_doc([0.0, 0.5, 1.0], [1.0, 0.5, 0.1])),
    ):
        _pin(app_driver, monkeypatch, _write(tmp_path, name, doc))
    return app_driver


def test_grid_selector_offers_only_the_differing_references(table_pins):
    """okane matches main exactly, so it keeps its quiet "same" ledger row
    and never appears in the selector -- its column would repeat the
    editor's own numbers."""
    d = table_pins
    d.go_to(_OCP_PATH)

    assert d.reference_grid_visible()
    assert d.reference_grid_badges() == ["Ch", "Ma"]
    assert d.reference_grid_selected() == "Ch"


def test_grid_selector_switches_which_numbers_are_shown(table_pins):
    d = table_pins
    d.go_to(_OCP_PATH)
    assert d.reference_grid_row_count() == 3  # chen has three points

    d.click_reference_grid_badge(1)

    assert d.reference_grid_selected() == "Ma"
    assert d.reference_grid_row_count() == 2  # marquis stops at 0.5


def test_chart_overlays_one_curve_per_differing_reference(table_pins):
    d = table_pins
    d.go_to(_OCP_PATH)
    if not d.charts_available():
        pytest.skip("QtCharts is absent from this PySide6 build")

    assert d.chart_legend_badges() == ["Ch", "Ma"]
    # Each curve holds only its own reference's points: marquis stops at its
    # own domain edge rather than being extended to meet chen's.
    assert d.chart_curve_points(1) == [(0.0, 0.9), (0.5, 0.4)]


def test_chart_legend_badge_toggles_its_own_curve(table_pins):
    d = table_pins
    d.go_to(_OCP_PATH)
    if not d.charts_available():
        pytest.skip("QtCharts is absent from this PySide6 build")

    assert d.chart_curve_shown(0)

    d.click_chart_legend_badge(0)

    assert not d.chart_curve_shown(0)
    assert d.chart_curve_shown(1)  # the others are untouched
    # The points stay: a hidden curve is switched off, not thrown away.
    assert d.chart_curve_points(0)


def test_chart_legend_badge_tooltip_names_the_domain(table_pins):
    d = table_pins
    d.go_to(_OCP_PATH)
    if not d.charts_available():
        pytest.skip("QtCharts is absent from this PySide6 build")

    tooltip = d.chart_legend_tooltips()[1]
    assert tooltip.startswith("marquis.json")
    assert "domain 0 – 0.5" in tooltip
    assert "2 points" in tooltip
