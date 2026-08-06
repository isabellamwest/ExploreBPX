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
        "Header": {"BPX": "0.1.0", "Title": "Test cell", "Model": "SPM"},
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
    assert d.reference_cap_text() == f"3 of {MAX_PINNED_REFERENCES} pinned"


def test_rows_start_collapsed_and_click_expands_the_full_record(three_pins):
    d = three_pins
    assert not d.reference_row_expanded(1)

    d.click_reference_row(1)

    assert d.reference_row_expanded(1)
    detail = d.reference_row_detail_text(1)
    assert "Origin: File on disk" in detail
    # Verbatim from the validator, whatever it says about this fixture --
    # the row reports, it never judges.
    assert "Validity: " in detail
    assert "Contents: 3 sections" in detail
    # A file reference names its path; a library set would cite its paper.
    assert "File: " in detail
    assert "Citation" not in detail
    # Expanding one row leaves the others alone.
    assert not d.reference_row_expanded(0)


def test_removing_a_pin_shifts_the_later_badges(three_pins):
    """Decision D1: colour and letters are the current pin order, so
    removing an earlier pin re-derives everything after it."""
    d = three_pins
    d.click_reference_remove(0)

    assert d.pinned_reference_names() == ["marquis.json", "okane.json"]
    assert d.reference_row_badges() == ["Ma", "Ok"]
    assert d.reference_cap_text() == f"2 of {MAX_PINNED_REFERENCES} pinned"


def test_entry_buttons_disable_at_the_cap(app_driver, tmp_path, monkeypatch):
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    for index in range(MAX_PINNED_REFERENCES):
        _pin(d, monkeypatch, _write(tmp_path, f"ref{index}.json", _REF_A))

    assert d.reference_cap_text() == f"4 of {MAX_PINNED_REFERENCES} pinned"
    assert not d.reference_entry_buttons_enabled()

    d.click_reference_remove(0)

    assert d.reference_entry_buttons_enabled()


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
    assert "1 differs" in tooltips[0] and "ref only" not in tooltips[0]
    assert "1 ref only" in tooltips[2]


def test_strip_keeps_names_while_they_fit_and_drops_them_together(qtbot):
    """The strip lives in the parameter list's own narrow column, so whether
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


def test_source_header_says_which_reference_of_how_many(three_pins):
    d = three_pins
    d.show_view("Source")

    assert d.source_reference_header_text().startswith("Reference 1 of 3")
    assert "chen.json" in d.source_reference_header_text()
    assert d.source_reference_badge_letters() == "Ch"


def test_source_header_drops_the_ordinal_for_a_single_pin(app_driver, tmp_path, monkeypatch):
    d = app_driver
    d.open(_write(tmp_path, "main.json", _MAIN))
    _pin(d, monkeypatch, _write(tmp_path, "chen.json", _REF_A))

    d.show_view("Source")

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

