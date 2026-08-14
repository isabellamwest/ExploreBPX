"""core.compare: the pure diff engine between a main raw dict and a
reference raw dict (multi-file track M2)."""

from __future__ import annotations

from pathlib import Path

from core import bpx_gateway
from core.compare import (
    ComparisonResult,
    RowDiff,
    RowState,
    SectionDiff,
    ValueGroup,
    compare,
    group_reference_values,
    matching_table_rows,
    merged_ghost_keys,
    merged_row_state,
    raw_equal,
)

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
    main-only, one ref-only, never DIFFERS."""
    main_raw = {"Section": {"Thickness [m]": 1.0}}
    ref_raw = {"Section": {"Thickness [µm]": 1000.0}}

    result = compare(main_raw, ref_raw)
    section = result.section(("Section",))

    assert section.rows["Thickness [m]"].state is RowState.MAIN_ONLY
    assert section.rows["Thickness [µm]"].state is RowState.REF_ONLY
    assert "Thickness [m]" not in [key for key, row in section.rows.items() if row.state is RowState.DIFFERS]


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
    assert cell.in_main
    assert cell.in_reference

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


# ----------------------------------------------------------------------
# matching_table_rows: per-row match used by the reference card's table grid
# ----------------------------------------------------------------------


def test_matching_table_rows_marks_rows_with_no_equal_pair_in_main():
    main_rows = [[0, 2.0], [1, 3.0]]
    ref_rows = [[0, 2.0], [1, 3.0], [5, 9.0]]
    assert matching_table_rows(main_rows, ref_rows) == [True, True, False]


def test_matching_table_rows_is_order_independent():
    """A ref row matches wherever the equal main row sits, not only at the
    same index."""
    main_rows = [[1, 3.0], [0, 2.0]]
    ref_rows = [[0, 2.0], [1, 3.0]]
    assert matching_table_rows(main_rows, ref_rows) == [True, True]


def test_matching_table_rows_is_type_aware_at_the_leaves():
    """1 (int) and 1.0 (float) are not the same cell -- the same leaf rule
    raw_equal uses (values_equal), never loosened for a table row."""
    main_rows = [[1, 2]]
    ref_rows = [[1.0, 2.0]]
    assert matching_table_rows(main_rows, ref_rows) == [False]


def test_matching_table_rows_empty_main_marks_every_ref_row_false():
    assert matching_table_rows([], [[0, 1.0]]) == [False]


# ----------------------------------------------------------------------
# group_reference_values: Card Ledger grouping
# ----------------------------------------------------------------------


def test_group_reference_values_groups_identical_values_together():
    rows = [
        RowDiff(RowState.DIFFERS, 6.0),
        RowDiff(RowState.DIFFERS, 7.0),
        RowDiff(RowState.DIFFERS, 6.0),
    ]
    groups = group_reference_values(rows)
    assert groups == (
        ValueGroup((0, 2), 6.0, False),
        ValueGroup((1,), 7.0, False),
    )


def test_group_reference_values_preserves_pin_order_within_and_across_groups():
    """Groups appear in first-pinned order, and each group's own member
    indices stay pin-order too, even when a later pin re-joins an earlier
    group."""
    rows = [
        RowDiff(RowState.DIFFERS, "b"),
        RowDiff(RowState.DIFFERS, "a"),
        RowDiff(RowState.DIFFERS, "b"),
        RowDiff(RowState.DIFFERS, "a"),
    ]
    groups = group_reference_values(rows)
    assert [g.indices for g in groups] == [(0, 2), (1, 3)]
    assert [g.value for g in groups] == ["b", "a"]


def test_group_reference_values_none_entries_contribute_nothing():
    """A ``None`` entry -- that reference has no comparison for this key at
    all (its section is absent) -- is skipped, not turned into its own
    group."""
    rows = [RowDiff(RowState.DIFFERS, 1.0), None, RowDiff(RowState.DIFFERS, 1.0)]
    groups = group_reference_values(rows)
    assert len(groups) == 1
    assert groups[0].indices == (0, 2)


def test_group_reference_values_main_only_rows_contribute_nothing():
    """A MAIN_ONLY row means this particular reference has no value for the
    key -- same as a ``None`` entry, it forms no group."""
    rows = [RowDiff(RowState.MAIN_ONLY), RowDiff(RowState.DIFFERS, 5.0)]
    groups = group_reference_values(rows)
    assert len(groups) == 1
    assert groups[0].indices == (1,)


def test_group_reference_values_all_absent_returns_no_groups():
    assert group_reference_values([None, RowDiff(RowState.MAIN_ONLY)]) == ()


def test_group_reference_values_equal_state_flags_equals_main_true():
    rows = [RowDiff(RowState.EQUAL, 298.15), RowDiff(RowState.DIFFERS, 300.0)]
    groups = group_reference_values(rows)
    equal_group = next(g for g in groups if g.value == 298.15)
    differs_group = next(g for g in groups if g.value == 300.0)
    assert equal_group.equals_main is True
    assert differs_group.equals_main is False


def test_group_reference_values_ref_only_rows_still_group_for_ghost_cards():
    """The ghost-card case: main lacks the key entirely, so every reference
    that has it is REF_ONLY -- these group exactly like any other state
    (ghost_card.py reuses this helper), never excluded the way MAIN_ONLY is."""
    rows = [RowDiff(RowState.REF_ONLY, 1.0), RowDiff(RowState.REF_ONLY, 1.0)]
    groups = group_reference_values(rows)
    assert len(groups) == 1
    assert groups[0].indices == (0, 1)
    assert groups[0].equals_main is False


def test_group_reference_values_uses_raw_equal_for_nested_tables():
    """Identical nested table/function shapes group together -- the same
    structural equality raw_equal gives ``compare()`` itself, not a shallow
    ``==`` on the dict/list objects."""
    table_a = {"x": [1, 2], "y": [3, 4]}
    table_b = {"x": [1, 2], "y": [3, 4]}
    table_c = {"x": [1, 2], "y": [3, 5]}
    rows = [
        RowDiff(RowState.DIFFERS, table_a),
        RowDiff(RowState.DIFFERS, table_b),
        RowDiff(RowState.DIFFERS, table_c),
    ]
    groups = group_reference_values(rows)
    assert len(groups) == 2
    assert groups[0].indices == (0, 1)
    assert groups[1].indices == (2,)


# ---------------------------------------------------------------------------
# merged_row_state / merged_ghost_keys: one mark against N pinned references
# ---------------------------------------------------------------------------


def test_merged_row_state_is_differs_when_any_reference_differs():
    """Design rule 6: one dissenting reference is enough, whatever the
    others say and whichever order they were pinned in."""
    rows = [RowDiff(RowState.EQUAL, 1.0), RowDiff(RowState.DIFFERS, 2.0)]
    assert merged_row_state(rows) is RowState.DIFFERS
    assert merged_row_state(list(reversed(rows))) is RowState.DIFFERS


def test_merged_row_state_keeps_fillable_distinct_from_differs():
    """FILLABLE and DIFFERS are told apart by whether *main* is empty, and
    every reference is compared against the same main -- so the two can
    never genuinely conflict, and the state survives unflattened."""
    rows = [RowDiff(RowState.FILLABLE, 1.0), RowDiff(RowState.FILLABLE, 2.0)]
    assert merged_row_state(rows) is RowState.FILLABLE


def test_merged_row_state_falls_through_equal_then_ref_only_then_main_only():
    assert merged_row_state([RowDiff(RowState.EQUAL, 1.0), RowDiff(RowState.MAIN_ONLY)]) is RowState.EQUAL
    assert merged_row_state([RowDiff(RowState.REF_ONLY, 1.0), RowDiff(RowState.MAIN_ONLY)]) is RowState.REF_ONLY
    assert merged_row_state([RowDiff(RowState.MAIN_ONLY)]) is RowState.MAIN_ONLY


def test_merged_row_state_is_none_when_no_reference_has_an_opinion():
    assert merged_row_state([]) is None
    assert merged_row_state([None, None]) is None


def test_merged_ghost_keys_is_the_union_in_first_contributing_pin_order():
    """A key only one reference carries is still something the main document
    lacks, so the union -- not the intersection -- is what renders."""
    first = SectionDiff(
        ("Parameterisation", "Cell"),
        in_main=True,
        in_reference=True,
        rows={"A": RowDiff(RowState.REF_ONLY, 1), "B": RowDiff(RowState.REF_ONLY, 2)},
    )
    second = SectionDiff(
        ("Parameterisation", "Cell"),
        in_main=True,
        in_reference=True,
        rows={"B": RowDiff(RowState.REF_ONLY, 2), "C": RowDiff(RowState.REF_ONLY, 3)},
    )
    assert merged_ghost_keys([first, second]) == ("A", "B", "C")


def test_merged_ghost_keys_skips_references_with_no_such_section():
    section = SectionDiff(
        ("Parameterisation", "Cell"),
        in_main=True,
        in_reference=True,
        rows={"A": RowDiff(RowState.REF_ONLY, 1)},
    )
    assert merged_ghost_keys([None, section, None]) == ("A",)
    assert merged_ghost_keys([None]) == ()
