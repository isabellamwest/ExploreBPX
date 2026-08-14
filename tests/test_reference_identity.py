"""Badge identity: the pure letters/colour rules behind every pinned
reference's badge.

No Qt and no widgets here -- ``reference_identity`` derives identity from
pin order alone, so it can be checked as arithmetic. The surfaces that
*paint* badges are covered by the comparison-UI and workspace tests.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from explore_bpx.state.reference_snapshot import ReferenceSnapshot
from explore_bpx.ui_qt import style
from explore_bpx.ui_qt.reference_identity import badge_colour, badge_letters, build_pins


def _snapshot(filename: str) -> ReferenceSnapshot:
    return ReferenceSnapshot(
        raw={},
        path=Path(filename),
        filename=filename,
        model="DFN",
        error_count=0,
        warning_count=0,
        section_count=0,
        parameter_count=0,
        mtime=0.0,
    )


def test_letters_are_the_first_two_alphanumerics():
    assert badge_letters(["Chen2020", "Marquis2019", "AE-LFP"]) == ["Ch", "Ma", "AE"]


def test_source_capitalisation_survives():
    """ "OKane2022" keeps its own capitals -- an all-caps name is a
    deliberate spelling, not something to flatten to title case."""
    assert badge_letters(["OKane2022"]) == ["OK"]
    assert badge_letters(["my_cell.json"]) == ["My"]


def test_punctuation_and_separators_are_skipped():
    assert badge_letters(["_ae-lfp.json"]) == ["Ae"]


def test_a_name_with_no_letters_still_gets_a_badge():
    assert badge_letters(["___"]) == ["?"]


def test_a_one_character_name_gets_a_one_character_badge():
    assert badge_letters(["a.json"]) == ["Aj"]  # the extension counts
    assert badge_letters(["x"]) == ["X"]


def test_colliding_names_both_fall_back_to_first_letter_plus_pin_ordinal():
    """Both members change, not just the later one: "Ch" beside "C3" would
    leave the first badge claiming letters it no longer identifies."""
    assert badge_letters(["Chen2020", "Marquis2019", "Chen2023"]) == ["C1", "Ma", "C3"]


def test_a_third_collision_joins_the_same_fallback():
    assert badge_letters(["Chen_a", "Chen_b", "Chen_c"]) == ["C1", "C2", "C3"]


def test_colours_follow_pin_order():
    assert [badge_colour(index) for index in range(4)] == list(style.REFERENCE_BADGES)


def test_badge_colours_never_collide_with_the_reserved_hues():
    reserved = {style.REFERENCE, style.ACCENT, style.OK, style.WARNING, style.ERROR}
    assert reserved.isdisjoint(style.REFERENCE_BADGES)
    assert len(set(style.REFERENCE_BADGES)) == 4


def test_build_pins_pairs_snapshots_with_identity_and_comparison():
    references = [_snapshot("Chen2020.json"), _snapshot("Marquis2019.json")]
    comparisons = ["first-comparison"]  # positional stand-ins; shape is untouched

    pins = build_pins(references, comparisons)

    assert [pin.index for pin in pins] == [0, 1]
    assert [pin.name for pin in pins] == ["Chen2020.json", "Marquis2019.json"]
    assert [pin.letters for pin in pins] == ["Ch", "Ma"]
    assert [pin.colour for pin in pins] == list(style.REFERENCE_BADGES[:2])
    # A shorter comparisons list means "not compared yet", never a shorter
    # pin list: a reference is pinned whether or not a main document is open.
    assert [pin.comparison for pin in pins] == ["first-comparison", None]


def test_removing_an_earlier_pin_shifts_the_later_colours():
    """Colour is the current list index, so identity is
    recomputed rather than stored -- nothing can go stale."""
    references = [_snapshot("a.json"), _snapshot("b.json"), _snapshot("c.json")]

    before = build_pins(references, [])
    after = build_pins(references[1:], [])

    assert before[1].colour == style.REFERENCE_BADGES[1]
    assert after[0].snapshot is before[1].snapshot
    assert after[0].colour == style.REFERENCE_BADGES[0]
