"""Pure badge-identity rules (``ui_qt.reference_identity``): display names,
two-letter badges with the collision fallback, and pin-order colours
(decision D1: colour = current list index, no extra state).
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("PySide6")

from core.compare import compare
from state.reference_snapshot import ReferenceSnapshot
from ui_qt.reference_identity import badge_letters, build_pins, display_name
from ui_qt.style import REFERENCE_BADGE_COLOURS


def _snapshot(filename: str, set_id: str | None = None) -> ReferenceSnapshot:
    return ReferenceSnapshot(
        raw={},
        path=None if set_id else Path(filename),
        filename=filename,
        model="SPM",
        error_count=0,
        warning_count=0,
        section_count=0,
        parameter_count=0,
        mtime=None if set_id else 0.0,
        set_id=set_id,
    )


def test_display_name_drops_the_file_extension():
    assert display_name(_snapshot("my_cell_dfn.json")) == "my_cell_dfn"
    assert display_name(_snapshot("AE-LFP.yaml")) == "AE-LFP"


def test_display_name_drops_a_library_sets_cell_parenthetical():
    snapshot = _snapshot("Chen2020 (LG M50 21700)", set_id="pybamm/chen2020")
    assert display_name(snapshot) == "Chen2020"


def test_badge_letters_take_the_first_two_characters_preserving_case():
    assert badge_letters(["Chen2020", "OKane2022", "AE-LFP", "marquis2019"]) == [
        "Ch",
        "OK",
        "AE",
        "Ma",
    ]


def test_badge_letters_collision_falls_back_to_first_letter_plus_ordinal():
    """Two names sharing natural letters both fall back to first letter +
    1-based pin ordinal, so no two badges ever read the same."""
    assert badge_letters(["Chen2020", "Chapman2021"]) == ["C1", "C2"]
    # Non-colliding neighbours keep their natural letters.
    assert badge_letters(["Chen2020", "Chapman2021", "OKane2022"]) == ["C1", "C2", "OK"]


def test_badge_letters_degenerate_names_still_produce_something():
    assert badge_letters(["a"]) == ["A"]
    assert badge_letters([""]) == ["R"]


def test_build_pins_assigns_colours_by_current_list_index():
    snapshots = [_snapshot(f"pin_{i}.json") for i in range(4)]
    pins = build_pins(snapshots, [])

    assert [pin.colour for pin in pins] == list(REFERENCE_BADGE_COLOURS)
    assert all(pin.comparison is None for pin in pins)

    # Decision D1: removing the first pin shifts every later colour up.
    shifted = build_pins(snapshots[1:], [])
    assert [pin.colour for pin in shifted] == list(REFERENCE_BADGE_COLOURS[:3])


def test_build_pins_tolerates_fewer_comparisons_than_references():
    """``_update_workspace_info`` may run before the comparison recompute:
    the unmatched tail gets ``comparison=None`` rather than misaligning."""
    snapshots = [_snapshot("a.json"), _snapshot("b.json")]
    main = {"Header": {"BPX": "0.1.0", "Title": "T", "Model": "SPM"}}
    comparisons = [compare(main, main)]

    pins = build_pins(snapshots, comparisons)

    assert pins[0].comparison is comparisons[0]
    assert pins[1].comparison is None
