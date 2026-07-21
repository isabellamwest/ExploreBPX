"""core.compare: the pure diff engine between a main raw dict and a
reference raw dict (multi-file track M2)."""

from __future__ import annotations

from pathlib import Path

from core import bpx_gateway
from core.compare import ComparisonResult, RowState, compare, raw_equal

APP_DIR = Path(__file__).resolve().parents[1] / "app"
_ABOUT_ENERGY = APP_DIR / "data" / "example_documents" / "about_energy"


def _load(stem: str) -> dict:
    path = _ABOUT_ENERGY / f"{stem}.json"
    raw, _fmt = bpx_gateway.load_raw(path.read_bytes(), path.name)
    return raw


def test_order_independence_of_key_order_in_either_dict():
    """Shuffling a dict's own key order never changes the comparison."""
    main_raw = {
        "Section": {
            "A": 1,
            "B": 2.0,
            "Nested": {"C": "hello", "D": [1, 2, 3]},
        },
        "Other": {"E": None},
    }
    ref_raw = {
        "Other": {"E": 5},
        "Section": {
            "Nested": {"D": [1, 2, 3], "C": "hello"},
            "B": 2.0,
            "A": 9,
        },
    }
    shuffled_main = {
        "Other": {"E": None},
        "Section": {
            "Nested": {"D": [1, 2, 3], "C": "hello"},
            "B": 2.0,
            "A": 1,
        },
    }

    baseline = compare(main_raw, ref_raw)
    shuffled = compare(shuffled_main, ref_raw)

    assert baseline == shuffled
    assert isinstance(baseline, ComparisonResult)


def test_units_in_key_never_unit_converted_or_fuzzy_matched():
    """``Thickness [m]`` and ``Thickness [µm]`` are different keys: one
    main-only, one ref-only, never DIFFERS (locked decision 1)."""
    main_raw = {"Section": {"Thickness [m]": 1.0}}
    ref_raw = {"Section": {"Thickness [µm]": 1000.0}}

    result = compare(main_raw, ref_raw)
    section = result.section(("Section",))

    assert section.rows["Thickness [m]"].state is RowState.MAIN_ONLY
    assert section.rows["Thickness [µm]"].state is RowState.REF_ONLY
    assert "Thickness [m]" not in [
        key for key, row in section.rows.items() if row.state is RowState.DIFFERS
    ]


def test_bool_vs_int_differs_not_equal():
    """``true`` (bool) vs ``1`` (int): Python's ``True == 1`` must not leak
    into raw comparison -- their JSON representations differ."""
    assert raw_equal(True, 1) is False
    assert raw_equal(1, True) is False

    main_raw = {"Section": {"Flag": True}}
    ref_raw = {"Section": {"Flag": 1}}
    result = compare(main_raw, ref_raw)
    assert result.row(("Section",), "Flag").state is RowState.DIFFERS


def test_int_vs_float_differs():
    """``1`` (int) vs ``1.0`` (float): chosen to DIFFER, not to be treated as
    numerically equal. This mirrors ``core.values.values_equal``'s existing
    rule (typing ``5.0`` over a stored ``5`` is a real, type-changing edit,
    not a no-op) -- raw comparison here reuses that exact convention rather
    than inventing a second notion of "the same number"."""
    assert raw_equal(1, 1.0) is False

    main_raw = {"Section": {"Value": 1}}
    ref_raw = {"Section": {"Value": 1.0}}
    result = compare(main_raw, ref_raw)
    assert result.row(("Section",), "Value").state is RowState.DIFFERS


def test_nested_table_identical_is_equal_one_point_changed_differs():
    main_raw = {
        "Section": {"Curve [A]": {"x": [0, 1, 2], "y": [1.0, 2.0, 3.0]}},
    }
    ref_same = {
        "Section": {"Curve [A]": {"x": [0, 1, 2], "y": [1.0, 2.0, 3.0]}},
    }
    ref_changed = {
        "Section": {"Curve [A]": {"x": [0, 1, 2], "y": [1.0, 2.0, 99.0]}},
    }

    equal_result = compare(main_raw, ref_same)
    assert equal_result.row(("Section",), "Curve [A]").state is RowState.EQUAL

    differs_result = compare(main_raw, ref_changed)
    assert differs_result.row(("Section",), "Curve [A]").state is RowState.DIFFERS


def test_fillable_reuses_completions_null_emptiness_rule():
    """A main value committed as literal ``None`` with a non-empty reference
    value is FILLABLE, not DIFFERS -- reusing ``core.completion``'s own
    "committed null" emptiness rule (no new one invented). Both empty is
    EQUAL; a real, non-``None`` falsy value (``0``) is never treated as
    empty."""
    main_raw = {
        "Section": {
            "Unset": None,
            "BothUnset": None,
            "Zero": 0,
        }
    }
    ref_raw = {
        "Section": {
            "Unset": 42,
            "BothUnset": None,
            "Zero": 5,
        }
    }

    result = compare(main_raw, ref_raw)
    section = result.section(("Section",))

    assert section.rows["Unset"].state is RowState.FILLABLE
    assert section.rows["Unset"].ref_value == 42
    assert section.rows["BothUnset"].state is RowState.EQUAL
    assert section.rows["Zero"].state is RowState.DIFFERS


def test_ghost_section_counting_and_totals():
    """A whole section absent from the main is a ghost section; its key
    count and the whole-file totals agree."""
    main_raw = {"Kept": {"A": 1}}
    ref_raw = {
        "Kept": {"A": 1},
        "GhostSection": {"X": 1, "Y": 2, "Z": 3},
    }

    result = compare(main_raw, ref_raw)

    ghost_sections = result.ghost_sections
    assert len(ghost_sections) == 1
    ghost = ghost_sections[0]
    assert ghost.path == ("GhostSection",)
    assert ghost.is_ghost is True
    assert ghost.ref_only_count == 3
    assert set(ghost.ghost_keys) == {"X", "Y", "Z"}

    assert result.ref_only_count == 3
    assert result.differ_count == 0
    assert result.main_only_count == 0
    assert result.main_only_sections == ()


def test_main_only_section_counting():
    """A whole section absent from the reference is main-only, no tint
    implied -- but still queryable, key by key."""
    main_raw = {
        "Kept": {"A": 1},
        "MainOnlySection": {"P": 1, "Q": 2},
    }
    ref_raw = {"Kept": {"A": 1}}

    result = compare(main_raw, ref_raw)

    main_only_sections = result.main_only_sections
    assert len(main_only_sections) == 1
    section = main_only_sections[0]
    assert section.path == ("MainOnlySection",)
    assert section.is_main_only is True
    assert section.main_only_count == 2
    assert result.main_only_count == 2
    assert result.ghost_sections == ()


def test_compare_never_mutates_its_inputs():
    main_raw = {"Section": {"A": 1, "B": None}}
    ref_raw = {"Section": {"A": 2, "C": 3}}
    main_copy = {"Section": {"A": 1, "B": None}}
    ref_copy = {"Section": {"A": 2, "C": 3}}

    compare(main_raw, ref_raw)

    assert main_raw == main_copy
    assert ref_raw == ref_copy


def test_end_to_end_against_bundled_about_energy_examples():
    """Real files, not fixtures: an LFP cell (main, no ``State``) against an
    NMC cell (reference, has ``State``). Spot-checks known keys rather than
    pinning fragile whole-file totals, per the brief."""
    lfp_raw = _load("lfp_18650_cell")
    nmc_raw = _load("nmc_pouch_cell")

    result = compare(lfp_raw, nmc_raw)

    # The NMC file's ``State`` section has no counterpart in the LFP file --
    # a whole ghost subtree. ``State`` itself owns no direct parameters (its
    # own leaves all live one level deeper, mirroring the app's own tree:
    # ``core.tree_model``'s ``_STATIC_PATHS`` lists ``("State", "Initial
    # conditions")``/``("State", "Thermal environment")`` as the real
    # sections), so the ghost rows land on those nested paths instead.
    state_ghost_paths = {section.path for section in result.ghost_sections if section.path[:1] == ("State",)}
    assert ("State",) in state_ghost_paths
    assert ("State", "Initial conditions") in state_ghost_paths
    assert ("State", "Thermal environment") in state_ghost_paths
    state_ref_only_total = sum(
        section.ref_only_count for section in result.ghost_sections if section.path[:1] == ("State",)
    )
    assert state_ref_only_total > 0

    cell = result.section(("Parameterisation", "Cell"))
    assert cell is not None
    assert cell.in_main and cell.in_reference

    # Both files declare 298.15 K as their reference temperature.
    assert cell.rows["Reference temperature [K]"].state is RowState.EQUAL
    # Two real, distinct cells: their capacities differ.
    assert cell.rows["Nominal cell capacity [A.h]"].state is RowState.DIFFERS
    # The LFP file's Cell section carries fields the NMC file's Cell lacks.
    assert cell.rows["Ambient temperature [K]"].state is RowState.MAIN_ONLY
    assert cell.rows["Initial temperature [K]"].state is RowState.MAIN_ONLY

    # Self-consistency: whole-file totals are at least what these sections
    # alone already account for.
    assert result.ref_only_count >= state_ref_only_total
    assert result.differ_count >= cell.differ_count
    assert result.main_only_count >= cell.main_only_count
